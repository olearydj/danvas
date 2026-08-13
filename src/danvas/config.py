"""Project-local danvas configuration and Canvas metadata snapshots."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from danvas.auth import canvas_from_args
from danvas.page_sources import BODY_NORMALIZER_VERSION
from danvas.project_config import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,  # noqa: F401 - compatibility re-export
    COURSE_SNAPSHOT_NAME,
    config_path,
    course_snapshot_path,
    find_config_dir,
    load_project_config,
    project_dir,  # noqa: F401 - compatibility re-export
    resolve_api_url,  # noqa: F401 - compatibility re-export
    resolve_course_id,
    resolve_course_timezone,  # noqa: F401 - compatibility re-export
)
from danvas.reports import create_report_run
from danvas.snapshot_collections import (
    collect_snapshot_collections,
    snapshot_collection_metadata,
    snapshot_collection_warnings,
    snapshot_is_complete,
)
from danvas.utils import canvas_object_to_dict, write_json_atomic

SNAPSHOT_SCHEMA_VERSION = 5
PARTIAL_SNAPSHOT_EXIT_CODE = 3

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
            metadata = snapshot_collection_metadata(snapshot, "assignment_groups")
            if not metadata["authoritative"]:
                raise SystemExit(
                    "Assignment groups are unavailable in the course snapshot "
                    f"({metadata['reason'] or metadata['status']}). Run `danvas refresh` "
                    "and resolve the collection warning before planning this mutation."
                )
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
    for warning in snapshot_collection_warnings(payload):
        print(warning, file=sys.stderr)
    require_complete_snapshot(payload, args, action="initialize")
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
    for warning in snapshot_collection_warnings(payload):
        print(warning, file=sys.stderr)
    require_complete_snapshot(payload, args, action="refresh")
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
            manifest_path = report_run.finish(
                "partial" if payload.get("snapshot_status") == "partial" else "success"
            )
            print(f"Wrote {json_path}")
            print(f"Wrote {md_path}")
            print(f"Wrote {manifest_path}")
            print(f"Report directory: {report_run.path}")
        except Exception as exc:
            report_run.finish("failed", error=str(exc))
            raise


def require_complete_snapshot(payload: dict[str, Any], args: Any, *, action: str) -> None:
    if not getattr(args, "require_complete", False):
        return
    if payload.get("snapshot_status") != "partial":
        return
    print(
        f"Snapshot is partial; --require-complete prevents {action} state from being written.",
        file=sys.stderr,
    )
    raise SystemExit(PARTIAL_SNAPSHOT_EXIT_CODE)


def build_course_snapshot(
    course: Any, *, canvas_origin: str | None = None
) -> dict[str, Any]:
    course_payload = canvas_object_to_dict(course)
    for key in ("id", "name", "course_code", "start_at", "end_at"):
        value = getattr(course, key, None)
        if value is not None and course_payload.get(key) is None:
            course_payload[key] = value
    if course_payload.get("id") is None:
        raise SystemExit("Required course metadata unavailable: course id is missing.")
    collections, collection_metadata = collect_snapshot_collections(
        course, canvas_origin=canvas_origin
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "snapshot_status": (
            "complete" if snapshot_is_complete(collection_metadata) else "partial"
        ),
        "course": course_payload,
        **collections,
        "collections": collection_metadata,
    }


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
    comparison_status = "success"
    for section, label_key, fields in DIFF_SECTIONS:
        old_metadata = snapshot_collection_metadata(old, section)
        new_metadata = snapshot_collection_metadata(new, section)
        old_authoritative = old_metadata["authoritative"]
        new_authoritative = new_metadata["authoritative"]
        if not (old_authoritative and new_authoritative):
            section_status = (
                "restored" if not old_authoritative and new_authoritative else "unavailable"
            )
            sections[section] = {
                "comparison_status": section_status,
                "old_status": old_metadata["status"],
                "new_status": new_metadata["status"],
                "old_reason": old_metadata.get("reason") or "",
                "new_reason": new_metadata.get("reason") or "",
                "added": [],
                "removed": [],
                "changed": [],
            }
            comparison_status = "partial"
            continue
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
            sections[section] = {
                "comparison_status": "compared",
                "old_status": old_metadata["status"],
                "new_status": new_metadata["status"],
                "old_reason": old_metadata.get("reason") or "",
                "new_reason": new_metadata.get("reason") or "",
                "added": added,
                "removed": removed,
                "changed": changed,
            }
    return {
        "old_generated_at": old.get("generated_at"),
        "new_generated_at": new.get("generated_at"),
        "comparison_status": comparison_status,
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
    status = str(diff.get("comparison_status") or "success")
    return {
        "status": status,
        "message": (
            "Some snapshot sections were not compared because one side was not authoritative."
            if status == "partial"
            else ""
        ),
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
        comparison_status = data.get("comparison_status", "compared")
        if comparison_status != "compared":
            lines.append(f"- Comparison: `{comparison_status}`")
            lines.append(
                f"- Previous collection: `{data.get('old_status')}`"
                + (
                    f" (`{data.get('old_reason')}`)"
                    if data.get("old_reason")
                    else ""
                )
            )
            lines.append(
                f"- New collection: `{data.get('new_status')}`"
                + (
                    f" (`{data.get('new_reason')}`)"
                    if data.get("new_reason")
                    else ""
                )
            )
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
        comparison_status = data.get("comparison_status", "compared")
        if comparison_status != "compared":
            old_detail = data.get("old_status") or "unknown"
            new_detail = data.get("new_status") or "unknown"
            if data.get("old_reason"):
                old_detail += f"/{data['old_reason']}"
            if data.get("new_reason"):
                new_detail += f"/{data['new_reason']}"
            lines.append(
                f"    comparison {comparison_status}: {old_detail} -> {new_detail}; "
                "no change claims"
            )
        for label in data["added"]:
            lines.append(f"    added: {label}")
        for label in data["removed"]:
            lines.append(f"    removed: {label}")
        for change in data["changed"]:
            lines.append(f"    changed: {change['label']} ({'; '.join(change['changes'])})")
    return lines


def write_course_snapshot(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(path, payload)


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
