"""Read-only course status report comparing the snapshot to local sources."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from danvas.config import (
    COURSE_SNAPSHOT_NAME,
    SNAPSHOT_SCHEMA_VERSION,
    find_config_dir,
    load_project_config,
)
from danvas.files import local_files, status_for
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
    if int(snapshot.get("schema_version") or 1) < SNAPSHOT_SCHEMA_VERSION:
        raise SystemExit(
            "Course snapshot predates the current format. Run `danvas refresh` first."
        )
    max_age_hours = resolve_max_age_hours(args.max_age_hours, config_dir)
    payload = build_status(snapshot, config_dir.parent, max_age_hours=max_age_hours)
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
) -> dict[str, Any]:
    sources = scan_sources(root)
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sources:
        by_kind[record["kind"]].append(record)

    sections = {
        "assignments": compare_titled(
            by_kind["assignment"], comparable_assignments(snapshot), title_key="name"
        ),
        "announcements": compare_titled(
            by_kind["announcement"], snapshot.get("announcements") or []
        ),
        "discussions": compare_discussions(by_kind["discussion"], snapshot),
        "quizzes": compare_quizzes(by_kind["quiz"], snapshot.get("quizzes") or []),
        "files": compare_files(snapshot.get("files") or [], root),
    }
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
        ],
    }


def comparable_assignments(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Assignments backed by discussions or quizzes are covered by their own sections."""
    rows = []
    for row in snapshot.get("assignments") or []:
        types = row.get("submission_types") or []
        if isinstance(types, str):
            types = [item.strip() for item in types.split(",") if item.strip()]
        if {"discussion_topic", "online_quiz"} & set(types):
            continue
        rows.append(row)
    return rows


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
            }
        )
    return items


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
        counts = Counter(item["classification"] for item in items)
        count_text = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
        lines.append(f"{section.capitalize()}: {count_text or 'none'}")
        for item in items:
            if item["classification"] == "exact":
                continue
            detail = f" ({'; '.join(item['details'])})" if item["details"] else ""
            lines.append(f"  {item['classification']}: {item['title']}{detail}")
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
        if not items:
            lines.append("None.")
            continue
        for item in items:
            detail = f" ({'; '.join(item['details'])})" if item["details"] else ""
            location = item["local_path"] or f"Canvas ID {item['canvas_id']}"
            lines.append(f"- {item['classification']}: {item['title']} - {location}{detail}")
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
