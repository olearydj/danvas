"""Project-local danvas configuration and Canvas metadata snapshots."""

from __future__ import annotations

import datetime as dt
import json
import tomllib
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from danvas.auth import canvas_from_args
from danvas.files import canvas_file_record
from danvas.overrides import redacted_assignment_overrides
from danvas.pages import (
    BODY_NORMALIZER_VERSION,
    canonicalize_page_html,
    canonicalize_page_url,
    page_record,
)
from danvas.reports import create_report_run
from danvas.utils import canvas_object_to_dict, html_to_text

CONFIG_DIR_NAME = ".danvas"
CONFIG_FILE_NAME = "config.toml"
COURSE_SNAPSHOT_NAME = "course.json"
SNAPSHOT_SCHEMA_VERSION = 4


def project_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / CONFIG_DIR_NAME


def config_path(root: Path | None = None) -> Path:
    return project_dir(root) / CONFIG_FILE_NAME


def course_snapshot_path(root: Path | None = None) -> Path:
    return project_dir(root) / COURSE_SNAPSHOT_NAME


def find_config_dir(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        path = candidate / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if path.is_file():
            return path.parent
    return None


def load_project_config(start: Path | None = None) -> dict[str, Any]:
    config_dir = find_config_dir(start)
    if not config_dir:
        return {}
    data = tomllib.loads((config_dir / CONFIG_FILE_NAME).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"danvas config must be a TOML table: {config_dir / CONFIG_FILE_NAME}")
    return data


def resolve_course_id(explicit: int | None, *, start: Path | None = None) -> int:
    if explicit is not None:
        return explicit
    config = load_project_config(start)
    course_id = (config.get("canvas") or {}).get("course_id")
    if course_id is None:
        raise SystemExit(
            "Canvas course ID required. Pass --course-id or run `danvas init COURSE_ID` "
            "from the course project."
        )
    return int(course_id)


def resolve_api_url(explicit: str | None, *, start: Path | None = None) -> str | None:
    if explicit:
        return explicit
    config = load_project_config(start)
    value = (config.get("canvas") or {}).get("api_url")
    return str(value) if value else None


def resolve_assignment_group_id(
    name: str, *, explicit_id: int | None = None, start: Path | None = None
) -> int:
    if explicit_id is not None:
        raise SystemExit("Use either assignment_group_id or assignment_group_name, not both.")
    config_dir = find_config_dir(start)
    config = load_project_config(start)
    groups = config.get("assignment_groups") or {}
    if name in groups:
        return int(groups[name])
    if config_dir:
        snapshot_path = config_dir / COURSE_SNAPSHOT_NAME
        if snapshot_path.is_file():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            matches = [
                group
                for group in snapshot.get("assignment_groups", [])
                if str(group.get("name") or "") == name
            ]
            if len(matches) == 1:
                return int(matches[0]["id"])
            if len(matches) > 1:
                raise SystemExit(f"Assignment group name is ambiguous in course snapshot: {name}")
    raise SystemExit(
        f"Unknown assignment group name: {name}. Run `danvas refresh` or use assignment_group_id."
    )


def resolve_course_timezone(start: Path | None = None) -> ZoneInfo:
    config = load_project_config(start)
    timezone = (config.get("canvas") or {}).get("timezone")
    if not timezone:
        raise SystemExit(
            "Date-only assignment metadata requires [canvas].timezone in .danvas/config.toml. "
            "Run `danvas init` or use explicit *_at datetime fields."
        )
    try:
        return ZoneInfo(str(timezone))
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"Unknown course timezone in .danvas/config.toml: {timezone}") from exc


def command_init(args: Any) -> None:
    root = Path(args.project_root).resolve()
    config = config_path(root)
    snapshot = course_snapshot_path(root)
    if config.exists() and not args.force:
        raise SystemExit(f"Config already exists: {config}. Use --force to replace it.")
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    payload = build_course_snapshot(
        course, canvas_origin=getattr(args, "api_url", None)
    )
    write_project_config(
        config,
        course_snapshot=payload,
        api_url=args.api_url,
        timezone=args.timezone,
    )
    write_course_snapshot(snapshot, payload)
    maybe_ignore_course_snapshot(root)
    maybe_ignore_reports(root)
    print(f"Wrote {config}")
    print(f"Wrote {snapshot}")


def command_refresh(args: Any) -> None:
    root = Path(args.project_root).resolve()
    args.course_id = resolve_course_id(args.course_id, start=root)
    report_root = getattr(args, "report_root", None)
    report_dir = getattr(args, "report_dir", None)
    report_slug = getattr(args, "report_slug", None)
    report_requested = bool(report_root or report_dir or report_slug)
    if report_root and report_dir:
        raise SystemExit("Use either --report-root or --report-dir, not both.")
    if report_requested and not getattr(args, "diff", False):
        raise SystemExit("Refresh report output requires --diff.")
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    payload = build_course_snapshot(
        course, canvas_origin=getattr(args, "api_url", None)
    )
    snapshot = course_snapshot_path(root)
    diff_report = None
    if getattr(args, "diff", False):
        if snapshot.is_file():
            previous = json.loads(snapshot.read_text(encoding="utf-8"))
            diff_report = build_refresh_diff_report(previous, payload, snapshot)
            for line in render_snapshot_diff_payload(diff_report):
                print(line)
        else:
            diff_report = build_refresh_diff_report(None, payload, snapshot)
            print("No previous snapshot; nothing to diff.")
    write_course_snapshot(snapshot, payload)
    print(f"Wrote {snapshot}")
    if report_requested and diff_report is not None:
        report_run = create_report_run(
            command="refresh --diff",
            slug=report_slug or "refresh-diff",
            project_root=root,
            report_root=Path(report_root) if report_root else None,
            report_dir=Path(report_dir) if report_dir else None,
            course_id=args.course_id,
            input_paths=[snapshot],
            snapshot_timestamp=payload.get("generated_at"),
            private_data=False,
        )
        try:
            json_path = report_run.write_json("refresh-diff.json", diff_report)
            md_path = report_run.write_text(
                "refresh-diff.md", render_refresh_diff_markdown(diff_report)
            )
            manifest_path = report_run.finish()
            print(f"Wrote {json_path}")
            print(f"Wrote {md_path}")
            print(f"Wrote {manifest_path}")
            print(f"Report directory: {report_run.path}")
        except Exception as exc:
            report_run.finish("failed", error=str(exc))
            raise


def build_course_snapshot(
    course: Any, *, canvas_origin: str | None = None
) -> dict[str, Any]:
    course_payload = canvas_object_to_dict(course)
    for key in ("id", "name", "course_code", "start_at", "end_at"):
        value = getattr(course, key, None)
        if value is not None and course_payload.get(key) is None:
            course_payload[key] = value
    groups = [
        canvas_object_to_dict(group)
        for group in sorted(
            course.get_assignment_groups(), key=lambda group: str(getattr(group, "name", ""))
        )
    ]
    groups_by_id = {int(group["id"]): group for group in groups if group.get("id") is not None}
    assignments = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        group = groups_by_id.get(int(getattr(assignment, "assignment_group_id", 0) or 0), {})
        row = {
            "id": getattr(assignment, "id", ""),
            "name": getattr(assignment, "name", ""),
            "assignment_group_id": getattr(assignment, "assignment_group_id", ""),
            "assignment_group_name": group.get("name", ""),
            "points_possible": getattr(assignment, "points_possible", ""),
            "due_at": getattr(assignment, "due_at", ""),
            "unlock_at": getattr(assignment, "unlock_at", ""),
            "lock_at": getattr(assignment, "lock_at", ""),
            "published": getattr(assignment, "published", ""),
            "html_url": getattr(assignment, "html_url", ""),
            "submission_types": getattr(assignment, "submission_types", []) or [],
            "description_text": html_to_text(getattr(assignment, "description", "")),
        }
        row.update(redacted_assignment_overrides(assignment))
        assignments.append(row)
    assignments.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    folder_objs = list(course.get_folders())
    folders = [
        canvas_object_to_dict(folder)
        for folder in sorted(folder_objs, key=lambda folder: str(getattr(folder, "full_name", "")))
    ]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "course": course_payload,
        "assignment_groups": groups,
        "assignments": assignments,
        "folders": folders,
        "files": snapshot_files(course, folder_objs),
        "discussions": snapshot_discussions(course),
        "announcements": snapshot_announcements(course),
        "quizzes": snapshot_quizzes(course),
        "pages": snapshot_pages(course, canvas_origin=canvas_origin),
        "group_categories": snapshot_group_categories(course),
    }


def snapshot_files(course: Any, folder_objs: list[Any]) -> list[dict[str, Any]]:
    folders_by_id = {
        int(folder.id): folder for folder in folder_objs if getattr(folder, "id", None)
    }
    rows = [canvas_file_record(file_obj, folders_by_id) for file_obj in course.get_files()]
    rows.sort(key=lambda row: (str(row["folder_full_name"]), str(row["display_name"])))
    return rows


def snapshot_pages(
    course: Any, *, canvas_origin: str | None = None
) -> list[dict[str, Any]]:
    rows = []
    course_id = int(getattr(course, "id", 0) or 0)
    for summary in course.get_pages():
        record = page_record(summary)
        if not record["body"] and record["url"]:
            record = page_record(course.get_page(record["url"]))
        canonical = canonicalize_page_html(
            record.pop("body", ""),
            course_id=course_id,
            canvas_origin=canvas_origin,
        )
        record["html_url"], unsafe_html_url = canonicalize_page_url(
            str(record.get("html_url") or ""),
            course_id=course_id,
            canvas_origin=canvas_origin,
        )
        if unsafe_html_url:
            record["html_url"] = ""
        rows.append(
            {
                **record,
                "body_sha256": canonical["body_sha256"],
                "body_hash_status": canonical["body_hash_status"],
                "volatile_url_count": canonical["volatile_url_count"],
                "body_normalizer": BODY_NORMALIZER_VERSION,
            }
        )
    rows.sort(
        key=lambda row: (
            " ".join(str(row.get("title") or "").casefold().split()),
            str(row.get("page_id") or row.get("url") or ""),
        )
    )
    return rows


def snapshot_discussions(course: Any) -> list[dict[str, Any]]:
    rows = [discussion_record(topic) for topic in course.get_discussion_topics()]
    rows.sort(key=lambda row: str(row["title"]))
    return rows


def snapshot_announcements(course: Any) -> list[dict[str, Any]]:
    rows = [
        discussion_record(topic)
        for topic in course.get_discussion_topics(only_announcements=True)
    ]
    rows.sort(key=lambda row: (str(row["posted_at"]), str(row["title"])))
    return rows


def discussion_record(topic: Any) -> dict[str, Any]:
    return {
        "id": getattr(topic, "id", None),
        "title": getattr(topic, "title", "") or "",
        "html_url": getattr(topic, "html_url", "") or "",
        "assignment_id": getattr(topic, "assignment_id", None),
        "published": getattr(topic, "published", None),
        "locked": getattr(topic, "locked", None),
        "posted_at": getattr(topic, "posted_at", "") or "",
        "delayed_post_at": getattr(topic, "delayed_post_at", "") or "",
        "message_text": html_to_text(getattr(topic, "message", "") or ""),
    }


def snapshot_quizzes(course: Any) -> list[dict[str, Any]]:
    rows = []
    for quiz in course.get_quizzes():
        rows.append(
            {
                "id": getattr(quiz, "id", None),
                "assignment_id": getattr(quiz, "assignment_id", None),
                "title": getattr(quiz, "title", "") or "",
                "description_text": html_to_text(getattr(quiz, "description", "") or ""),
                "quiz_type": getattr(quiz, "quiz_type", "") or "",
                "points_possible": getattr(quiz, "points_possible", None),
                "question_count": getattr(quiz, "question_count", None),
                "due_at": getattr(quiz, "due_at", "") or "",
                "unlock_at": getattr(quiz, "unlock_at", "") or "",
                "lock_at": getattr(quiz, "lock_at", "") or "",
                "published": getattr(quiz, "published", None),
                "time_limit": getattr(quiz, "time_limit", None),
                "allowed_attempts": getattr(quiz, "allowed_attempts", None),
                "html_url": getattr(quiz, "html_url", "") or "",
            }
        )
    rows.sort(key=lambda row: str(row["title"]))
    return rows


def snapshot_group_categories(course: Any) -> list[dict[str, Any]]:
    rows = []
    for category in course.get_group_categories():
        groups = sorted(
            category.get_groups(), key=lambda group: str(getattr(group, "name", ""))
        )
        rows.append(
            {
                "id": getattr(category, "id", None),
                "name": getattr(category, "name", "") or "",
                "self_signup": getattr(category, "self_signup", None),
                "group_count": len(groups),
                "member_count": sum(
                    int(getattr(group, "members_count", 0) or 0) for group in groups
                ),
                "groups": [
                    {
                        "id": getattr(group, "id", None),
                        "name": getattr(group, "name", "") or "",
                        "members_count": getattr(group, "members_count", None),
                    }
                    for group in groups
                ],
            }
        )
    rows.sort(key=lambda row: str(row["name"]))
    return rows


DIFF_SECTIONS: list[tuple[str, str, list[str]]] = [
    (
        "assignments",
        "name",
        ["name", "points_possible", "due_at", "unlock_at", "lock_at", "published"],
    ),
    ("assignment_groups", "name", ["name", "group_weight"]),
    ("files", "display_name", ["display_name", "folder_full_name", "size", "updated_at"]),
    (
        "quizzes",
        "title",
        [
            "title",
            "points_possible",
            "due_at",
            "unlock_at",
            "lock_at",
            "published",
            "time_limit",
            "allowed_attempts",
            "question_count",
        ],
    ),
    ("announcements", "title", ["title", "posted_at", "delayed_post_at", "published"]),
    ("discussions", "title", ["title", "published", "locked", "assignment_id"]),
    (
        "pages",
        "title",
        ["title", "url", "published", "front_page", "publish_at", "body_sha256"],
    ),
    ("group_categories", "name", ["name", "group_count", "member_count"]),
]


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any] | None:
    old_version = int(old.get("schema_version") or 1)
    new_version = int(new.get("schema_version") or 1)
    if old_version != new_version:
        return None
    sections: dict[str, dict[str, Any]] = {}
    for section, label_key, fields in DIFF_SECTIONS:
        identity_key = "page_id" if section == "pages" else "id"
        old_rows = rows_by_id(old.get(section) or [], identity_key=identity_key)
        new_rows = rows_by_id(new.get(section) or [], identity_key=identity_key)
        added = sorted(
            str(new_rows[key].get(label_key) or key) for key in new_rows.keys() - old_rows.keys()
        )
        removed = sorted(
            str(old_rows[key].get(label_key) or key) for key in old_rows.keys() - new_rows.keys()
        )
        changed = []
        for key in sorted(old_rows.keys() & new_rows.keys(), key=str):
            changes = []
            for field in fields:
                if section == "pages" and field == "body_sha256":
                    old_normalizer = old_rows[key].get("body_normalizer")
                    new_normalizer = new_rows[key].get("body_normalizer")
                    if not (
                        old_normalizer == new_normalizer == BODY_NORMALIZER_VERSION
                    ):
                        changes.append(
                            "body_sha256: comparison unavailable "
                            "(normalizer mismatch; refresh required)"
                        )
                        continue
                if old_rows[key].get(field) != new_rows[key].get(field):
                    changes.append(
                        f"{field}: {old_rows[key].get(field)!r} -> "
                        f"{new_rows[key].get(field)!r}"
                    )
            if changes:
                changed.append(
                    {
                        "label": str(new_rows[key].get(label_key) or key),
                        "changes": changes,
                    }
                )
        if added or removed or changed:
            sections[section] = {"added": added, "removed": removed, "changed": changed}
    return {
        "old_generated_at": old.get("generated_at"),
        "new_generated_at": new.get("generated_at"),
        "sections": sections,
    }


def build_refresh_diff_report(
    old: dict[str, Any] | None, new: dict[str, Any], snapshot_path: Path
) -> dict[str, Any]:
    if old is None:
        return {
            "status": "no_previous_snapshot",
            "message": "No previous snapshot; nothing to diff.",
            "snapshot_path": str(snapshot_path),
            "old_generated_at": None,
            "new_generated_at": new.get("generated_at"),
            "old_schema_version": None,
            "new_schema_version": new.get("schema_version"),
            "schema_compatible": True,
            "sections": {},
        }
    old_version = int(old.get("schema_version") or 1)
    new_version = int(new.get("schema_version") or 1)
    diff = diff_snapshots(old, new)
    if diff is None:
        return {
            "status": "schema_changed",
            "message": "Snapshot format changed; diff unavailable. The new snapshot replaces the old one.",
            "snapshot_path": str(snapshot_path),
            "old_generated_at": old.get("generated_at"),
            "new_generated_at": new.get("generated_at"),
            "old_schema_version": old_version,
            "new_schema_version": new_version,
            "schema_compatible": False,
            "sections": {},
        }
    return {
        "status": "success",
        "message": "",
        "snapshot_path": str(snapshot_path),
        "old_schema_version": old_version,
        "new_schema_version": new_version,
        "schema_compatible": True,
        **diff,
    }


def render_snapshot_diff_payload(report: dict[str, Any]) -> list[str]:
    if report["status"] == "schema_changed":
        return [report["message"]]
    if report["status"] == "no_previous_snapshot":
        return [report["message"]]
    return render_snapshot_diff(
        {
            "old_generated_at": report["old_generated_at"],
            "new_generated_at": report["new_generated_at"],
            "sections": report["sections"],
        }
    )


def render_refresh_diff_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Refresh Diff Report",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`",
        f"- Snapshot: `{report['snapshot_path']}`",
        f"- Previous generated at: `{report['old_generated_at']}`",
        f"- New generated at: `{report['new_generated_at']}`",
        f"- Previous schema version: `{report['old_schema_version']}`",
        f"- New schema version: `{report['new_schema_version']}`",
        f"- Schema compatible: `{report['schema_compatible']}`",
        "",
    ]
    if report.get("message"):
        lines.extend(["## Message", "", report["message"], ""])
    if not report["sections"]:
        lines.extend(["## Changes", "", "- No tracked changes."])
        return "\n".join(lines).rstrip() + "\n"
    lines.extend(["## Changes", ""])
    for section, data in report["sections"].items():
        lines.extend([f"### {section}", ""])
        for label in data["added"]:
            lines.append(f"- Added: {label}")
        for label in data["removed"]:
            lines.append(f"- Removed: {label}")
        for change in data["changed"]:
            lines.append(f"- Changed: {change['label']}")
            for item in change["changes"]:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def rows_by_id(
    rows: list[dict[str, Any]], *, identity_key: str = "id"
) -> dict[Any, dict[str, Any]]:
    return {
        row.get(identity_key): row
        for row in rows
        if row.get(identity_key) is not None
    }


def render_snapshot_diff(report: dict[str, Any] | None) -> list[str]:
    if report is None:
        return ["Snapshot format changed; diff unavailable. The new snapshot replaces the old one."]
    lines = [
        f"Snapshot diff: {report['old_generated_at']} -> {report['new_generated_at']}"
    ]
    if not report["sections"]:
        lines.append("  No changes detected in tracked sections.")
    for section, data in report["sections"].items():
        lines.append(f"  {section}:")
        for label in data["added"]:
            lines.append(f"    added: {label}")
        for label in data["removed"]:
            lines.append(f"    removed: {label}")
        for change in data["changed"]:
            lines.append(f"    changed: {change['label']} ({'; '.join(change['changes'])})")
    return lines


def write_course_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_project_config(
    path: Path, *, course_snapshot: dict[str, Any], api_url: str, timezone: str
) -> None:
    course = course_snapshot.get("course") or {}
    course_id = course.get("id")
    if course_id is None:
        raise SystemExit("Course snapshot is missing course.id; cannot write danvas config.")
    lines = [
        "# danvas project configuration",
        "# Generated by `danvas init`; edit stable project defaults here.",
        "",
        "[canvas]",
        f"api_url = {toml_string(api_url)}",
        f"course_id = {int(course_id)}",
        f"course_name = {toml_string(str(course.get('name') or ''))}",
        f"timezone = {toml_string(timezone)}",
        "",
        "[assignment_groups]",
    ]
    for group in course_snapshot.get("assignment_groups", []):
        name = str(group.get("name") or "")
        if name:
            lines.append(f"{toml_key(name)} = {int(group['id'])}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def maybe_ignore_course_snapshot(root: Path) -> None:
    maybe_append_gitignore(root, f"{CONFIG_DIR_NAME}/{COURSE_SNAPSHOT_NAME}")


def maybe_ignore_reports(root: Path) -> None:
    maybe_append_gitignore(root, f"{CONFIG_DIR_NAME}/reports/")


def maybe_append_gitignore(root: Path, ignore_line: str) -> None:
    if not (root / ".git").exists():
        return
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ignore_line in existing.splitlines():
        return
    with gitignore.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"{ignore_line}\n")


def toml_key(value: str) -> str:
    if value.isascii() and value.replace("_", "").replace("-", "").isalnum():
        return value
    return toml_string(value)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
