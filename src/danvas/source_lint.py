"""Local-only validation for Canvas-facing authored sources."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from danvas.frontmatter import parse_frontmatter
from danvas.pages import load_page_source
from danvas.source_map import find_source_entry, load_source_map, source_path_key
from danvas.sources import DEFAULT_SOURCE_PATTERNS, source_paths
from danvas.utils import write_json

LintKind = Literal["assignment", "announcement", "discussion", "page"]
SEVERITY_ORDER = {"warning": 1, "error": 2}
DATE_FIELDS = {"due_at", "unlock_at", "lock_at", "delayed_post_at", "publish_at"}
ASSIGNMENT_ONLY = {
    "allowed_attempts", "allowed_extensions", "assignment_group", "assignment_group_id",
    "grading_type", "group_category_id", "peer_reviews", "points_possible", "submission_types",
}
URL_RE = re.compile(r"!?\[[^]]*]\(([^)\s]+)(?:\s+[^)]*)?\)")
HTML_URL_RE = re.compile(r"\b(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]", re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
POINTS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s+points?\b", re.I)


def finding(
    rule: str,
    severity: str,
    path: Path,
    message: str,
    remediation: str,
    *,
    line: int | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule,
        "severity": severity,
        "path": str(path),
        "line": line,
        "message": message,
        "remediation": remediation,
    }


def line_for(text: str, needle: str) -> int | None:
    index = text.find(needle)
    return None if index < 0 else text.count("\n", 0, index) + 1


def infer_kind(path: Path, metadata: dict[str, Any], explicit: str | None) -> LintKind:
    if explicit == "assignment":
        return "assignment"
    if explicit == "announcement":
        return "announcement"
    if explicit == "discussion":
        return "discussion"
    if explicit == "page":
        return "page"
    parts = {part.casefold() for part in path.parts}
    if "pages" in parts or path.suffix.lower() in {".html", ".htm"} or "canvas_css" in metadata:
        return "page"
    if "announcements" in parts or metadata.get("is_announcement"):
        return "announcement"
    if "discussions" in parts or metadata.get("discussion_type"):
        return "discussion"
    if set(metadata) & ASSIGNMENT_ONLY or "assignments" in parts or "assignment" in path.stem:
        return "assignment"
    raise ValueError("Could not infer source kind; pass --kind.")


def source_suppressions(metadata: dict[str, Any], path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    raw = metadata.get("lint_suppress")
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, [finding("suppression-invalid", "error", path, "lint_suppress must be a rule-to-reason mapping.", "Use lint_suppress: {rule-id: reason}.")]
    result = {}
    invalid = []
    for rule, reason in raw.items():
        if not isinstance(reason, str) or not reason.strip():
            invalid.append(finding("suppression-invalid", "error", path, f"Suppression {rule!s} has no reason.", "Give every suppressed rule a non-empty reason."))
        else:
            result[str(rule)] = reason.strip()
    return result, invalid


def lint_source(path: Path, *, kind: str | None, project_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {"path": str(path), "kind": kind or "unknown", "findings": [finding("source-read", "error", path, f"Cannot read source: {type(exc).__name__}.", "Check that the path exists and is readable.")]}
    try:
        metadata, body = parse_frontmatter(text, path, "Canvas")
    except SystemExit as exc:
        return {"path": str(path), "kind": kind or "unknown", "findings": [finding("frontmatter-invalid", "error", path, str(exc), "Add valid YAML or TOML front matter at the start of the file.", line=1)]}
    try:
        resolved_kind = infer_kind(path, metadata, kind)
    except ValueError as exc:
        return {"path": str(path), "kind": "unknown", "findings": [finding("kind-unknown", "error", path, str(exc), "Pass --kind assignment, announcement, discussion, or page.")]}
    suppressions, suppression_findings = source_suppressions(metadata, path)
    findings.extend(suppression_findings)
    title = str(metadata.get("title") or metadata.get("name") or "").strip()
    if not title:
        findings.append(finding("title-required", "error", path, "Source front matter has no title.", "Add a non-empty title field."))
    findings.extend(lint_dates(path, text, metadata))
    findings.extend(lint_structure(path, body, title))
    findings.extend(lint_links(path, body))
    findings.extend(lint_point_total(path, body, metadata))
    if resolved_kind == "assignment":
        findings.extend(lint_assignment(path, metadata))
    elif resolved_kind == "announcement":
        findings.extend(lint_announcement(path, metadata))
    elif resolved_kind == "discussion":
        findings.extend(lint_discussion(path, body))
    else:
        findings.extend(lint_page(path, metadata))
    findings.extend(lint_provenance(path, resolved_kind, metadata, project_root))
    kept = [item for item in findings if item["rule_id"] not in suppressions]
    suppressed = sorted({item["rule_id"] for item in findings if item["rule_id"] in suppressions})
    kept.sort(key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["rule_id"], item["line"] or 0))
    return {"path": str(path), "kind": resolved_kind, "findings": kept, "suppressed_rules": suppressed}


def lint_dates(path: Path, text: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    parsed: dict[str, datetime] = {}
    for field in DATE_FIELDS & set(metadata):
        value = metadata.get(field)
        if value in (None, ""):
            continue
        raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            findings.append(finding("date-invalid", "error", path, f"{field} is not a valid ISO 8601 date.", "Use an ISO 8601 timestamp with a timezone offset.", line=line_for(text, field)))
            continue
        if date.tzinfo is None or date.utcoffset() is None:
            findings.append(finding("date-timezone", "error", path, f"{field} has no timezone offset.", "Add Z or an explicit offset such as -05:00.", line=line_for(text, field)))
        parsed[field] = date
    for earlier, later in (("unlock_at", "due_at"), ("due_at", "lock_at"), ("unlock_at", "lock_at")):
        if earlier in parsed and later in parsed:
            try:
                invalid = parsed[earlier] > parsed[later]
            except TypeError:
                invalid = False
            if invalid:
                findings.append(finding("date-order", "error", path, f"{earlier} occurs after {later}.", "Put unlock, due, and lock dates in chronological order."))
    return findings


def clean_heading(value: str) -> str:
    return re.sub(r"\s*\{#[^}]+}\s*$", "", value).strip().strip("#").strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def lint_structure(path: Path, body: str, title: str) -> list[dict[str, Any]]:
    findings = []
    headings = [(match.group(1), clean_heading(match.group(2)), match.start()) for match in HEADING_RE.finditer(body)]
    h1s = [item for item in headings if len(item[0]) == 1]
    if title and h1s and h1s[0][1].casefold() == title.casefold():
        findings.append(finding("title-duplicate-h1", "warning", path, "The body repeats the front-matter title as H1.", "Remove the duplicate H1 unless the renderer explicitly handles it.", line=body.count("\n", 0, h1s[0][2]) + 1))
    seen: set[str] = set()
    for _marks, heading, offset in headings:
        identifier_match = re.search(r"\{#([^}]+)}\s*$", body[offset : body.find("\n", offset) if "\n" in body[offset:] else len(body)])
        identifier = identifier_match.group(1) if identifier_match else slug(heading)
        if identifier in seen:
            findings.append(finding("heading-duplicate-id", "warning", path, f"Heading ID {identifier!r} is duplicated.", "Give repeated headings explicit unique IDs.", line=body.count("\n", 0, offset) + 1))
        seen.add(identifier)
    soup = BeautifulSoup(body, "html.parser")
    html_ids: set[str] = set()
    for node in soup.find_all(id=True):
        identifier = str(node["id"])
        if identifier in html_ids:
            findings.append(finding("html-duplicate-id", "error", path, f"HTML id {identifier!r} is duplicated.", "Use a unique id for every element."))
        html_ids.add(identifier)
    return findings


def lint_links(path: Path, body: str) -> list[dict[str, Any]]:
    findings = []
    values = URL_RE.findall(body) + HTML_URL_RE.findall(body)
    headings = {slug(clean_heading(match.group(2))) for match in HEADING_RE.finditer(body)}
    explicit_ids = set(re.findall(r"\{#([^}]+)}", body)) | {str(node["id"]) for node in BeautifulSoup(body, "html.parser").find_all(id=True)}
    anchors = headings | explicit_ids
    for value in values:
        parsed = urlparse(value)
        if parsed.scheme.casefold() in {"javascript", "vbscript", "data"}:
            findings.append(finding("url-unsafe", "error", path, "Source contains an unsafe URL scheme.", "Use an https, mailto, tel, fragment, or local relative link.", line=line_for(body, value)))
        elif value.startswith("#") and value[1:] not in anchors:
            findings.append(finding("link-fragment-missing", "error", path, f"Fragment target #{value[1:]} does not exist.", "Add the target heading/id or correct the link.", line=line_for(body, value)))
        elif not parsed.scheme and not parsed.netloc and not value.startswith(("#", "/")):
            target = (path.parent / parsed.path).resolve()
            if not target.exists():
                findings.append(finding("asset-missing", "error", path, f"Relative target {parsed.path!r} does not exist.", "Add the local file or correct the relative path.", line=line_for(body, value)))
    return findings


def lint_point_total(path: Path, body: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("points_possible")
    if raw is None:
        return []
    try:
        expected = float(raw)
    except (TypeError, ValueError):
        return [finding("points-invalid", "error", path, "points_possible is not numeric.", "Use an integer or decimal number.")]
    mentioned = {float(value) for value in POINTS_RE.findall(body)}
    if mentioned and expected not in mentioned:
        return [finding("points-prose-mismatch", "warning", path, "Recognizable prose point totals do not include points_possible.", "Review the authored point totals and metadata.")]
    return []


def lint_assignment(path: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    if "points_possible" not in metadata:
        findings.append(finding("assignment-points-required", "error", path, "Assignment has no points_possible.", "Add points_possible to front matter."))
    submission_types = metadata.get("submission_types")
    if submission_types == "none" and metadata.get("allowed_extensions"):
        findings.append(finding("assignment-submission-conflict", "error", path, "allowed_extensions conflicts with submission_types: none.", "Remove allowed_extensions or enable online_upload."))
    if isinstance(submission_types, list) and "none" in submission_types and len(submission_types) > 1:
        findings.append(finding("assignment-submission-conflict", "error", path, "submission_types combines none with active submission types.", "Use none alone or remove it."))
    return findings


def lint_announcement(path: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    fields = sorted(set(metadata) & ASSIGNMENT_ONLY)
    return [] if not fields else [finding("announcement-assignment-metadata", "error", path, f"Announcement uses assignment-only fields: {', '.join(fields)}.", "Remove assignment-only metadata from the announcement.")]


def lint_discussion(path: Path, body: str) -> list[dict[str, Any]]:
    prompts = [clean_heading(match.group(2)) for match in HEADING_RE.finditer(body) if "prompt" in match.group(2).casefold()]
    findings = []
    if len(prompts) > 3:
        findings.append(finding("discussion-prompts-excessive", "warning", path, "Discussion contains more than three prompt headings.", "Consolidate the prompt structure if the repetition is accidental."))
    seeded = re.findall(r"^#{1,6}\s+seed(?:ed)?\b", body, re.I | re.M)
    if len(seeded) > 1:
        findings.append(finding("discussion-seeded-repeated", "warning", path, "Discussion contains repeated seeded sections.", "Use one clearly delimited seeded section."))
    return findings


def lint_page(path: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    if metadata.get("front_page") is True and metadata.get("published") is False:
        findings.append(finding("page-front-page-draft", "error", path, "A front Page cannot remain an unpublished draft.", "Publish the Page or set front_page: false."))
    try:
        load_page_source(path)
    except SystemExit as exc:
        findings.append(finding("page-profile", "error", path, str(exc), "Use only Page profile V1 markup, metadata, URLs, and CSS."))
    return findings


def lint_provenance(path: Path, kind: str, metadata: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    raw_id = metadata.get("page_id", metadata.get("canvas_id", metadata.get("assignment_id")))
    try:
        payload = load_source_map(project_root)
    except SystemExit:
        return [finding("provenance-invalid", "error", path, "The local source map is invalid.", "Repair or regenerate .danvas/source-map.json.")]
    entry = find_source_entry(payload, kind=kind, path=source_path_key(path, project_root))
    if raw_id is not None and entry is None:
        return [finding("provenance-missing", "warning", path, "Source declares a Canvas ID but has no local source-map entry.", "Run a verified create/update or confirm that embedded identity is intentional.")]
    if entry and raw_id is not None:
        mapped = (entry.get("canvas") or {}).get("id")
        if mapped is not None and str(mapped) != str(raw_id):
            return [finding("provenance-conflict", "error", path, "Front matter and source-map Canvas IDs conflict.", "Resolve the identity conflict before a write.")]
    return []


def discover_lint_paths(paths: list[Path], *, kind: str | None, project_root: Path) -> list[Path]:
    if paths:
        result = []
        for path in paths:
            raw = str(path)
            if any(char in raw for char in "*?["):
                result.extend(sorted(project_root.glob(raw)))
            else:
                candidate = path if path.is_absolute() else project_root / path
                if candidate.is_dir():
                    result.extend(sorted(item for item in candidate.rglob("*") if item.suffix.lower() in {".md", ".html", ".htm"}))
                else:
                    result.append(candidate)
        return sorted({item.resolve() for item in result if item.is_file()})
    kinds = [kind] if kind else ["assignment", "announcement", "discussion", "page"]
    result = []
    for item_kind in kinds:
        pattern = DEFAULT_SOURCE_PATTERNS.get(
            item_kind, ["content/pages/*.md", "content/pages/*.html", "content/pages/*.htm"]
        )
        result.extend(source_paths(project_root, pattern, []))
    return sorted(set(result))


def command_sources_lint(args: Any) -> None:
    root = Path(args.project_root).resolve()
    paths = discover_lint_paths([Path(item) for item in args.paths], kind=args.kind, project_root=root)
    if not paths:
        raise SystemExit("No Canvas-facing source files matched.")
    records = [lint_source(path, kind=args.kind, project_root=root) for path in paths]
    counts = {"errors": 0, "warnings": 0, "suppressed": 0}
    for record in records:
        for item in record["findings"]:
            counts["errors" if item["severity"] == "error" else "warnings"] += 1
        counts["suppressed"] += len(record.get("suppressed_rules") or [])
    payload = {"project_root": str(root), "counts": counts, "sources": records}
    if args.format == "json":
        if args.output:
            write_json(Path(args.output), payload)
            print(f"Wrote lint results to {args.output}")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for record in records:
            for item in record["findings"]:
                location = f":{item['line']}" if item["line"] else ""
                print(f"{item['severity'].upper()} {item['rule_id']} {item['path']}{location}: {item['message']} {item['remediation']}")
        print(f"Checked {len(records)} source(s): {counts['errors']} error(s), {counts['warnings']} warning(s), {counts['suppressed']} suppressed rule(s).")
    if counts["errors"] or (args.fail_on == "warning" and counts["warnings"]):
        raise SystemExit(1)
