"""Read-only course status report comparing the snapshot to local sources."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from danvas.config import (
    COURSE_SNAPSHOT_NAME,
    find_config_dir,
    load_project_config,
)
from danvas.files import local_files, status_for
from danvas.overrides import (
    assignment_base_compare_row,
    compare_local_overrides,
    load_local_override_file,
)
from danvas.reports import create_report_run
from danvas.source_map import find_source_entry, load_source_map
from danvas.sources import scan_sources
from danvas.utils import write_json

DEFAULT_MAX_SNAPSHOT_AGE_HOURS = 24.0
DATE_FIELDS = {"due_at", "unlock_at", "lock_at", "posted_at", "delayed_post_at"}
FILE_CLASSIFICATIONS = {
    "present_by_name_and_size": "exact",
    "present_by_name": "filename-only match",
    "ambiguous_name_match": "filename-only match",
    "missing": "Canvas-only",
}


def command_status(args: Any) -> None:
    config_dir = find_config_dir(Path(args.project_root).resolve())
    if not config_dir:
        raise SystemExit(
            "No .danvas project found. Run `danvas init COURSE_ID` from the course project."
        )
    snapshot_path = config_dir / COURSE_SNAPSHOT_NAME
    if not snapshot_path.is_file():
        raise SystemExit(f"Course snapshot not found: {snapshot_path}. Run `danvas refresh`.")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if int(snapshot.get("schema_version") or 1) < 3:
        raise SystemExit(
            "Course snapshot predates the current format. Run `danvas refresh` first."
        )
    config = load_project_config(config_dir)
    max_age_hours = resolve_max_age_hours(args.max_age_hours, config_dir)
    payload = build_status(
        snapshot,
        config_dir.parent,
        max_age_hours=max_age_hours,
        source_config=config.get("sources") or {},
    )
    payload["snapshot"]["path"] = str(snapshot_path)
    for line in render_status_lines(payload):
        print(line)
    if args.output:
        write_json(Path(args.output), payload)
        print(f"Wrote {args.output}")
    if args.report_md:
        report = Path(args.report_md)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_status_markdown(payload), encoding="utf-8")
        print(f"Wrote {args.report_md}")
    report_root = getattr(args, "report_root", None)
    report_dir = getattr(args, "report_dir", None)
    report_slug = getattr(args, "report_slug", None)
    if report_root or report_dir or report_slug:
        report_run = create_report_run(
            command="status",
            slug=report_slug or "status",
            project_root=config_dir.parent,
            report_root=Path(report_root) if report_root else None,
            report_dir=Path(report_dir) if report_dir else None,
            course_id=payload["course"]["id"],
            snapshot_timestamp=str(payload["snapshot"].get("generated_at") or ""),
            private_data=False,
        )
        report_run.manifest["snapshot_path"] = str(snapshot_path)
        report_run.manifest["snapshot_stale"] = payload["snapshot"]["stale"]
        try:
            json_path = report_run.write_json("status.json", payload)
            md_path = report_run.write_text("status.md", render_status_markdown(payload))
            manifest_path = report_run.finish()
            print(f"Wrote {json_path}")
            print(f"Wrote {md_path}")
            print(f"Wrote {manifest_path}")
            print(f"Report directory: {report_run.path}")
        except Exception as exc:
            report_run.finish("failed", error=str(exc))
            raise


def resolve_max_age_hours(explicit: float | None, config_dir: Path) -> float:
    if explicit is not None:
        return float(explicit)
    config = load_project_config(config_dir)
    value = (config.get("status") or {}).get("max_snapshot_age_hours")
    return float(value) if value is not None else DEFAULT_MAX_SNAPSHOT_AGE_HOURS


def build_status(
    snapshot: dict[str, Any],
    root: Path,
    *,
    max_age_hours: float = DEFAULT_MAX_SNAPSHOT_AGE_HOURS,
    now: dt.datetime | None = None,
    source_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = scan_sources(root, source_config=source_config)
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sources:
        by_kind[record["kind"]].append(record)

    snapshot_version = int(snapshot.get("schema_version") or 1)
    pages_available = snapshot_version >= 4
    sections = {
        "assignments": compare_assignments(by_kind["assignment"], snapshot, root),
        "announcements": compare_titled(
            by_kind["announcement"], snapshot.get("announcements") or []
        ),
        "discussions": compare_discussions(by_kind["discussion"], snapshot),
        "quizzes": compare_quizzes(by_kind["quiz"], snapshot.get("quizzes") or []),
        "files": compare_files(snapshot.get("files") or [], root),
        "pages": (
            compare_pages(by_kind["page"], snapshot.get("pages") or [], root)
            if pages_available
            else []
        ),
    }
    add_next_actions(sections)
    summary: Counter[str] = Counter()
    for items in sections.values():
        summary.update(item["classification"] for item in items)

    age_hours = snapshot_age_hours(str(snapshot.get("generated_at") or ""), now)
    stale = age_hours is not None and age_hours > max_age_hours
    if stale:
        summary["snapshot stale"] = 1

    categories = snapshot.get("group_categories") or []
    course = snapshot.get("course") or {}
    return {
        "course": {"id": course.get("id"), "name": course.get("name") or ""},
        "snapshot": {
            "generated_at": snapshot.get("generated_at"),
            "schema_version": snapshot.get("schema_version"),
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "max_age_hours": max_age_hours,
            "stale": stale,
            "pages_available": pages_available,
        },
        "summary": dict(summary),
        "sections": sections,
        "group_categories": [
            {
                "name": category.get("name") or "",
                "group_count": category.get("group_count"),
                "member_count": category.get("member_count"),
            }
            for category in categories
        ],
        "notes": [
            "Quiz comparison covers titles only; question-body comparison is unavailable "
            "from the snapshot.",
            "Local files not present in Canvas are not reported.",
        ]
        + (
            []
            if pages_available
            else ["Pages unavailable from this schema-3 snapshot. Run `danvas refresh`."]
        ),
    }


def compare_pages(
    local_records: list[dict[str, Any]], canvas_rows: list[dict[str, Any]], root: Path
) -> list[dict[str, Any]]:
    by_identity: dict[str, dict[str, Any]] = {}
    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canvas_rows:
        for value in (row.get("page_id"), row.get("url")):
            if value not in (None, ""):
                by_identity[str(value)] = row
        by_title[normalize_title(str(row.get("title") or ""))].append(row)
    try:
        source_map = load_source_map(root)
        source_map_error = ""
    except SystemExit as exc:
        source_map = {"sources": []}
        source_map_error = str(exc)
    matched: set[int] = set()
    items = []
    for record in local_records:
        item = {
            "classification": "",
            "title": record.get("title") or record.get("path") or "",
            "local_path": record.get("path") or "",
            "canvas_id": None,
            "canvas_url": "",
            "details": [],
        }
        if record.get("error"):
            item["classification"] = "unsupported comparison"
            item["details"].append(record["error"])
            items.append(item)
            continue
        entry = find_source_entry(source_map, kind="page", path=str(record["path"]))
        canvas_entry = entry.get("canvas") if isinstance(entry, dict) else {}
        if not isinstance(canvas_entry, dict):
            canvas_entry = {}
        metadata = record.get("source_metadata") or {}
        frontmatter = metadata.get("page_id", metadata.get("canvas_id"))
        map_identity = canvas_entry.get("id", canvas_entry.get("url"))
        if source_map_error and frontmatter in (None, ""):
            item["classification"] = "unsupported comparison"
            item["details"].append(source_map_error)
            items.append(item)
            continue
        if frontmatter not in (None, "") and map_identity not in (None, ""):
            map_values = {str(canvas_entry.get("id") or ""), str(canvas_entry.get("url") or "")}
            if str(frontmatter) not in map_values:
                item["classification"] = "unsupported comparison"
                item["details"].append(
                    f"front matter identity {frontmatter!r} conflicts with source-map identity"
                )
                items.append(item)
                continue
        identity = frontmatter if frontmatter not in (None, "") else map_identity
        row = by_identity.get(str(identity)) if identity not in (None, "") else None
        if identity not in (None, "") and row is None:
            item["classification"] = "local-only"
            item["details"].append(f"stable Page identity {identity!r} not found in snapshot")
            items.append(item)
            continue
        title_candidate = False
        if row is None:
            candidates = by_title.get(normalize_title(str(record.get("title") or "")), [])
            if len(candidates) == 1:
                row = candidates[0]
                title_candidate = True
            elif len(candidates) > 1:
                item["classification"] = "unsupported comparison"
                item["details"].append(f"{len(candidates)} Canvas Pages share this title")
                matched.update(id(candidate) for candidate in candidates)
                items.append(item)
                continue
            else:
                item["classification"] = "local-only"
                items.append(item)
                continue
        matched.add(id(row))
        item["canvas_id"] = row.get("page_id")
        item["canvas_url"] = row.get("url") or ""
        metadata_diffs = field_diffs(record.get("metadata") or {}, row)
        local_hash = (record.get("artifacts") or {}).get("body_sha256")
        canvas_hash = row.get("body_sha256")
        body_supported = bool(local_hash and canvas_hash) and row.get("body_hash_status") == "available"
        body_diff = body_supported and local_hash != canvas_hash
        if title_candidate:
            item["classification"] = "probable match, unbound"
            item["details"].extend(metadata_diffs)
            if body_diff:
                item["details"].append("body hash differs from title candidate")
        elif not body_supported:
            item["classification"] = "unsupported comparison"
            item["details"].extend(metadata_diffs)
            item["details"].append("body comparison unavailable because URL canonicalization blocked hashing")
        elif body_diff and metadata_diffs:
            item["classification"] = "metadata and body mismatch"
            item["details"].extend(metadata_diffs)
            item["details"].append("body hash differs")
        elif body_diff:
            item["classification"] = "body mismatch"
            item["details"].append("body hash differs")
        elif metadata_diffs:
            item["classification"] = "metadata mismatch"
            item["details"].extend(metadata_diffs)
        else:
            item["classification"] = "exact"
        items.append(item)
    for row in canvas_rows:
        if id(row) not in matched:
            items.append(
                {
                    "classification": "Canvas-only",
                    "title": str(row.get("title") or ""),
                    "local_path": "",
                    "canvas_id": row.get("page_id"),
                    "canvas_url": row.get("url") or "",
                    "details": [],
                }
            )
    return items


def comparable_assignments(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Assignments backed by discussions or quizzes are covered by their own sections."""
    rows = []
    for row in snapshot.get("assignments") or []:
        types = row.get("submission_types") or []
        if isinstance(types, str):
            types = [item.strip() for item in types.split(",") if item.strip()]
        if {"discussion_topic", "online_quiz"} & set(types):
            continue
        rows.append(assignment_base_compare_row(row))
    return rows


def compare_assignments(
    local_records: list[dict[str, Any]], snapshot: dict[str, Any], root: Path
) -> list[dict[str, Any]]:
    canvas_rows = comparable_assignments(snapshot)
    items = compare_titled(local_records, canvas_rows, title_key="name")
    records_by_path = {record["path"]: record for record in local_records}
    canvas_by_id = {row.get("id"): row for row in canvas_rows}
    for item in items:
        row = canvas_by_id.get(item.get("canvas_id"))
        record = records_by_path.get(item.get("local_path"))
        if not row or not record or not row.get("has_overrides"):
            continue
        source_metadata = record.get("source_metadata") or {}
        reference = str(source_metadata.get("availability_overrides_ref") or "").strip()
        count = len(
            [
                window
                for window in row.get("all_dates") or []
                if isinstance(window, dict) and not window.get("base")
            ]
        )
        if not reference:
            item["override_status"] = "untracked"
            item["details"].append(f"Canvas has untracked assignment overrides ({count})")
            if item["classification"] == "exact":
                item["classification"] = "override untracked"
            continue
        payload, error = load_local_override_file(root, reference)
        if error or payload is None:
            item["override_status"] = "error"
            item["details"].append(error)
            if item["classification"] == "exact":
                item["classification"] = "override mismatch"
            continue
        status, details = compare_local_overrides(row, payload)
        item["override_status"] = status.removeprefix("override ")
        item["details"].extend(details)
        if status == "override mismatch" and item["classification"] == "exact":
            item["classification"] = status
    return items


def snapshot_age_hours(generated_at: str, now: dt.datetime | None) -> float | None:
    text = generated_at.strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    current = now or dt.datetime.now(dt.UTC)
    return (current - parsed).total_seconds() / 3600


def compare_titled(
    local_records: list[dict[str, Any]],
    canvas_rows: list[dict[str, Any]],
    *,
    title_key: str = "title",
) -> list[dict[str, Any]]:
    canvas_by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canvas_rows:
        canvas_by_title[normalize_title(str(row.get(title_key) or ""))].append(row)

    items = []
    matched: set[int] = set()
    for record in local_records:
        item = {
            "classification": "",
            "title": record["title"] or record["path"],
            "local_path": record["path"],
            "canvas_id": None,
            "details": [],
        }
        if record["error"]:
            item["classification"] = "unsupported comparison"
            item["details"].append(record["error"])
        else:
            rows = canvas_by_title.get(normalize_title(record["title"]), [])
            if not rows:
                item["classification"] = "local-only"
            elif len(rows) > 1:
                item["classification"] = "unsupported comparison"
                item["details"].append(f"{len(rows)} Canvas items share this title")
                matched.update(id(row) for row in rows)
            else:
                row = rows[0]
                matched.add(id(row))
                item["canvas_id"] = row.get("id")
                diffs = field_diffs(record["metadata"], row)
                item["classification"] = "metadata mismatch" if diffs else "exact"
                item["details"].extend(diffs)
        items.append(item)

    for row in canvas_rows:
        if id(row) not in matched:
            items.append(
                {
                    "classification": "Canvas-only",
                    "title": str(row.get(title_key) or ""),
                    "local_path": "",
                    "canvas_id": row.get("id"),
                    "details": [],
                }
            )
    return items


def field_diffs(local_metadata: dict[str, Any], canvas_row: dict[str, Any]) -> list[str]:
    diffs = []
    for field, local_value in local_metadata.items():
        canvas_value = canvas_row.get(field)
        if not values_equal(field, local_value, canvas_value):
            diffs.append(f"{field}: local {local_value!r} != Canvas {canvas_value!r}")
    return diffs


def values_equal(field: str, local_value: Any, canvas_value: Any) -> bool:
    if field in DATE_FIELDS:
        return canonical_datetime(local_value) == canonical_datetime(canvas_value)
    if isinstance(local_value, bool) or isinstance(canvas_value, bool):
        return bool(local_value) == bool(canvas_value)
    if isinstance(local_value, (int, float)) and isinstance(canvas_value, (int, float)):
        return float(local_value) == float(canvas_value)
    return local_value == canvas_value


def canonical_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.astimezone(dt.UTC).isoformat()


def normalize_title(value: str) -> str:
    return " ".join(value.split()).lower()


def compare_discussions(
    local_records: list[dict[str, Any]], snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    assignments_by_id = {
        row.get("id"): row for row in snapshot.get("assignments") or [] if row.get("id")
    }
    enriched = []
    for row in snapshot.get("discussions") or []:
        merged = dict(row)
        linked = assignments_by_id.get(row.get("assignment_id"))
        if linked:
            merged["points_possible"] = linked.get("points_possible")
            merged["due_at"] = linked.get("due_at")
        enriched.append(merged)
    return compare_titled(local_records, enriched)


def compare_quizzes(
    local_records: list[dict[str, Any]], canvas_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items = compare_titled(local_records, canvas_rows)
    records_by_path = {record["path"]: record for record in local_records}
    for item in items:
        record = records_by_path.get(item["local_path"])
        if record and not record["error"] and not record["artifacts"].get("qti_zip"):
            item["details"].append("no QTI zip found next to source")
    return items


def compare_files(canvas_files: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    local_rows = local_files(root)
    local_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in local_rows:
        local_by_name[row["normalized_name"]].append(row)

    items = []
    for record in canvas_files:
        status, matches = status_for(record, local_by_name)
        details = [match["relative_path"] for match in matches]
        if status == "ambiguous_name_match":
            details.append("multiple local files share this name")
        items.append(
            {
                "classification": FILE_CLASSIFICATIONS[status],
                "title": record.get("canvas_path") or record.get("display_name") or "",
                "local_path": details[0] if matches else "",
                "canvas_id": record.get("id"),
                "details": details if status != "present_by_name_and_size" else [],
                "canvas_size": record.get("size"),
                "canvas_updated_at": record.get("updated_at") or "",
                "local_matches": [local_match_detail(match) for match in matches],
            }
        )
    return items


def local_match_detail(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "relative_path": match.get("relative_path") or "",
        "size": match.get("size"),
        "mtime": match.get("mtime") or "",
    }


def add_next_actions(sections: dict[str, list[dict[str, Any]]]) -> None:
    for section, items in sections.items():
        for item in items:
            action = next_action_for(section, item)
            if action:
                item["next_action"] = action


def next_action_for(section: str, item: dict[str, Any]) -> str:
    classification = item.get("classification")
    if section == "announcements" and classification == "Canvas-only":
        return (
            "Run `danvas announcements sync --output-dir content/announcements --dry-run` "
            "to plan a local source file."
        )
    if section == "discussions" and classification == "Canvas-only":
        return (
            "Run `danvas discussions sync-prompts --output-dir content/discussions --dry-run` "
            "to plan a local prompt source file."
        )
    if section == "assignments" and classification == "local-only":
        return "Run `danvas assignments create SOURCE --dry-run` before posting this local assignment."
    if section == "assignments" and classification == "override untracked":
        return "Export and reference the private Canvas assignment overrides if they should be tracked."
    if section == "assignments" and classification == "override mismatch":
        return "Review the private assignment override reference against Canvas before changing dates or membership."
    if section == "quizzes" and classification == "Canvas-only":
        return "Add a local quiz source if this Canvas quiz should be tracked in the course repo."
    if section == "files" and classification == "filename-only match":
        return "Inspect Canvas/local size and timestamps before deciding whether Canvas or local content is stale."
    if section == "pages" and classification == "Canvas-only":
        return "Run `danvas pages sync --output-dir content/pages --dry-run` to plan a local source."
    if section == "pages" and classification == "local-only":
        return "Run `danvas pages create SOURCE --dry-run` before creating this Page."
    if section == "pages" and classification == "probable match, unbound":
        identity = item.get("canvas_id") or item.get("canvas_url") or "CANDIDATE"
        return (
            f"Run `danvas pages verify SOURCE --page-id {identity}` and then bind the verified "
            "Page deliberately."
        )
    if section == "pages" and classification in {
        "metadata mismatch", "body mismatch", "metadata and body mismatch"
    }:
        return "Run `danvas pages verify SOURCE` or `danvas pages update SOURCE --dry-run`."
    if classification == "metadata mismatch":
        return "Review metadata differences before deciding whether local source or Canvas should change."
    return ""


def render_status_lines(payload: dict[str, Any]) -> list[str]:
    course = payload["course"]
    snapshot = payload["snapshot"]
    lines = [f"Course status: {course['name']} ({course['id']})"]
    age = snapshot["age_hours"]
    lines.append(
        f"Snapshot generated {snapshot['generated_at']}"
        + (f" ({age}h old)" if age is not None else "")
    )
    if snapshot["stale"]:
        lines.append(
            f"WARNING: snapshot is older than {snapshot['max_age_hours']}h. "
            "Run `danvas refresh` for current Canvas state."
        )
    summary = payload["summary"]
    if summary:
        lines.append(
            "Summary: " + ", ".join(f"{name}: {count}" for name, count in sorted(summary.items()))
        )
    for section, items in payload["sections"].items():
        if section == "pages" and not snapshot.get("pages_available", True):
            lines.append("Pages: unavailable (run `danvas refresh` for schema-v4 Page data)")
            continue
        counts = Counter(item["classification"] for item in items)
        count_text = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
        lines.append(f"{section.capitalize()}: {count_text or 'none'}")
        for item in items:
            if item["classification"] == "exact":
                continue
            detail = f" ({'; '.join(item['details'])})" if item["details"] else ""
            lines.append(f"  {item['classification']}: {item['title']}{detail}")
            if item.get("next_action"):
                lines.append(f"    Next action: {item['next_action']}")
    categories = payload["group_categories"]
    if categories:
        parts = [
            f"{category['name']}: {category['group_count']} groups, "
            f"{category['member_count']} members"
            for category in categories
        ]
        lines.append(f"Group categories: {len(categories)} ({'; '.join(parts)})")
    for note in payload["notes"]:
        lines.append(f"Note: {note}")
    return lines


def render_status_markdown(payload: dict[str, Any]) -> str:
    course = payload["course"]
    snapshot = payload["snapshot"]
    lines = [
        "# Course Status Report",
        "",
        f"- Course: {course['name']} ({course['id']})",
        f"- Snapshot generated: {snapshot['generated_at']}",
        f"- Snapshot age (hours): {snapshot['age_hours']}",
        f"- Snapshot stale: {'yes' if snapshot['stale'] else 'no'}",
        "",
        "## Summary",
        "",
    ]
    for name, count in sorted(payload["summary"].items()):
        lines.append(f"- {name}: {count}")
    for section, items in payload["sections"].items():
        lines.extend(["", f"## {section.capitalize()}", ""])
        if section == "pages" and not snapshot.get("pages_available", True):
            lines.append("Unavailable from this snapshot. Run `danvas refresh`.")
            continue
        if not items:
            lines.append("None.")
            continue
        for item in items:
            detail = f" ({'; '.join(item['details'])})" if item["details"] else ""
            location = item["local_path"] or f"Canvas ID {item['canvas_id']}"
            lines.append(f"- {item['classification']}: {item['title']} - {location}{detail}")
            if item.get("next_action"):
                lines.append(f"  Next action: {item['next_action']}")
    categories = payload["group_categories"]
    lines.extend(["", "## Group Categories", ""])
    if categories:
        for category in categories:
            lines.append(
                f"- {category['name']}: {category['group_count']} groups, "
                f"{category['member_count']} members"
            )
    else:
        lines.append("None.")
    lines.extend(["", "## Notes", ""])
    for note in payload["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
