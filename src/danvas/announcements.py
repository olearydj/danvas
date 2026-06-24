"""Canvas announcement import/export operations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from danvas.auth import canvas_from_args
from danvas.frontmatter import markdown_to_html, normalize_canvas_value, parse_frontmatter
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.utils import (
    canvas_object_to_dict,
    html_to_text,
    print_mutation_banner,
    slugify,
    write_rows,
)

ANNOUNCEMENT_METADATA_FIELDS = {
    "allow_rating",
    "delayed_post_at",
    "discussion_type",
    "lock_at",
    "lock_comment",
    "locked",
    "only_graders_can_rate",
    "pinned",
    "podcast_enabled",
    "podcast_has_student_posts",
    "published",
    "require_initial_post",
    "sort_by_rating",
    "specific_sections",
    "title",
}
ANNOUNCEMENT_PROVENANCE_FIELDS = {
    "canvas_id",
    "canvas_url",
    "posted_at",
}


def command_announcements_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    reply_user_id = args.reply_user_id
    reply_user_name = ""
    if reply_user_id is None:
        current_user = canvas.get_current_user()
        reply_user_id = int(current_user.id)
        reply_user_name = getattr(current_user, "name", "") or getattr(
            current_user, "sortable_name", ""
        )

    course_payload = canvas_object_to_dict(course)
    records = announcement_records(course, int(reply_user_id))
    payload = {
        "course": course_payload,
        "reply_user": {"id": int(reply_user_id), "name": reply_user_name},
        "announcements": records,
    }
    output = Path(args.output)
    fmt = resolve_format(output, args.format)
    if fmt == "csv":
        write_announcements_csv(output, records)
    elif fmt == "markdown":
        write_announcements_markdown(output, payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    reply_count = sum(len(record["instructor_replies"]) for record in records)
    print(f"Wrote {len(records)} announcements and {reply_count} filtered replies to {output}")


def command_announcements_sync(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    output_dir = Path(args.output_dir)
    records = announcement_records(course, reply_user_id=0)
    plan = build_announcements_sync_plan(
        course=course,
        records=records,
        output_dir=output_dir,
        dry_run=bool(args.dry_run),
    )
    if not args.dry_run:
        write_announcements_sync_files(plan)
    write_announcements_sync_report_run(make_announcements_sync_report_run(args, plan), plan)
    print_announcements_sync_summary(plan)


def command_announcements_verify(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Announcement Markdown source not found: {source}")
    local = announcement_verify_local_source(source, getattr(args, "announcement_id", None))
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    records = announcement_records(course, reply_user_id=0)
    canvas_record = next(
        (record for record in records if str(record.get("id") or "") == str(local["canvas_id"])),
        None,
    )
    report = build_announcement_verify_report(
        course=course,
        source=source,
        local=local,
        canvas_record=canvas_record,
    )
    write_announcement_verify_report_run(make_announcement_verify_report_run(args, report), report)
    print_announcement_verify_summary(report)
    if report["status"] != "matches":
        raise SystemExit(1)


def command_announcements_create(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Announcement Markdown source not found: {source}")
    announcement = load_announcement_markdown(source)
    if args.dry_run:
        print("Dry run - no announcement created.")
        print(json.dumps(announcement, indent=2, ensure_ascii=False))
        return
    print_mutation_banner(
        "create announcement",
        {
            "course": args.course_id,
            "title": announcement.get("title", ""),
            "published": announcement.get("published", False),
            "source": source,
        },
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    created = course.create_discussion_topic(**announcement)
    print(f"Created announcement: {created.title} (ID {created.id})")
    if getattr(created, "html_url", None):
        print(f"URL: {created.html_url}")


def load_announcement_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text, source, "Announcement")
    if not str(metadata.get("title", "")).strip():
        raise SystemExit("Announcement metadata must include 'title'.")
    unknown = sorted(set(metadata) - ANNOUNCEMENT_METADATA_FIELDS - ANNOUNCEMENT_PROVENANCE_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported announcement metadata field(s): {', '.join(unknown)}")
    announcement = {
        key: normalize_canvas_value(value)
        for key, value in metadata.items()
        if key not in ANNOUNCEMENT_PROVENANCE_FIELDS
    }
    announcement.setdefault("published", False)
    announcement["is_announcement"] = True
    announcement["message"] = markdown_to_html(body)
    return announcement


def resolve_format(output: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if output.suffix.lower() == ".csv":
        return "csv"
    if output.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    return "json"


def announcement_records(course: Any, reply_user_id: int) -> list[dict[str, Any]]:
    records = [
        announcement_record(course, topic, reply_user_id)
        for topic in course.get_discussion_topics(only_announcements=True)
    ]
    records.sort(key=lambda row: (str(row["posted_at"] or ""), str(row["title"] or "")))
    return records


def announcement_record(course: Any, topic: Any, reply_user_id: int) -> dict[str, Any]:
    topic_payload = canvas_object_to_dict(topic)
    full_topic = course.get_full_discussion_topic(topic.id)
    return {
        "id": getattr(topic, "id", topic_payload.get("id", "")),
        "title": getattr(topic, "title", topic_payload.get("title", "")),
        "posted_at": first_value(topic, topic_payload, "posted_at", "created_at"),
        "delayed_post_at": first_value(topic, topic_payload, "delayed_post_at"),
        "lock_at": first_value(topic, topic_payload, "lock_at"),
        "locked": first_value(topic, topic_payload, "locked"),
        "published": first_value(topic, topic_payload, "published"),
        "last_reply_at": first_value(topic, topic_payload, "last_reply_at"),
        "html_url": first_value(topic, topic_payload, "html_url"),
        "author": announcement_author(topic, topic_payload, full_topic),
        "message": html_to_text(first_value(topic, topic_payload, "message") or ""),
        "message_html": first_value(topic, topic_payload, "message") or "",
        "instructor_replies": filtered_replies(full_topic, reply_user_id),
        "topic": topic_payload,
    }


def first_value(obj: Any, payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None and value != "":
            return value
        value = payload.get(name)
        if value is not None and value != "":
            return value
    return ""


def announcement_author(
    topic: Any, topic_payload: dict[str, Any], full_topic: dict[str, Any]
) -> str:
    user_name = first_value(topic, topic_payload, "user_name")
    if user_name:
        return str(user_name)
    user_id = first_value(topic, topic_payload, "user_id")
    participants = participants_by_id(full_topic)
    return participants.get(user_id, f"User {user_id}" if user_id else "")


def filtered_replies(full_topic: dict[str, Any], reply_user_id: int) -> list[dict[str, Any]]:
    participants = participants_by_id(full_topic)
    replies: list[dict[str, Any]] = []

    def walk(entries: list[dict[str, Any]], parent_id: int | None = None, depth: int = 0) -> None:
        for entry in entries:
            if entry.get("deleted"):
                continue
            user_id = entry.get("user_id")
            if user_id == reply_user_id:
                replies.append(
                    {
                        "id": entry.get("id"),
                        "parent_id": entry.get("parent_id", parent_id),
                        "author": participants.get(reply_user_id, f"User {user_id}"),
                        "author_id": user_id,
                        "message": html_to_text(entry.get("message") or ""),
                        "message_html": entry.get("message") or "",
                        "created_at": entry.get("created_at"),
                        "updated_at": entry.get("updated_at"),
                        "depth": depth,
                    }
                )
            walk(entry.get("replies") or [], entry.get("id"), depth + 1)

    walk(full_topic.get("view", []))
    replies.sort(key=lambda row: (str(row["created_at"] or ""), int(row["id"] or 0)))
    return replies


def participants_by_id(full_topic: dict[str, Any]) -> dict[int, str]:
    participants: dict[int, str] = {}
    for participant in full_topic.get("participants", []):
        user_id = participant.get("id")
        if user_id is None:
            continue
        participants[int(user_id)] = participant.get("display_name") or f"User {user_id}"
    return participants


def write_announcements_csv(output: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for record in records:
        rows.append(
            {
                "announcement_id": record["id"],
                "announcement_title": record["title"],
                "announcement_posted_at": record["posted_at"],
                "announcement_url": record["html_url"],
                "record_type": "announcement",
                "reply_id": "",
                "parent_id": "",
                "created_at": record["posted_at"],
                "author": record["author"],
                "author_id": "",
                "message": record["message"],
            }
        )
        for reply in record["instructor_replies"]:
            rows.append(
                {
                    "announcement_id": record["id"],
                    "announcement_title": record["title"],
                    "announcement_posted_at": record["posted_at"],
                    "announcement_url": record["html_url"],
                    "record_type": "instructor_reply",
                    "reply_id": reply["id"],
                    "parent_id": reply["parent_id"] or "",
                    "created_at": reply["created_at"],
                    "author": reply["author"],
                    "author_id": reply["author_id"],
                    "message": reply["message"],
                }
            )
    write_rows(
        output,
        rows,
        [
            "announcement_id",
            "announcement_title",
            "announcement_posted_at",
            "announcement_url",
            "record_type",
            "reply_id",
            "parent_id",
            "created_at",
            "author",
            "author_id",
            "message",
        ],
    )


def write_announcements_markdown(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    course = payload["course"]
    reply_user = payload["reply_user"]
    lines = [
        "# Canvas Announcements Export",
        "",
        f"Course: {course.get('name') or course.get('course_code') or course.get('id') or ''}",
        f"Reply filter user ID: {reply_user.get('id', '')}",
        "",
    ]
    for record in payload["announcements"]:
        lines.extend(
            [
                f"## {record['title']}",
                "",
                f"- Announcement ID: {record['id']}",
                f"- Posted: {record['posted_at'] or ''}",
                f"- URL: {record['html_url'] or ''}",
                "",
                record["message"] or "",
                "",
            ]
        )
        if record["instructor_replies"]:
            lines.extend(["### Filtered Replies", ""])
            for reply in record["instructor_replies"]:
                lines.extend(
                    [
                        f"- {reply['created_at'] or ''} - {reply['author']}",
                        "",
                        reply["message"] or "",
                        "",
                    ]
                )
        else:
            lines.extend(["### Filtered Replies", "", "None.", ""])
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_announcements_sync_plan(
    *,
    course: Any,
    records: list[dict[str, Any]],
    output_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    existing_by_id = existing_announcement_sources(output_dir)
    used_names: set[str] = set()
    actions = []
    for index, record in enumerate(records, start=1):
        path = unique_announcement_path(output_dir, index, record, used_names)
        markdown = render_announcement_source_markdown(record)
        canvas_id = str(record.get("id") or "")
        existing_path = existing_by_id.get(canvas_id) if canvas_id else None
        status = "would_create" if dry_run else "created"
        reason = ""
        if existing_path:
            status = "skipped_known_local"
            reason = "Existing local source has matching canvas_id."
            path = existing_path
        elif path.exists():
            existing_canvas_id = announcement_source_canvas_id(path)
            if existing_canvas_id:
                status = "conflict"
                reason = f"Target exists with different canvas_id {existing_canvas_id}."
            else:
                status = "skipped_exists"
                reason = "Target exists without matching canvas_id."
        actions.append(
            {
                "status": status,
                "reason": reason,
                "canvas_id": record.get("id"),
                "title": record.get("title") or "",
                "canvas_url": record.get("html_url") or "",
                "target_path": str(path),
                "target_relative_path": (
                    path.relative_to(output_dir).as_posix()
                    if path.is_relative_to(output_dir)
                    else str(path)
                ),
                "markdown": markdown if status in {"would_create", "created"} else "",
            }
        )
    return {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "output_dir": str(output_dir),
        "actions": actions,
    }


def existing_announcement_sources(output_dir: Path) -> dict[str, Path]:
    if not output_dir.exists():
        return {}
    by_id = {}
    for path in sorted(output_dir.glob("*.md")):
        canvas_id = announcement_source_canvas_id(path)
        if canvas_id:
            by_id.setdefault(canvas_id, path)
    return by_id


def announcement_source_canvas_id(path: Path) -> str:
    try:
        metadata, _body = parse_frontmatter(
            path.read_text(encoding="utf-8-sig"),
            path,
            "Announcement",
        )
    except (OSError, SystemExit):
        return ""
    return str(metadata.get("canvas_id") or "")


def unique_announcement_path(
    output_dir: Path,
    index: int,
    record: dict[str, Any],
    used_names: set[str],
) -> Path:
    base = f"{index:03d}-{slugify(str(record.get('title') or ''), f'announcement-{index}')}"
    name = f"{base}.md"
    counter = 2
    while name in used_names:
        name = f"{base}-{counter}.md"
        counter += 1
    used_names.add(name)
    return output_dir / name


def render_announcement_source_markdown(record: dict[str, Any]) -> str:
    metadata = {
        "title": record.get("title") or "",
        "canvas_id": record.get("id"),
        "canvas_url": record.get("html_url") or "",
        "posted_at": record.get("posted_at") or "",
        "delayed_post_at": record.get("delayed_post_at") or "",
        "lock_at": record.get("lock_at") or "",
        "locked": record.get("locked") if record.get("locked") != "" else None,
        "published": record.get("published") if record.get("published") != "" else None,
    }
    metadata = {key: value for key, value in metadata.items() if value not in {"", None}}
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    body = str(record.get("message") or "").strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def announcement_verify_local_source(
    source: Path, announcement_id: int | None = None
) -> dict[str, Any]:
    metadata, body = parse_frontmatter(source.read_text(encoding="utf-8-sig"), source, "Announcement")
    canvas_id = announcement_id if announcement_id is not None else metadata.get("canvas_id")
    if canvas_id is None or str(canvas_id).strip() == "":
        raise SystemExit("Announcement verification requires --announcement-id or canvas_id front matter.")
    return {
        "canvas_id": int(canvas_id),
        "canvas_url": str(metadata.get("canvas_url") or ""),
        "title": str(metadata.get("title") or ""),
        "published": metadata.get("published"),
        "delayed_post_at": str(metadata.get("delayed_post_at") or ""),
        "lock_at": str(metadata.get("lock_at") or ""),
        "body_text": normalized_text(html_to_text(markdown_to_html(body))),
    }


def build_announcement_verify_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    canvas_record: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = []
    if canvas_record is None:
        status = "not_found"
    else:
        checks = announcement_verify_checks(local, canvas_record)
        status = "matches" if all(check["matches"] for check in checks) else "mismatch"
    return {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "canvas_id": local["canvas_id"],
        "status": status,
        "local": local,
        "canvas": canvas_record or {},
        "checks": checks,
    }


def announcement_verify_checks(
    local: dict[str, Any], canvas_record: dict[str, Any]
) -> list[dict[str, Any]]:
    checks = [
        verify_check("title", local.get("title"), canvas_record.get("title")),
        verify_check("canvas_url", local.get("canvas_url"), canvas_record.get("html_url")),
        verify_check("published", local.get("published"), canvas_record.get("published")),
        verify_check(
            "delayed_post_at",
            local.get("delayed_post_at"),
            canvas_record.get("delayed_post_at"),
        ),
        verify_check("lock_at", local.get("lock_at"), canvas_record.get("lock_at")),
        verify_check(
            "body_text",
            local.get("body_text"),
            normalized_text(str(canvas_record.get("message") or "")),
        ),
    ]
    return [check for check in checks if check["local"] != "" or check["canvas"] != ""]


def verify_check(field: str, local_value: Any, canvas_value: Any) -> dict[str, Any]:
    local = comparable_value(local_value)
    canvas = comparable_value(canvas_value)
    return {
        "field": field,
        "matches": local == canvas,
        "local": local,
        "canvas": canvas,
    }


def comparable_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    text = str(value)
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    return normalized_text(text)


def normalized_text(value: str) -> str:
    return " ".join(value.split())


def make_announcement_verify_report_run(args: Any, report: dict[str, Any]) -> ReportRun | None:
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=False,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="announcements verify",
        slug=report_slug or "announcements-verify",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"])],
        private_data=False,
    )


def write_announcement_verify_report_run(
    report_run: ReportRun | None, report: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        json_path = report_run.write_json("announcements-verify.json", report)
        md_path = report_run.write_text(
            "announcements-verify.md", render_announcement_verify_markdown(report)
        )
        manifest_path = report_run.finish("success" if report["status"] == "matches" else "failed")
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def render_announcement_verify_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Announcements Verify",
        "",
        f"- Status: `{report['status']}`",
        f"- Source: `{report['source']}`",
        f"- Canvas ID: `{report['canvas_id']}`",
        "",
        "| Field | Local | Canvas | Status |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        status = "matches" if check["matches"] else "mismatch"
        lines.append(
            f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
        )
    if report["status"] == "not_found":
        lines.extend(["", "Canvas announcement was not found by ID."])
    return "\n".join(lines) + "\n"


def print_announcement_verify_summary(report: dict[str, Any]) -> None:
    print(f"Announcement verify: {report['status']}")
    for check in report["checks"]:
        marker = "OK" if check["matches"] else "MISMATCH"
        print(f"  {check['field']}: {marker}")


def write_announcements_sync_files(plan: dict[str, Any]) -> None:
    for action in plan["actions"]:
        if action["status"] != "created":
            continue
        target = Path(action["target_path"])
        if target.exists():
            action["status"] = "skipped_exists"
            action["reason"] = "Target appeared before write."
            action["markdown"] = ""
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action["markdown"], encoding="utf-8")


def make_announcements_sync_report_run(args: Any, plan: dict[str, Any]) -> ReportRun | None:
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=False,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="announcements sync",
        slug=report_slug or "announcements-sync",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(plan["output_dir"])],
        private_data=False,
    )


def write_announcements_sync_report_run(
    report_run: ReportRun | None, plan: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        report_plan = sync_report_payload(plan)
        json_path = report_run.write_json("announcements-sync.json", report_plan)
        md_path = report_run.write_text(
            "announcements-sync.md", render_announcements_sync_markdown(report_plan)
        )
        manifest_path = report_run.finish()
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def sync_report_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **plan,
        "actions": [
            {key: value for key, value in action.items() if key != "markdown"}
            for action in plan["actions"]
        ],
    }


def render_announcements_sync_markdown(plan: dict[str, Any]) -> str:
    counts = sync_status_counts(plan["actions"])
    lines = [
        "# Announcements Sync",
        "",
        f"- Dry run: `{plan['dry_run']}`",
        f"- Output directory: `{plan['output_dir']}`",
        f"- Actions: `{len(plan['actions'])}`",
        "",
        "## Summary",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        [
            "",
            "## Actions",
            "",
            "| Status | Canvas ID | Title | Target | Reason |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for action in plan["actions"]:
        lines.append(
            "| {status} | {canvas_id} | {title} | `{target}` | {reason} |".format(
                status=action["status"],
                canvas_id=action.get("canvas_id") or "",
                title=escape_table(str(action.get("title") or "")),
                target=action.get("target_relative_path") or action.get("target_path") or "",
                reason=escape_table(str(action.get("reason") or "")),
            )
        )
    return "\n".join(lines) + "\n"


def print_announcements_sync_summary(plan: dict[str, Any]) -> None:
    print(json.dumps(sync_status_counts(plan["actions"]), indent=2, sort_keys=True))


def sync_status_counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action["status"]] = counts.get(action["status"], 0) + 1
    return counts


def escape_table(value: str) -> str:
    return value.replace("|", "\\|")
