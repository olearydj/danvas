"""Canvas Page authoring, rendering, and bounded write workflows."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import markdown as markdown_lib
import tinycss2
from bs4 import BeautifulSoup, Comment, Tag
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.auth import canvas_from_args
from danvas.frontmatter import normalize_canvas_value, parse_frontmatter
from danvas.reports import create_report_run, should_write_report_run
from danvas.source_map import resolve_source_canvas_id, write_source_map_entry
from danvas.utils import canvas_object_to_dict, print_mutation_banner, write_json

RENDERER_VERSION = "pages-markdown-v1"
COMPATIBILITY_PROFILE = "canvas-page-v1"

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
    html = normalize_html_fragment(html)
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
        body_sha256=sha256_text(html),
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
    return soup.decode(formatter="html").strip()


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


def compare_page(local: PageSource, canvas_page: dict[str, Any]) -> dict[str, Any]:
    expected_body = normalize_html_fragment(local.html)
    actual_body = normalize_html_fragment(str(canvas_page.get("body") or ""))
    differences = []
    if expected_body != actual_body:
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
        "expected_body_sha256": sha256_text(expected_body),
        "actual_body_sha256": sha256_text(actual_body),
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


def command_pages_list(args: Any) -> None:
    course = canvas_from_args(args).get_course(args.course_id)
    records = [page_record(page) for page in course.get_pages()]
    for record in sorted(records, key=lambda item: str(item["title"]).casefold()):
        state = "published" if record["published"] else "draft"
        print(f"{record['page_id']}\t{record['url']}\t{state}\t{record['title']}")


def command_pages_export(args: Any) -> None:
    course = canvas_from_args(args).get_course(args.course_id)
    records = []
    for summary in course.get_pages():
        record = page_record(summary)
        with suppress(ResourceDoesNotExist):
            record = page_record(course.get_page(record["url"]))
        records.append(record)
    output = Path(args.output)
    if output.exists() and not bool(getattr(args, "overwrite", False)):
        raise SystemExit(f"Output already exists (pass --overwrite): {output}")
    write_json(output, {"course_id": args.course_id, "pages": records})
    print(f"Wrote {len(records)} Pages to {output}")


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
    verification = compare_page(local, readback)
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
    verification = compare_page(local, readback)
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
    verification = compare_page(local, canvas_page)
    result = {"status": verification["status"], "source": str(local.source), "canvas_id": canvas_page["page_id"], "canvas_url": canvas_page["url"], "renderer_version": RENDERER_VERSION, "compatibility_profile": COMPATIBILITY_PROFILE, "verification": verification}
    write_page_report(args, "pages verify", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if verification["status"] != "matches":
        raise SystemExit(1)
