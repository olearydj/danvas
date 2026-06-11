"""Canvas announcement import/export operations."""

from __future__ import annotations

import datetime as dt
import json
import tomllib
from pathlib import Path
from typing import Any

import yaml

from danvas.auth import canvas_from_args
from danvas.utils import canvas_object_to_dict, html_to_text, write_rows

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


def command_announcements_create(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Announcement Markdown source not found: {source}")
    announcement = load_announcement_markdown(source)
    if args.dry_run:
        print("Dry run - no announcement created.")
        print(json.dumps(announcement, indent=2, ensure_ascii=False))
        return
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    created = course.create_discussion_topic(**announcement)
    print(f"Created announcement: {created.title} (ID {created.id})")
    if getattr(created, "html_url", None):
        print(f"URL: {created.html_url}")


def load_announcement_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_announcement_frontmatter(text, source)
    if not str(metadata.get("title", "")).strip():
        raise SystemExit("Announcement metadata must include 'title'.")
    unknown = sorted(set(metadata) - ANNOUNCEMENT_METADATA_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported announcement metadata field(s): {', '.join(unknown)}")

    import markdown as markdown_lib

    announcement = {key: normalize_canvas_value(value) for key, value in metadata.items()}
    announcement.setdefault("published", False)
    announcement["is_announcement"] = True
    announcement["message"] = markdown_lib.markdown(body, extensions=["extra", "sane_lists"])
    return announcement


def parse_announcement_frontmatter(text: str, source: Path) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines:
        raise SystemExit(f"Announcement source must start with front matter: {source}")
    delimiter = lines[0].strip()
    if delimiter not in {"+++", "---"}:
        raise SystemExit(
            f"Announcement source must start with YAML (---) or TOML (+++) front matter: {source}"
        )
    close = next(
        (idx for idx, line in enumerate(lines[1:], start=1) if line.strip() == delimiter), None
    )
    if close is None:
        raise SystemExit(f"Announcement source missing closing {delimiter}: {source}")
    metadata_text = "".join(lines[1:close])
    if delimiter == "+++":
        metadata = tomllib.loads(metadata_text)
    else:
        metadata = yaml.safe_load(metadata_text) or {}
        if not isinstance(metadata, dict):
            raise SystemExit(f"Announcement YAML front matter must be a mapping: {source}")
    body = "".join(lines[close + 1 :])
    return {str(key): value for key, value in metadata.items()}, body


def normalize_canvas_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_canvas_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_canvas_value(item) for key, item in value.items()}
    return value


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
                        "author": participants.get(user_id, f"User {user_id}"),
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
