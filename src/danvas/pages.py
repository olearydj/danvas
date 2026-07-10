"""Canvas Page authoring, rendering, and bounded write workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import markdown as markdown_lib
import tinycss2
import yaml
from bs4 import BeautifulSoup, Comment, Tag
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.auth import canvas_from_args
from danvas.frontmatter import normalize_canvas_value, parse_frontmatter
from danvas.reports import create_report_run, should_write_report_run
from danvas.source_map import (
    find_source_entry,
    load_source_map,
    resolve_source_canvas_id,
    source_path_key,
    write_source_map_entry,
)
from danvas.utils import canvas_object_to_dict, print_mutation_banner, write_json

RENDERER_VERSION = "pages-markdown-v1"
COMPATIBILITY_PROFILE = "canvas-page-v1"
BODY_NORMALIZER_VERSION = "pages-html-v2"

ALLOWED_TAGS = {
    "a", "abbr", "blockquote", "br", "caption", "code", "col", "colgroup", "dd", "del",
    "details", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4",
    "h5", "h6", "hr", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "s",
    "small", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "ul",
}
GLOBAL_ATTRS = {"class", "id", "lang", "dir", "role", "title"}
TAG_ATTRS = {
    "a": {"href", "target", "rel", "aria-label"},
    "img": {"src", "alt", "width", "height", "aria-label"},
    "ol": {"start", "reversed", "type"},
    "li": {"value"},
    "table": {"summary", "width"},
    "th": {"scope", "colspan", "rowspan", "headers", "abbr", "width"},
    "td": {"colspan", "rowspan", "headers", "width"},
    "col": {"span", "width"},
    "colgroup": {"span", "width"},
}
SAFE_CSS_PROPERTIES = {
    "background-color", "border", "border-bottom", "border-color", "border-left", "border-radius",
    "border-right", "border-style", "border-top", "border-width", "color", "display", "font-family",
    "font-size", "font-style", "font-weight", "letter-spacing", "line-height", "list-style-type",
    "margin", "margin-bottom", "margin-left", "margin-right", "margin-top", "max-width", "min-width",
    "padding", "padding-bottom", "padding-left", "padding-right", "padding-top", "text-align",
    "text-decoration", "text-transform", "vertical-align", "white-space", "width", "word-break",
}
URL_ATTRS = {"href", "src"}
UNSAFE_SCHEMES = {"javascript", "vbscript", "data"}
VOLATILE_QUERY_NAMES = {
    "access_token", "expires", "key-pair-id", "policy", "signature", "token", "verifier"
}
NONSEMANTIC_CANVAS_ATTRS = {
    "data-api-endpoint", "data-api-returntype", "data-canvas-previewable", "data-id",
    "data-mce-href", "data-mce-src", "data-mce-style",
}
LOCAL_ASSET_SUFFIXES = {
    ".avif", ".csv", ".doc", ".docx", ".gif", ".jpeg", ".jpg", ".mp3", ".mp4", ".pdf",
    ".png", ".ppt", ".pptx", ".svg", ".webp", ".xls", ".xlsx", ".zip",
}


@dataclass
class PageSource:
    source: Path
    metadata: dict[str, Any]
    body: str
    html: str
    body_sha256: str
    warnings: list[str]
    unresolved_assets: list[str]
    anchors: list[str]
    local_links: list[str]
    css_report: dict[str, Any] | None
    matching_h1_removed: bool


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_page_url(value: str, *, course_id: int | None = None) -> tuple[str, bool]:
    """Return a stable Page URL and whether an unresolved secret/expiry value was found."""
    parsed = urlsplit(value)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    volatile = [
        (name, item)
        for name, item in query
        if name.casefold() in VOLATILE_QUERY_NAMES
        or name.casefold().startswith(("x-amz-", "x-goog-"))
    ]
    path = parsed.path
    course_path = re.match(r"^/courses/(\d+)(/.*)?$", path)
    file_path = re.match(r"^/(?:courses/(\d+)/)?files/(\d+)(/(?:download|preview))?/?$", path)
    stable_canvas = bool(course_path or file_path)
    if file_path:
        found_course = file_path.group(1) or (str(course_id) if course_id is not None else "")
        if found_course:
            mode = file_path.group(3) or ""
            path = f"/courses/{found_course}/files/{file_path.group(2)}{mode}"
            stable_canvas = True
    elif course_path:
        path = f"/courses/{course_path.group(1)}{course_path.group(2) or ''}"
    unresolved = bool(parsed.username or parsed.password or (volatile and not stable_canvas))
    kept = [item for item in query if item not in volatile]
    kept.sort(key=lambda item: (item[0].casefold(), item[0], item[1]))
    scheme = parsed.scheme
    netloc = parsed.netloc
    if stable_canvas:
        scheme = ""
        netloc = ""
    return urlunsplit((scheme, netloc, path, urlencode(kept, doseq=True), parsed.fragment)), unresolved


def canonicalize_page_html(html: str, *, course_id: int | None = None) -> dict[str, Any]:
    """Canonicalize Page URLs before hashing or writing durable output."""
    soup = BeautifulSoup(f"<div data-danvas-root>{html}</div>", "html.parser")
    root = soup.find("div", attrs={"data-danvas-root": True})
    volatile_count = 0
    for tag in soup.find_all(True):
        for name, raw_value in list(tag.attrs.items()):
            if name in NONSEMANTIC_CANVAS_ATTRS or name.startswith("data-mce-"):
                del tag.attrs[name]
                continue
            if not isinstance(raw_value, str):
                continue
            if name not in {"href", "src", "data-api-endpoint", "data-download-url"}:
                continue
            canonical, unresolved = canonicalize_page_url(raw_value, course_id=course_id)
            if unresolved:
                volatile_count += 1
            tag[name] = canonical
    normalized = normalize_html_fragment(inner_html(root))
    return {
        "html": normalized,
        "body_sha256": None if volatile_count else sha256_text(normalized),
        "body_hash_status": "blocked_volatile_url" if volatile_count else "available",
        "volatile_url_count": volatile_count,
        "body_normalizer": BODY_NORMALIZER_VERSION,
    }


def load_page_source(source: Path, *, apply_css: bool = True) -> PageSource:
    if not source.is_file():
        raise SystemExit(f"Page source not found: {source}")
    metadata, body = parse_frontmatter(source.read_text(encoding="utf-8"), source, "Page")
    title = str(metadata.get("title") or "").strip()
    if not title:
        raise SystemExit(f"Page front matter requires a non-empty title: {source}")
    metadata = normalize_page_metadata(metadata, source)
    warnings: list[str] = []
    if source.suffix.lower() in {".html", ".htm"}:
        html = body.strip()
    else:
        html = markdown_lib.markdown(
            body,
            extensions=["extra", "sane_lists", "toc"],
            extension_configs={"toc": {"permalink": False}},
        ).strip()
    html, h1_removed, h1_warning = handle_matching_h1(html, title)
    if h1_warning:
        warnings.append(h1_warning)
    validate_fragment(html, source)
    css_report = None
    css_ref = metadata.get("canvas_css")
    if apply_css and css_ref:
        css_path = (source.parent / str(css_ref)).resolve()
        css_report, html = check_and_inline_css(css_path, html)
        if css_report["errors"]:
            raise SystemExit(format_css_errors(css_path, css_report))
        warnings.extend(css_report["warnings"])
        validate_fragment(html, source)
    canonical = canonicalize_page_html(html)
    if canonical["body_hash_status"] != "available":
        raise SystemExit("Page source contains an unresolved volatile or signed URL.")
    html = canonical["html"]
    anchors, local_links = fragment_anchors(html)
    missing = sorted(set(local_links) - set(anchors))
    if missing:
        raise SystemExit(f"Page has same-page links without rendered targets: {', '.join(missing)}")
    unresolved = unresolved_local_assets(html, source)
    return PageSource(
        source=source,
        metadata=metadata,
        body=body,
        html=html,
        body_sha256=str(canonical["body_sha256"]),
        warnings=warnings,
        unresolved_assets=unresolved,
        anchors=anchors,
        local_links=local_links,
        css_report=css_report,
        matching_h1_removed=h1_removed,
    )


def normalize_page_metadata(metadata: dict[str, Any], source: Path) -> dict[str, Any]:
    allowed = {
        "title", "page_id", "canvas_id", "published", "front_page", "editing_roles",
        "publish_at", "notify_of_update", "canvas_css", "css_policy",
        "lint_suppress",
    }
    unknown = sorted(set(metadata) - allowed)
    if unknown:
        raise SystemExit(f"Unsupported Page front matter in {source}: {', '.join(unknown)}")
    result = {key: normalize_canvas_value(value) for key, value in metadata.items()}
    result.setdefault("published", False)
    result.setdefault("front_page", False)
    result.setdefault("notify_of_update", False)
    if result.get("css_policy", "strict") != "strict":
        raise SystemExit("Only css_policy: strict is supported.")
    return result


def handle_matching_h1(html: str, title: str) -> tuple[str, bool, str | None]:
    soup = BeautifulSoup(f"<div data-danvas-root>{html}</div>", "html.parser")
    root = soup.find("div", attrs={"data-danvas-root": True})
    first = next((node for node in root.children if isinstance(node, Tag)), None) if root else None
    if first and first.name == "h1":
        if normalize_text(first.get_text(" ")) == normalize_text(title):
            first.decompose()
            return inner_html(root), True, None
        return inner_html(root), False, "First H1 does not match the Page title and was preserved."
    return inner_html(root), False, None


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def validate_fragment(html: str, source: Path | None = None) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            raise SystemExit(f"Unsupported or unsafe <{tag.name}> in Page source{source_label(source)}.")
        for name, value in tag.attrs.items():
            lowered = name.lower()
            if lowered.startswith("on"):
                raise SystemExit(f"Event-handler attribute {name!r} is not allowed{source_label(source)}.")
            allowed = lowered in GLOBAL_ATTRS or lowered.startswith("aria-") or lowered in TAG_ATTRS.get(tag.name, set())
            if lowered == "style":
                allowed = True
                errors = validate_inline_style(str(value))
                if errors:
                    raise SystemExit(f"Unsafe inline style{source_label(source)}: {'; '.join(errors)}")
            if not allowed:
                raise SystemExit(f"Attribute {name!r} is not allowed on <{tag.name}>{source_label(source)}.")
            if lowered in URL_ATTRS and unsafe_url(str(value), allow_fragment=True):
                raise SystemExit(f"Unsafe URL in {lowered}{source_label(source)}: {value}")


def source_label(source: Path | None) -> str:
    return f" {source}" if source else ""


def validate_inline_style(style: str) -> list[str]:
    errors: list[str] = []
    for item in tinycss2.parse_declaration_list(style, skip_whitespace=True, skip_comments=True):
        if item.type == "error":
            errors.append(item.message)
        elif item.type != "declaration":
            errors.append(f"unsupported CSS token {item.type}")
        elif item.lower_name not in SAFE_CSS_PROPERTIES:
            errors.append(f"unsupported property {item.lower_name}")
        elif item.important:
            errors.append("!important is not supported")
        elif unsafe_css_value(tinycss2.serialize(item.value).strip()):
            errors.append(f"unsafe value for {item.lower_name}")
    return errors


def unsafe_url(value: str, *, allow_fragment: bool) -> bool:
    stripped = value.strip()
    if allow_fragment and stripped.startswith("#"):
        return False
    parsed = urlparse(stripped)
    return parsed.scheme.casefold() in UNSAFE_SCHEMES


def unsafe_css_value(value: str) -> bool:
    lowered = value.casefold().replace(" ", "")
    return any(token in lowered for token in ("url(", "expression(", "javascript:", "var("))


def unresolved_local_assets(html: str, source: Path) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    result: set[str] = set()
    for tag, attr in (("img", "src"), ("a", "href")):
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "").strip()
            if not value or value.startswith(("#", "/", "mailto:", "tel:")):
                continue
            parsed = urlparse(value)
            if parsed.scheme or parsed.netloc:
                continue
            candidate = parsed.path
            if tag == "img" or Path(candidate).suffix.lower() in LOCAL_ASSET_SUFFIXES:
                result.add(candidate)
    return sorted(result)


def fragment_anchors(html: str) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = sorted({str(node["id"]) for node in soup.find_all(id=True)})
    links = sorted({str(node["href"])[1:] for node in soup.find_all("a", href=True) if str(node["href"]).startswith("#")})
    return anchors, links


def normalize_html_fragment(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        if tag.has_attr("style"):
            styles = parse_style_map(str(tag["style"]))
            tag["style"] = serialize_style_map(styles)
        if tag.has_attr("class"):
            attrs = dict(tag.attrs)
            attrs["class"] = " ".join(sorted(str(value) for value in (tag.get("class") or [])))
            tag.attrs = attrs
        tag.attrs = dict(sorted(tag.attrs.items()))
    decoded = soup.decode(formatter="html").strip()
    return re.sub(r">[ \t]*[\r\n]+[ \t\r\n]*<", "><", decoded)


def parse_style_map(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in tinycss2.parse_declaration_list(style, skip_whitespace=True, skip_comments=True):
        if item.type == "declaration":
            result[item.lower_name] = normalize_css_value(tinycss2.serialize(item.value))
    return result


def normalize_css_value(value: str) -> str:
    """Normalize common Canvas-equivalent CSS serialization without hiding changes."""
    normalized = " ".join(value.casefold().split())
    normalized = re.sub(r"\s*([,:/()])\s*", r"\1", normalized)
    normalized = re.sub(
        r"(?<![\w.-])(?:0+(?:\.0+)?)(?:px|em|rem|%|pt|pc|in|cm|mm|ex|ch|vh|vw|vmin|vmax)\b",
        "0",
        normalized,
    )
    short_hex = re.fullmatch(r"#([0-9a-f])([0-9a-f])([0-9a-f])", normalized)
    if short_hex:
        normalized = "#" + "".join(character * 2 for character in short_hex.groups())
    rgb = re.fullmatch(r"rgb\((\d+),(\d+),(\d+)\)", normalized)
    if rgb and all(0 <= int(component) <= 255 for component in rgb.groups()):
        normalized = "#" + "".join(f"{int(component):02x}" for component in rgb.groups())
    return normalized


def serialize_style_map(styles: dict[str, str]) -> str:
    return "; ".join(f"{name}: {styles[name]}" for name in sorted(styles))


def check_css(css_path: Path, html: str | None = None) -> dict[str, Any]:
    if not css_path.is_file():
        raise SystemExit(f"Canvas CSS sidecar not found: {css_path}")
    rules = tinycss2.parse_stylesheet(css_path.read_text(encoding="utf-8"), skip_whitespace=True, skip_comments=True)
    errors: list[str] = []
    warnings: list[str] = []
    plans: list[dict[str, Any]] = []
    soup = BeautifulSoup(f"<div data-danvas-root>{html or ''}</div>", "html.parser") if html is not None else None
    for rule in rules:
        if rule.type == "error":
            errors.append(f"CSS parse error: {rule.message}")
            continue
        if rule.type == "at-rule":
            errors.append(f"Unsupported at-rule: @{rule.lower_at_keyword}")
            continue
        if rule.type != "qualified-rule":
            errors.append(f"Unsupported CSS rule type: {rule.type}")
            continue
        selector = tinycss2.serialize(rule.prelude).strip()
        if not selector:
            errors.append("Empty CSS selector")
            continue
        if "::" in selector or re.search(r":(?!not\(|is\(|where\()[\w-]+", selector):
            errors.append(f"Pseudo selectors are unsupported: {selector}")
            continue
        declarations: dict[str, str] = {}
        for item in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True):
            if item.type == "error":
                errors.append(f"{selector}: {item.message}")
            elif item.type != "declaration":
                errors.append(f"{selector}: unsupported CSS token {item.type}")
            else:
                value = " ".join(tinycss2.serialize(item.value).split())
                if item.lower_name.startswith("--") or item.lower_name not in SAFE_CSS_PROPERTIES:
                    errors.append(f"{selector}: unsupported property {item.lower_name}")
                elif item.important:
                    errors.append(f"{selector}: !important is unsupported")
                elif unsafe_css_value(value):
                    errors.append(f"{selector}: unsafe or external value for {item.lower_name}")
                else:
                    declarations[item.lower_name] = value
        matches: list[Tag] = []
        if soup is not None:
            try:
                matches = list(soup.select(selector))
            except Exception as exc:
                errors.append(f"Unsupported selector {selector!r}: {exc}")
                continue
            if not matches:
                warnings.append(f"Selector matched no elements: {selector}")
        plans.append({"selector": selector, "matches": len(matches), "declarations": declarations, "_nodes": matches})
    return {
        "profile": COMPATIBILITY_PROFILE,
        "css_path": str(css_path),
        "errors": errors,
        "warnings": warnings,
        "rules": [{key: value for key, value in plan.items() if key != "_nodes"} for plan in plans],
        "_plans": plans,
        "_soup": soup,
    }


def check_and_inline_css(css_path: Path, html: str) -> tuple[dict[str, Any], str]:
    report = check_css(css_path, html)
    soup = report.pop("_soup")
    plans = report.pop("_plans")
    conflicts: set[str] = set()
    for plan in plans:
        for node in plan["_nodes"]:
            styles = parse_style_map(str(node.get("style") or ""))
            for name, value in plan["declarations"].items():
                if name in styles and styles[name] != value:
                    conflicts.add(f"{plan['selector']}: {name} overrides an earlier value")
                styles[name] = value
            if styles:
                node["style"] = serialize_style_map(styles)
    report["warnings"].extend(sorted(conflicts))
    root = soup.find("div", attrs={"data-danvas-root": True})
    return report, inner_html(root)


def inner_html(node: Tag | None) -> str:
    return "" if node is None else "".join(str(child) for child in node.contents).strip()


def format_css_errors(path: Path, report: dict[str, Any]) -> str:
    return f"Canvas CSS failed profile {COMPATIBILITY_PROFILE} ({path}): " + "; ".join(report["errors"])


def page_record(page: Any) -> dict[str, Any]:
    raw = canvas_object_to_dict(page)
    def value(*names: str, default: Any = "") -> Any:
        for name in names:
            found = getattr(page, name, None)
            if found is None:
                found = raw.get(name)
            if found is not None:
                return found
        return default
    return {
        "page_id": value("page_id", "id"),
        "url": value("url"),
        "html_url": value("html_url"),
        "title": value("title"),
        "published": bool(value("published", default=False)),
        "front_page": bool(value("front_page", default=False)),
        "editing_roles": value("editing_roles"),
        "publish_at": value("publish_at"),
        "updated_at": value("updated_at"),
        "body": str(value("body")),
    }


def page_plan(local: PageSource, *, action: str, before: dict[str, Any] | None = None) -> dict[str, Any]:
    changes: dict[str, dict[str, Any]] = {}
    if before is not None:
        expected = {"body": local.html, "published": bool(local.metadata["published"])}
        for field, target in expected.items():
            current = before.get(field)
            if field == "body":
                current = normalize_html_fragment(str(current or ""))
            if current != target:
                changes[field] = {"before": current, "after": target}
    return {
        "status": "blocked" if local.unresolved_assets else ("no_change" if before is not None and not changes else "planned"),
        "action": action,
        "source": str(local.source),
        "title": local.metadata["title"],
        "published": bool(local.metadata["published"]),
        "front_page": bool(local.metadata["front_page"]),
        "editing_roles": local.metadata.get("editing_roles"),
        "publish_at": local.metadata.get("publish_at"),
        "notify_of_update": bool(local.metadata["notify_of_update"]),
        "renderer_version": RENDERER_VERSION,
        "compatibility_profile": COMPATIBILITY_PROFILE,
        "body_sha256": local.body_sha256,
        "matching_h1_removed": local.matching_h1_removed,
        "anchors": local.anchors,
        "same_page_links": local.local_links,
        "unresolved_assets": local.unresolved_assets,
        "warnings": local.warnings,
        "changes": changes,
    }


def create_payload(local: PageSource) -> dict[str, Any]:
    payload = {
        "title": local.metadata["title"],
        "body": local.html,
        "published": bool(local.metadata["published"]),
        "front_page": bool(local.metadata["front_page"]),
        "notify_of_update": bool(local.metadata["notify_of_update"]),
    }
    for field in ("editing_roles", "publish_at"):
        if local.metadata.get(field) not in (None, ""):
            payload[field] = local.metadata[field]
    return payload


def compare_page(
    local: PageSource, canvas_page: dict[str, Any], *, course_id: int | None = None
) -> dict[str, Any]:
    expected = canonicalize_page_html(local.html, course_id=course_id)
    actual = canonicalize_page_html(str(canvas_page.get("body") or ""), course_id=course_id)
    expected_body = expected["html"]
    actual_body = actual["html"]
    differences = []
    if expected["body_hash_status"] != "available" or actual["body_hash_status"] != "available":
        differences.append("volatile_urls")
    elif expected_body != actual_body:
        differences.append("body")
    if str(canvas_page.get("title") or "") != str(local.metadata["title"]):
        differences.append("title")
    if "published" in local.metadata and bool(canvas_page.get("published")) != bool(local.metadata["published"]):
        differences.append("published")
    actual_anchors, actual_links = fragment_anchors(actual_body)
    if local.anchors != actual_anchors or local.local_links != actual_links:
        differences.append("anchors")
    return {
        "status": "matches" if not differences else "mismatch",
        "differences": differences,
        "expected_body_sha256": expected["body_sha256"],
        "actual_body_sha256": actual["body_sha256"],
        "expected_anchors": local.anchors,
        "actual_anchors": actual_anchors,
    }


def resolve_page_identity(local: PageSource, args: Any) -> dict[str, Any]:
    raw = local.metadata.get("page_id", local.metadata.get("canvas_id"))
    frontmatter_id = int(raw) if raw is not None and str(raw).isdigit() else None
    explicit = getattr(args, "page_id", None)
    explicit_id = int(explicit) if explicit is not None and str(explicit).isdigit() else None
    resolved = resolve_source_canvas_id(
        kind="page", source=local.source, explicit_id=explicit_id,
        frontmatter_id=frontmatter_id, project_root=Path(args.project_root),
    )
    if explicit is not None and not str(explicit).isdigit():
        resolved.update({"id": str(explicit), "source": "cli"})
    elif raw is not None and not str(raw).isdigit():
        resolved.update({"id": str(raw), "source": "frontmatter"})
    return resolved


def get_page(course: Any, identity: Any) -> Any:
    if identity in (None, ""):
        raise SystemExit("No Page identity found. Pass --page-id or add page_id/canvas_id front matter.")
    try:
        return course.get_page(identity)
    except ResourceDoesNotExist:
        for page in course.get_pages():
            record = page_record(page)
            if str(identity) in {str(record["page_id"]), str(record["url"])}:
                return course.get_page(record["url"])
        raise


def write_page_report(args: Any, command: str, payload: dict[str, Any], *, status: str | None = None) -> None:
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)), legacy_output=False,
        report_root=Path(args.report_root) if getattr(args, "report_root", None) else None,
        report_dir=Path(args.report_dir) if getattr(args, "report_dir", None) else None,
        report_slug=getattr(args, "report_slug", None), project_root=Path(args.project_root),
    ):
        return
    run = create_report_run(
        command=command, slug=getattr(args, "report_slug", None) or command.replace(" ", "-"),
        project_root=Path(args.project_root),
        report_root=Path(args.report_root) if getattr(args, "report_root", None) else None,
        report_dir=Path(args.report_dir) if getattr(args, "report_dir", None) else None,
        course_id=getattr(args, "course_id", None), input_paths=[Path(args.source)],
    )
    run.write_json("page.json", payload)
    run.finish(status or ("success" if payload.get("status") not in {"blocked", "mismatch", "failed"} else "failed"))
    print(f"Report: {run.path}")


def canvas_page_inventory(course: Any) -> list[dict[str, Any]]:
    course_id = int(getattr(course, "id", 0) or 0)
    records = []
    for summary in course.get_pages():
        record = page_record(summary)
        if record["url"]:
            record = page_record(course.get_page(record["url"]))
        record["html_url"], unsafe_html_url = canonicalize_page_url(
            str(record.get("html_url") or ""), course_id=course_id
        )
        if unsafe_html_url:
            record["html_url"] = ""
        canonical = canonicalize_page_html(record.get("body") or "", course_id=course_id)
        record.update(canonical)
        record["body"] = canonical["html"]
        records.append(record)
    records.sort(
        key=lambda item: (
            normalize_text(str(item.get("title") or "")),
            str(item.get("page_id") or item.get("url") or ""),
        )
    )
    return records


def select_canvas_pages(
    records: list[dict[str, Any]], *, page_id: str | None = None, url: str | None = None
) -> list[dict[str, Any]]:
    if page_id and url:
        raise SystemExit("Use either --page-id or --url, not both.")
    if page_id:
        matches = [row for row in records if str(row.get("page_id")) == str(page_id)]
    elif url:
        matches = [row for row in records if str(row.get("url")) == str(url)]
    else:
        return records
    if not matches:
        raise SystemExit("Canvas Page not found for the requested selector.")
    if len(matches) != 1:
        raise SystemExit("Canvas Page selector is ambiguous.")
    return matches


def page_frontmatter(record: dict[str, Any]) -> dict[str, Any]:
    values = {
        "title": record.get("title") or "",
        "page_id": record.get("page_id"),
        "published": bool(record.get("published")),
        "front_page": bool(record.get("front_page")),
        "editing_roles": record.get("editing_roles"),
        "publish_at": record.get("publish_at"),
    }
    return {key: value for key, value in values.items() if value not in (None, "")}


def render_synced_page_source(record: dict[str, Any], fmt: str) -> dict[str, Any]:
    if record.get("body_hash_status") != "available":
        return {
            "status": "conversion_blocked",
            "reason": "Page contains an unresolved volatile or signed URL.",
            "source": "",
            "body_sha256": None,
            "anchors": [],
        }
    body = str(record.get("body") or "")
    converted = body if fmt == "html" else html_fragment_to_markdown(body)
    frontmatter = yaml.safe_dump(page_frontmatter(record), sort_keys=False, allow_unicode=True).strip()
    source_text = f"---\n{frontmatter}\n---\n\n{converted.strip()}\n"
    suffix = ".html" if fmt == "html" else ".md"
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / f"page{suffix}"
        candidate.write_text(source_text, encoding="utf-8")
        try:
            local = load_page_source(candidate)
        except SystemExit as exc:
            return {
                "status": "conversion_blocked",
                "reason": str(exc),
                "source": "",
                "body_sha256": None,
                "anchors": [],
            }
    if local.unresolved_assets:
        return {
            "status": "conversion_blocked",
            "reason": "Converted source contains unresolved local asset references.",
            "source": "",
            "body_sha256": None,
            "anchors": local.anchors,
        }
    canonical = canonicalize_page_html(local.html)
    remote_anchors, remote_links = fragment_anchors(body)
    if canonical["body_sha256"] != record.get("body_sha256"):
        return {
            "status": "conversion_blocked",
            "reason": "Converted source does not round-trip to the normalized Canvas body.",
            "source": "",
            "body_sha256": canonical["body_sha256"],
            "anchors": local.anchors,
        }
    if local.anchors != remote_anchors or local.local_links != remote_links:
        return {
            "status": "conversion_blocked",
            "reason": "Converted source does not preserve same-page anchors and links.",
            "source": "",
            "body_sha256": canonical["body_sha256"],
            "anchors": local.anchors,
        }
    return {
        "status": "ready",
        "reason": "",
        "source": source_text,
        "body_sha256": canonical["body_sha256"],
        "anchors": local.anchors,
    }


def html_fragment_to_markdown(html: str) -> str:
    soup = BeautifulSoup(f"<div data-danvas-root>{html}</div>", "html.parser")
    root = soup.find("div", attrs={"data-danvas-root": True})
    if root is None:
        return ""
    blocks = [markdown_block(node, 0) for node in root.children if str(node).strip()]
    return "\n\n".join(block.strip() for block in blocks if block.strip()).strip()


def markdown_block(node: Any, depth: int) -> str:
    if not isinstance(node, Tag):
        return markdown_text(str(node)).strip()
    heading = node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
    if node.attrs and not (heading and set(node.attrs) == {"id"}):
        return str(node)
    if node.name == "p":
        return markdown_inline_children(node)
    if heading:
        marker = "#" * int(node.name[1])
        identifier = f" {{#{node.get('id')}}}" if node.get("id") else ""
        return f"{marker} {markdown_inline_children(node)}{identifier}"
    if node.name in {"ul", "ol"}:
        lines = []
        for index, item in enumerate(node.find_all("li", recursive=False), start=1):
            marker = f"{index}." if node.name == "ol" else "-"
            lines.append(f"{'  ' * depth}{marker} {markdown_inline_children(item).strip()}")
        return "\n".join(lines)
    if node.name == "blockquote":
        return "\n".join(f"> {line}" for line in markdown_inline_children(node).splitlines())
    if node.name == "pre":
        return f"```\n{node.get_text().rstrip()}\n```"
    if node.name == "hr":
        return "---"
    return str(node)


def markdown_inline_children(node: Tag) -> str:
    return "".join(markdown_inline(child) for child in node.children).strip()


def markdown_inline(node: Any) -> str:
    if not isinstance(node, Tag):
        return markdown_text(str(node))
    if node.name == "br":
        return "  \n"
    if node.name in {"strong", "b"}:
        return f"**{markdown_inline_children(node)}**"
    if node.name in {"em", "i"}:
        return f"*{markdown_inline_children(node)}*"
    if node.name == "code":
        return f"`{node.get_text()}`"
    if node.name == "a" and set(node.attrs) <= {"href"}:
        return f"[{markdown_inline_children(node)}]({node.get('href') or ''})"
    if node.name in {"ul", "ol"}:
        return "\n" + markdown_block(node, 1)
    return str(node)


def markdown_text(value: str) -> str:
    return re.sub(r"([\\*_[\]<>])", r"\\\1", value)


WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def sanitized_page_slug(value: str) -> tuple[str, bool]:
    normalized = unicodedata.normalize("NFC", value)
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", normalized)
    cleaned = re.sub(r"-+", "-", cleaned).strip().rstrip(". ")
    reserved = cleaned.casefold().split(".", 1)[0] in WINDOWS_RESERVED_NAMES
    return (cleaned or "page"), reserved or not bool(cleaned)


def page_target_plan(
    records: list[dict[str, Any]], output_dir: Path, fmt: str
) -> dict[str, Path]:
    extension = ".html" if fmt == "html" else ".md"
    bases: dict[str, tuple[str, bool]] = {}
    groups: dict[str, list[str]] = {}
    for record in records:
        identity = str(record.get("page_id") or record.get("url") or "")
        base, forced = sanitized_page_slug(str(record.get("url") or ""))
        bases[identity] = (base, forced)
        key = unicodedata.normalize("NFC", f"{base}{extension}").casefold()
        groups.setdefault(key, []).append(identity)
    result = {}
    for identity, (base, forced) in bases.items():
        key = unicodedata.normalize("NFC", f"{base}{extension}").casefold()
        filename = (
            f"{base}--page-{identity}{extension}"
            if forced or len(groups[key]) > 1
            else f"{base}{extension}"
        )
        result[identity] = output_dir / filename
    final_keys: dict[str, str] = {}
    for identity, path in result.items():
        key = unicodedata.normalize("NFC", path.name).casefold().rstrip(". ")
        if key in final_keys:
            raise SystemExit(
                f"Canonical Page targets still collide for {final_keys[key]} and {identity}."
            )
        final_keys[key] = identity
    return result


def command_pages_list(args: Any) -> None:
    course = canvas_from_args(args).get_course(args.course_id)
    records = [page_record(page) for page in course.get_pages()]
    for record in sorted(records, key=lambda item: str(item["title"]).casefold()):
        state = "published" if record["published"] else "draft"
        print(f"{record['page_id']}\t{record['url']}\t{state}\t{record['title']}")


def command_pages_export(args: Any) -> None:
    course = canvas_from_args(args).get_course(args.course_id)
    records = canvas_page_inventory(course)
    selected = select_canvas_pages(
        records, page_id=getattr(args, "page_id", None), url=getattr(args, "url", None)
    )
    fmt = getattr(args, "format", "json")
    if fmt != "json" and len(selected) != 1:
        raise SystemExit("HTML/Markdown Page export requires --page-id or --url.")
    output = Path(args.output)
    if output.exists() and not bool(getattr(args, "overwrite", False)):
        raise SystemExit(f"Output already exists (pass --overwrite): {output}")
    if fmt == "json":
        safe_records = [page_public_record(record, include_body=True) for record in selected]
        write_json(output, {"course_id": args.course_id, "pages": safe_records})
    else:
        rendered = render_synced_page_source(selected[0], fmt)
        if rendered["status"] != "ready":
            raise SystemExit(rendered["reason"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered["source"], encoding="utf-8")
    print(f"Wrote {len(selected)} Page{'s' if len(selected) != 1 else ''} to {output}")


def page_public_record(record: dict[str, Any], *, include_body: bool = False) -> dict[str, Any]:
    excluded = {"html", "_source"}
    if not include_body:
        excluded.add("body")
    return {key: value for key, value in record.items() if key not in excluded}


def command_pages_sync(args: Any) -> None:
    root = Path(args.project_root).resolve()
    course = canvas_from_args(args).get_course(args.course_id)
    inventory = canvas_page_inventory(course)
    selected = select_canvas_pages(
        inventory, page_id=getattr(args, "page_id", None), url=getattr(args, "url", None)
    )
    plan = build_pages_sync_plan(
        inventory=inventory,
        selected=selected,
        output_dir=Path(args.output_dir).resolve(),
        fmt=args.format,
        project_root=root,
        dry_run=bool(args.dry_run),
    )
    if not args.dry_run:
        execute_pages_sync(plan, project_root=root, course_id=args.course_id)
    write_pages_sync_report(args, plan)
    print_pages_sync_summary(plan)
    failures = {"conflict", "conversion_blocked", "source_created_provenance_failed", "error"}
    if any(action["status"] in failures for action in plan["actions"]):
        raise SystemExit(1)


def build_pages_sync_plan(
    *,
    inventory: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    output_dir: Path,
    fmt: str,
    project_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    from danvas.config import load_project_config
    from danvas.sources import scan_sources

    config = load_project_config(project_root)
    local_pages = [
        row for row in scan_sources(project_root, source_config=config.get("sources") or {})
        if row["kind"] == "page"
    ]
    source_map = load_source_map(project_root)
    by_identity: dict[str, list[dict[str, Any]]] = {}
    unbound_by_title: dict[str, list[dict[str, Any]]] = {}
    for local in local_pages:
        entry = find_source_entry(source_map, kind="page", path=local["path"])
        canvas = entry.get("canvas") if isinstance(entry, dict) else {}
        if not isinstance(canvas, dict):
            canvas = {}
        metadata = local.get("source_metadata") or {}
        frontmatter_identity = metadata.get("page_id", metadata.get("canvas_id"))
        map_values = {
            str(value)
            for value in (canvas.get("id"), canvas.get("url"))
            if value not in (None, "")
        }
        if (
            frontmatter_identity not in (None, "")
            and map_values
            and str(frontmatter_identity) not in map_values
        ):
            local["error"] = "Front matter Page identity conflicts with source-map provenance."
        identities = {
            str(value)
            for value in (
                frontmatter_identity,
                canvas.get("id"),
                canvas.get("url"),
            )
            if value not in (None, "")
        }
        local["_source_map_entry"] = entry
        if identities:
            for identity in identities:
                by_identity.setdefault(identity, []).append(local)
        else:
            unbound_by_title.setdefault(normalize_text(str(local.get("title") or "")), []).append(local)
    targets = page_target_plan(inventory, output_dir, fmt)
    actions = []
    for record in selected:
        identity = str(record.get("page_id") or record.get("url") or "")
        target = targets[identity]
        stable_matches = []
        for value in (record.get("page_id"), record.get("url")):
            stable_matches.extend(by_identity.get(str(value), []))
        stable_matches = list({row["path"]: row for row in stable_matches}.values())
        if len(stable_matches) > 1:
            actions.append(sync_action(record, target, "conflict", "Multiple local sources use this Page identity."))
            continue
        if stable_matches:
            local = stable_matches[0]
            if local.get("error"):
                actions.append(sync_action(record, Path(project_root / local["path"]), "conflict", local["error"]))
                continue
            if local.get("_source_map_entry"):
                actions.append(sync_action(record, Path(project_root / local["path"]), "skipped_known_local", "Stable Page provenance already exists."))
                continue
            status, reason = recovery_status(record, local)
            planned = "would_recover_provenance" if dry_run and status == "ready" else (
                "recovered_provenance" if status == "ready" else "conflict"
            )
            action = sync_action(record, Path(project_root / local["path"]), planned, reason)
            action["_recovery_source"] = str(project_root / local["path"])
            actions.append(action)
            continue
        title_matches = unbound_by_title.get(normalize_text(str(record.get("title") or "")), [])
        if len(title_matches) == 1:
            action = sync_action(
                record,
                Path(project_root / title_matches[0]["path"]),
                "skipped_known_local",
                "Unique title-only candidate remains unbound; verify and bind deliberately.",
            )
            action["identity"] = "title_candidate"
            actions.append(action)
            continue
        if len(title_matches) > 1:
            actions.append(
                sync_action(
                    record,
                    target,
                    "conflict",
                    "Multiple unbound local Page sources share this title.",
                )
            )
            continue
        if target.exists():
            target_action = existing_target_action(
                target,
                record,
                source_map=source_map,
                project_root=project_root,
                dry_run=dry_run,
            )
            actions.append(target_action)
            continue
        converted = render_synced_page_source(record, fmt)
        status = "would_create" if dry_run and converted["status"] == "ready" else converted["status"]
        if not dry_run and converted["status"] == "ready":
            status = "ready"
        action = sync_action(record, target, status, converted["reason"])
        action["body_sha256"] = converted["body_sha256"]
        action["anchors"] = converted["anchors"]
        action["_source"] = converted["source"]
        actions.append(action)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "format": fmt,
        "output_dir": str(output_dir),
        "inventory_count": len(inventory),
        "actions": actions,
    }


def sync_action(
    record: dict[str, Any], target: Path, status: str, reason: str
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "page_id": record.get("page_id"),
        "url": record.get("url") or "",
        "title": record.get("title") or "",
        "published": bool(record.get("published")),
        "front_page": bool(record.get("front_page")),
        "target_path": str(target),
        "body_sha256": record.get("body_sha256"),
        "anchors": fragment_anchors(str(record.get("body") or ""))[0],
    }


def recovery_status(record: dict[str, Any], local: dict[str, Any]) -> tuple[str, str]:
    metadata = local.get("source_metadata") or {}
    local_identity = metadata.get("page_id", metadata.get("canvas_id"))
    if str(local_identity) != str(record.get("page_id")):
        return "conflict", "Local Page ID does not match Canvas."
    if str(local.get("title") or "") != str(record.get("title") or ""):
        return "conflict", "Local Page title does not match Canvas."
    artifacts = local.get("artifacts") or {}
    if artifacts.get("body_sha256") != record.get("body_sha256"):
        return "conflict", "Local Page body hash does not match Canvas."
    if artifacts.get("anchors") != fragment_anchors(str(record.get("body") or ""))[0]:
        return "conflict", "Local Page anchors do not match Canvas."
    return "ready", "Stable Page source matches Canvas but provenance is missing."


def existing_target_status(target: Path, record: dict[str, Any]) -> tuple[str, str]:
    try:
        local = load_page_source(target)
    except SystemExit:
        return "skipped_exists", "Target exists and is not a matching Page source."
    identity = local.metadata.get("page_id", local.metadata.get("canvas_id"))
    if identity not in (None, "") and str(identity) != str(record.get("page_id")):
        return "conflict", "Target exists for a different Page identity."
    return "skipped_exists", "Target exists without tracked provenance."


def existing_target_action(
    target: Path,
    record: dict[str, Any],
    *,
    source_map: dict[str, Any],
    project_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    try:
        local_source = load_page_source(target)
    except SystemExit:
        return sync_action(
            record, target, "skipped_exists", "Target exists and is not a matching Page source."
        )
    entry = find_source_entry(
        source_map,
        kind="page",
        path=source_path_key(target, project_root),
    )
    if entry:
        return sync_action(
            record, target, "skipped_known_local", "Stable Page provenance already exists."
        )
    local = {
        "title": local_source.metadata["title"],
        "source_metadata": local_source.metadata,
        "artifacts": {
            "body_sha256": local_source.body_sha256,
            "anchors": local_source.anchors,
        },
    }
    status, reason = recovery_status(record, local)
    action = sync_action(
        record,
        target,
        "would_recover_provenance" if dry_run and status == "ready" else (
            "recovered_provenance" if status == "ready" else "conflict"
        ),
        reason,
    )
    if status == "ready":
        action["_recovery_source"] = str(target)
    return action


def install_source_no_clobber(target: Path, source_text: str) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(source_text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        except OSError as exc:
            raise OSError(
                f"No safe no-clobber installation primitive for {target}: {exc}"
            ) from exc
        return True
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def execute_pages_sync(
    plan: dict[str, Any], *, project_root: Path, course_id: int
) -> None:
    for action in plan["actions"]:
        if action["status"] == "recovered_provenance":
            source = Path(action["_recovery_source"])
            try:
                write_page_sync_provenance(action, source, course_id, project_root)
            except Exception as exc:
                action["status"] = "error"
                action["reason"] = f"Provenance recovery failed: {type(exc).__name__}"
            continue
        if action["status"] != "ready":
            continue
        target = Path(action["target_path"])
        try:
            installed = install_source_no_clobber(target, action["_source"])
        except OSError as exc:
            action["status"] = "error"
            action["reason"] = str(exc)
            continue
        if not installed:
            status, reason = existing_target_status(target, action)
            action["status"] = status
            action["reason"] = reason
            continue
        action["status"] = "created"
        try:
            local = load_page_source(target)
            if local.body_sha256 != action["body_sha256"]:
                raise ValueError("installed source hash changed during local readback")
            write_page_sync_provenance(action, target, course_id, project_root)
        except Exception as exc:
            action["status"] = "source_created_provenance_failed"
            action["reason"] = f"Source created but provenance failed: {type(exc).__name__}"


def write_page_sync_provenance(
    action: dict[str, Any], source: Path, course_id: int, project_root: Path
) -> Path:
    return write_source_map_entry(
        kind="page",
        source=source,
        course_id=course_id,
        canvas={"id": action["page_id"], "url": action["url"], "title": action["title"]},
        command="pages sync",
        fields={
            "title": action["title"],
            "url": action["url"],
            "published": action["published"],
            "front_page": action["front_page"],
        },
        body_sha256=action.get("body_sha256"),
        project_root=project_root,
    )


def pages_sync_report_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: value for key, value in plan.items() if key != "actions"},
        "actions": [
            {key: value for key, value in action.items() if not key.startswith("_")}
            for action in plan["actions"]
        ],
    }


def write_pages_sync_report(args: Any, plan: dict[str, Any]) -> None:
    project_root = Path(args.project_root)
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=False,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=getattr(args, "report_slug", None),
        project_root=project_root,
    ):
        return
    run = create_report_run(
        command="pages sync",
        slug=getattr(args, "report_slug", None) or "pages-sync",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=args.course_id,
        input_paths=[Path(plan["output_dir"])],
    )
    payload = pages_sync_report_payload(plan)
    run.write_json("pages-sync.json", payload)
    run.write_text("pages-sync.md", render_pages_sync_markdown(payload))
    failures = {"conflict", "conversion_blocked", "source_created_provenance_failed", "error"}
    status = "failed" if any(action["status"] in failures for action in plan["actions"]) else "success"
    run.finish(status)
    print(f"Report: {run.path}")


def render_pages_sync_markdown(plan: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    for action in plan["actions"]:
        counts[action["status"]] = counts.get(action["status"], 0) + 1
    lines = [
        "# Pages Sync",
        "",
        f"- Dry run: `{plan['dry_run']}`",
        f"- Format: `{plan['format']}`",
        f"- Inventory count: `{plan['inventory_count']}`",
        "",
        "## Summary",
        "",
    ]
    lines.extend(f"- `{status}`: `{count}`" for status, count in sorted(counts.items()))
    lines.extend(
        [
            "",
            "## Actions",
            "",
            "| Status | Page ID | Title | Target | Reason |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for action in plan["actions"]:
        title = str(action["title"]).replace("|", "\\|")
        reason = str(action["reason"]).replace("|", "\\|")
        lines.append(
            f"| {action['status']} | {action['page_id']} | {title} | "
            f"`{action['target_path']}` | {reason} |"
        )
    return "\n".join(lines) + "\n"


def print_pages_sync_summary(plan: dict[str, Any]) -> None:
    print(f"Pages sync ({'dry run' if plan['dry_run'] else 'local write'}):")
    for action in plan["actions"]:
        print(f"  {action['status']}: {action['title']} -> {action['target_path']}")


def command_pages_render(args: Any) -> None:
    local = load_page_source(Path(args.source))
    if local.unresolved_assets:
        raise SystemExit(f"Unresolved local Page assets: {', '.join(local.unresolved_assets)}")
    if str(args.output) == "-":
        print(local.html)
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(local.html + "\n", encoding="utf-8")
        print(f"Rendered Page fragment to {output}")


def command_pages_css_check(args: Any) -> None:
    css_path = Path(args.css)
    if getattr(args, "source", None):
        local = load_page_source(Path(args.source), apply_css=False)
        report, final_html = check_and_inline_css(css_path, local.html)
        report["final_body_sha256"] = sha256_text(normalize_html_fragment(final_html))
    else:
        report = check_css(css_path)
        report.pop("_plans", None)
        report.pop("_soup", None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["errors"]:
        raise SystemExit(1)


def command_pages_create(args: Any) -> None:
    local = load_page_source(Path(args.source))
    plan = page_plan(local, action="create")
    if args.dry_run or plan["status"] == "blocked":
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        write_page_report(args, "pages create", plan)
        if plan["status"] == "blocked":
            raise SystemExit(1)
        return
    print_mutation_banner("create Page", {"course": args.course_id, "title": local.metadata["title"], "published": local.metadata["published"], "source": local.source})
    course = canvas_from_args(args).get_course(args.course_id)
    created = course.create_page(create_payload(local))
    created_record = page_record(created)
    readback = page_record(course.get_page(created_record["url"]))
    verification = compare_page(local, readback, course_id=args.course_id)
    result = {**plan, "status": verification["status"], "canvas": {key: readback.get(key) for key in ("page_id", "url", "title", "published", "front_page")}, "verification": verification}
    if verification["status"] == "matches":
        write_source_map_entry(
            kind="page", source=local.source, course_id=args.course_id,
            canvas={"id": readback["page_id"], "url": readback["url"], "title": readback["title"]},
            command="pages create", fields={"title": readback["title"], "published": readback["published"], "front_page": readback["front_page"], "renderer_version": RENDERER_VERSION, "compatibility_profile": COMPATIBILITY_PROFILE},
            body_sha256=local.body_sha256, project_root=Path(args.project_root),
        )
    write_page_report(args, "pages create", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if verification["status"] != "matches":
        raise SystemExit(1)


def command_pages_update(args: Any) -> None:
    local = load_page_source(Path(args.source))
    resolved = resolve_page_identity(local, args)
    course = canvas_from_args(args).get_course(args.course_id)
    page = get_page(course, resolved["id"])
    before = page_record(page)
    if before["title"] != local.metadata["title"]:
        raise SystemExit("Page update refuses title/slug changes; local title does not match Canvas.")
    if bool(before["front_page"]) != bool(local.metadata["front_page"]):
        raise SystemExit("Page update refuses front-page changes.")
    plan = page_plan(local, action="update", before=before)
    plan["canvas_id"] = before["page_id"]
    plan["canvas_url"] = before["url"]
    if args.dry_run or plan["status"] in {"blocked", "no_change"}:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        write_page_report(args, "pages update", plan)
        if plan["status"] == "blocked":
            raise SystemExit(1)
        return
    print_mutation_banner("update Page body/publication", {"course": args.course_id, "page": before["page_id"], "title": before["title"], "published": local.metadata["published"], "source": local.source})
    page.edit(wiki_page={"body": local.html, "published": bool(local.metadata["published"]), "notify_of_update": bool(local.metadata["notify_of_update"])})
    readback = page_record(course.get_page(before["url"]))
    verification = compare_page(local, readback, course_id=args.course_id)
    result = {**plan, "status": verification["status"], "verification": verification}
    if verification["status"] == "matches":
        write_source_map_entry(
            kind="page", source=local.source, course_id=args.course_id,
            canvas={"id": readback["page_id"], "url": readback["url"], "title": readback["title"]},
            command="pages update", fields={"title": readback["title"], "published": readback["published"], "front_page": readback["front_page"], "renderer_version": RENDERER_VERSION, "compatibility_profile": COMPATIBILITY_PROFILE},
            body_sha256=local.body_sha256, project_root=Path(args.project_root),
        )
    write_page_report(args, "pages update", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if verification["status"] != "matches":
        raise SystemExit(1)


def command_pages_verify(args: Any) -> None:
    local = load_page_source(Path(args.source))
    resolved = resolve_page_identity(local, args)
    course = canvas_from_args(args).get_course(args.course_id)
    canvas_page = page_record(get_page(course, resolved["id"]))
    verification = compare_page(local, canvas_page, course_id=args.course_id)
    result = {"status": verification["status"], "source": str(local.source), "canvas_id": canvas_page["page_id"], "canvas_url": canvas_page["url"], "renderer_version": RENDERER_VERSION, "compatibility_profile": COMPATIBILITY_PROFILE, "verification": verification}
    write_page_report(args, "pages verify", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if verification["status"] != "matches":
        raise SystemExit(1)
