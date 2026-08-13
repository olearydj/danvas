"""Authored Canvas discussion create, verify, and scoped update workflows."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.auth import canvas_from_args
from danvas.authored_content import (
    DATETIME,
    SCALAR,
    ComparisonPolicy,
    comparison_check,
    first_value,
    normalized_text,
    require_valid_datetimes,
)
from danvas.canvas_links import canonical_canvas_object_url
from danvas.config import resolve_assignment_group_id
from danvas.frontmatter import markdown_to_html, normalize_canvas_value, parse_frontmatter
from danvas.mutation import (
    MutationMode,
    assert_canvas_mutation_allowed,
    mutation_mode_from_args,
)
from danvas.reports import ReportRun, create_report_run, safe_error, should_write_report_run
from danvas.source_map import resolve_source_canvas_id, write_source_map_entry
from danvas.utils import canvas_object_to_dict, html_to_text, print_mutation_banner

REPLY_DELIMITER_RE = re.compile(r"(?m)^---[ \t]+reply[ \t]+---[ \t]*$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)

DISCUSSION_TOPIC_FIELDS = {
    "allow_rating",
    "delayed_post_at",
    "discussion_type",
    "group_category_id",
    "lock_at",
    "lock_comment",
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
DISCUSSION_ASSIGNMENT_FIELDS = {
    "assignment_group_id",
    "assignment_group_name",
    "due_at",
    "grading_type",
    "lock_at",
    "only_visible_to_overrides",
    "points_possible",
    "published",
    "unlock_at",
}
DISCUSSION_GRADING_TRIGGER_FIELDS = {
    "assignment_group_id",
    "assignment_group_name",
    "due_at",
    "grading_type",
    "only_visible_to_overrides",
    "points_possible",
    "unlock_at",
}
DISCUSSION_PROVENANCE_FIELDS = {
    "assignment_id",
    "canvas_id",
    "canvas_url",
    "html_url",
    "id",
    "posted_at",
    "seed_entry_ids",
}
DISCUSSION_COMPARE_FIELDS = DISCUSSION_TOPIC_FIELDS | {
    "assignment_group_id",
    "assignment_id",
    "assignment_linked",
    "assignment_published",
    "canvas_url",
    "due_at",
    "grading_type",
    "only_visible_to_overrides",
    "points_possible",
    "unlock_at",
    "body_text",
}
DISCUSSION_DATETIME_FIELDS = {"delayed_post_at", "due_at", "lock_at", "unlock_at"}
DISCUSSION_FIELD_POLICIES: dict[str, ComparisonPolicy] = {
    field: (DATETIME if field in DISCUSSION_DATETIME_FIELDS else SCALAR)
    for field in DISCUSSION_COMPARE_FIELDS
}


def command_discussions_create(args: Any) -> None:
    source = require_discussion_source(args.source)
    project_root = optional_path(getattr(args, "project_root", None))
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = load_discussion_source(source, canvas_origin=canvas_origin)
    include_seeds = bool(getattr(args, "seed_replies", False))
    if local["seed_replies"] and not include_seeds:
        raise SystemExit(
            "Discussion source contains seeded replies. Pass --seed-replies to confirm posting them."
        )
    prepare_discussion_assignment(local, source)
    resolved = resolve_discussion_identity(args, source, local, project_root)
    plan = build_discussion_create_report(
        args=args,
        source=source,
        local=local,
        dry_run=bool(args.dry_run),
    )
    if resolved["id"] is not None:
        plan["status"] = "already_bound"
        plan["discussion_id"] = resolved["id"]
        plan["id_resolution"] = safe_resolution(resolved)
        plan["lookup"] = {
            "status": "already_bound",
            "reason": (
                f"Source is already bound to Canvas discussion ID {resolved['id']}; "
                "use discussions verify or update instead of create."
            ),
        }
        write_discussion_report(args, "create", plan)
        print_discussion_summary("create", plan)
        raise SystemExit(1)
    if args.dry_run:
        write_discussion_report(args, "create", plan)
        print_discussion_summary("create", plan)
        return

    mutation_mode = mutation_mode_from_args(args)
    assert_canvas_mutation_allowed(mutation_mode, "discussions create")
    print_mutation_banner(
        "create discussion",
        {
            "course": args.course_id,
            "title": local["topic"].get("title", ""),
            "published": local["topic"].get("published", False),
            "seed_replies": len(local["seed_replies"]),
            "source": source,
        },
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    topic_id: int | None = None
    identity_path: Path | None = None
    posted_progress: list[dict[str, Any]] = []
    try:
        created = course.create_discussion_topic(**discussion_create_payload(local))
        created_payload = canvas_object_to_dict(created)
        topic_id = int(first_value(created, created_payload, "id"))
        print(f"Created discussion topic ID {topic_id}")
        identity_path = write_discussion_creation_identity(
            source=source,
            course_id=int(args.course_id),
            created=created,
            created_payload=created_payload,
            local=local,
            project_root=project_root,
            seed_entry_ids=[],
            verification_status="pending",
            canvas_origin=canvas_origin,
        )
        print(f"Recorded created discussion identity in {identity_path}")
        posted = (
            post_seed_replies(
                created,
                local["seed_replies"],
                progress=posted_progress,
                mutation_mode=mutation_mode,
            )
            if include_seeds
            else []
        )
        readback = course.get_discussion_topic(topic_id)
        posted_ids = [row["id"] for row in posted]
        seed_records = discussion_seed_records(readback, posted_ids)
        canvas_record = discussion_canvas_record(
            course,
            readback,
            seed_records=seed_records,
            seed_entry_ids_requested=posted_ids,
            canvas_origin=canvas_origin,
        )
        report = build_discussion_create_report(
            args=args,
            source=source,
            local=local,
            dry_run=False,
            canvas_record=canvas_record,
            posted=posted,
        )
        write_discussion_creation_identity(
            source=source,
            course_id=int(args.course_id),
            created=created,
            created_payload=created_payload,
            local=local,
            project_root=project_root,
            seed_entry_ids=posted_ids,
            verification_status=report["status"],
            canvas_origin=canvas_origin,
        )
    except Exception as exc:  # noqa: BLE001 - retain bounded mutation failure evidence.
        recovery_error = ""
        if topic_id is not None and identity_path is not None:
            try:
                write_discussion_creation_identity(
                    source=source,
                    course_id=int(args.course_id),
                    created=created,
                    created_payload=created_payload,
                    local=local,
                    project_root=project_root,
                    seed_entry_ids=[
                        int(row["id"])
                        for row in sorted(posted_progress, key=lambda row: row["source_index"])
                    ],
                    verification_status="incomplete",
                    canvas_origin=canvas_origin,
                )
            except Exception as recovery_exc:  # noqa: BLE001 - retain original failure.
                recovery_error = safe_error(str(recovery_exc))
        plan["status"] = "failed"
        plan["error"] = safe_error(str(exc))
        plan["canvas"] = {"id": topic_id} if topic_id is not None else {}
        plan["posted_entries"] = posted_progress
        plan["source_map_status"] = "identity_recorded" if identity_path else "not_recorded"
        if recovery_error:
            plan["source_map_error"] = recovery_error
        write_discussion_report(args, "create", plan)
        print_discussion_summary("create", plan)
        raise

    write_discussion_report(args, "create", report)
    print_discussion_summary("create", report)
    if report["status"] != "created":
        raise SystemExit(1)
    if canvas_record.get("assignment_id"):
        print(f"Assignment ID: {canvas_record['assignment_id']}")
    if canvas_record.get("canvas_url"):
        print(f"URL: {canvas_record['canvas_url']}")
    source_map_path = write_discussion_source_map_entry(
        source=source,
        course_id=int(args.course_id),
        canvas_record=canvas_record,
        command="discussions create",
        local=local,
        project_root=project_root,
    )
    print(f"Wrote {source_map_path}")


def command_discussions_verify(args: Any) -> None:
    source = require_discussion_source(args.source)
    project_root = optional_path(getattr(args, "project_root", None))
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = load_discussion_source(source, canvas_origin=canvas_origin)
    prepare_discussion_assignment(local, source)
    resolved = resolve_discussion_identity(args, source, local, project_root)
    if resolved["id"] is None:
        raise SystemExit(
            "Discussion verification requires --discussion-id, canvas_id front matter, "
            "or a source-map entry."
        )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    lookup = {"method": resolved["source"], "status": "matched", "reason": ""}
    canvas_record: dict[str, Any] | None = None
    try:
        topic = course.get_discussion_topic(resolved["id"])
        entry_ids = discussion_seed_entry_ids(local, resolved)
        canvas_record = discussion_canvas_record(
            course,
            topic,
            seed_records=discussion_seed_records(topic, entry_ids),
            seed_entry_ids_requested=entry_ids,
            canvas_origin=canvas_origin,
        )
    except (ResourceDoesNotExist, KeyError):
        lookup = {
            "method": resolved["source"],
            "status": "not_found",
            "reason": f"Canvas discussion ID {resolved['id']} was not found.",
        }
    except Exception as exc:  # noqa: BLE001 - verification reports bounded lookup state.
        lookup = {
            "method": resolved["source"],
            "status": "indeterminate",
            "reason": safe_error(str(exc)),
        }
    report = build_discussion_verify_report(
        course=course,
        source=source,
        local=local,
        resolved=resolved,
        lookup=lookup,
        canvas_record=canvas_record,
    )
    write_discussion_report(args, "verify", report)
    print_discussion_summary("verify", report)
    if report["status"] != "matches":
        raise SystemExit(1)


def command_discussions_update(args: Any) -> None:
    source = require_discussion_source(args.source)
    project_root = optional_path(getattr(args, "project_root", None))
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = load_discussion_source(source, canvas_origin=canvas_origin)
    prepare_discussion_assignment(local, source)
    resolved = resolve_discussion_identity(args, source, local, project_root)
    if resolved["id"] is None:
        raise SystemExit(
            "Discussion update requires --discussion-id, canvas_id front matter, "
            "or a source-map entry."
        )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    topic, lookup = resolve_discussion_for_update(course, resolved)
    canvas_before = (
        discussion_canvas_record(course, topic, canvas_origin=canvas_origin) if topic else None
    )
    payload = discussion_update_payload(local, body_only=bool(args.body_only))
    report = build_discussion_update_report(
        course=course,
        source=source,
        local=local,
        resolved=resolved,
        lookup=lookup,
        canvas_before=canvas_before,
        canvas_after=None,
        update_payload=payload,
        body_only=bool(args.body_only),
        dry_run=bool(args.dry_run),
    )
    if topic is None:
        write_discussion_report(args, "update", report)
        print_discussion_summary("update", report)
        raise SystemExit(1)
    if args.dry_run or report["status"] == "no_change":
        write_discussion_report(args, "update", report)
        print_discussion_summary("update", report)
        return

    assert_canvas_mutation_allowed(args, "discussions update")
    print_discussion_summary("update", report)
    print_mutation_banner(
        "update discussion",
        {
            "course": args.course_id,
            "discussion_id": resolved["id"],
            "scope": "body-only" if args.body_only else "topic-and-assignment",
            "seed_replies": "unchanged",
            "source": source,
        },
    )
    updated = topic.update(**payload)
    updated_id = int(first_value(updated, canvas_object_to_dict(updated), "id") or resolved["id"])
    readback = course.get_discussion_topic(updated_id)
    canvas_after = discussion_canvas_record(course, readback, canvas_origin=canvas_origin)
    final_report = build_discussion_update_report(
        course=course,
        source=source,
        local=local,
        resolved={**resolved, "id": updated_id},
        lookup=lookup,
        canvas_before=canvas_before,
        canvas_after=canvas_after,
        update_payload=payload,
        body_only=bool(args.body_only),
        dry_run=False,
    )
    write_discussion_report(args, "update", final_report)
    print_discussion_summary("update", final_report)
    if final_report["status"] != "updated":
        raise SystemExit(1)
    source_map_path = write_discussion_source_map_entry(
        source=source,
        course_id=int(args.course_id),
        canvas_record=canvas_after,
        command="discussions update",
        local=local,
        project_root=project_root,
        seed_entry_ids=discussion_seed_entry_ids(local, resolved),
    )
    print(f"Wrote {source_map_path}")


def require_discussion_source(value: str | Path) -> Path:
    source = Path(value)
    if not source.is_file():
        raise SystemExit(f"Discussion Markdown source not found: {source}")
    return source


def load_discussion_source(source: Path, *, canvas_origin: str | None = None) -> dict[str, Any]:
    metadata, authored_body = parse_frontmatter(
        source.read_text(encoding="utf-8-sig"), source, "Discussion"
    )
    if not str(metadata.get("title") or "").strip():
        raise SystemExit("Discussion metadata must include 'title'.")
    unknown = sorted(
        set(metadata)
        - DISCUSSION_TOPIC_FIELDS
        - DISCUSSION_ASSIGNMENT_FIELDS
        - DISCUSSION_PROVENANCE_FIELDS
    )
    if unknown:
        raise SystemExit(f"Unsupported discussion metadata field(s): {', '.join(unknown)}")
    validate_discussion_datetimes(metadata)
    root_body, seed_bodies = split_discussion_body(authored_body)
    if not root_body.strip():
        raise SystemExit("Discussion topic body must not be empty.")
    topic = {
        key: normalize_canvas_value(value)
        for key, value in metadata.items()
        if key in DISCUSSION_TOPIC_FIELDS
    }
    topic.setdefault("published", False)
    topic.setdefault("discussion_type", "threaded")
    topic["message"] = markdown_to_html(root_body)
    assignment_values = {
        key: normalize_canvas_value(value)
        for key, value in metadata.items()
        if key in DISCUSSION_ASSIGNMENT_FIELDS
    }
    graded = bool(set(metadata) & DISCUSSION_GRADING_TRIGGER_FIELDS)
    assignment = assignment_values if graded else {}
    if "assignment_group_name" in assignment and "assignment_group_id" in assignment:
        raise SystemExit("Use either assignment_group_name or assignment_group_id, not both.")
    seed_replies = [
        {
            "source_index": index,
            "heading": markdown_heading(body),
            "body": body.strip(),
            "message": markdown_to_html(body),
        }
        for index, body in enumerate(seed_bodies, start=1)
    ]
    raw_ids = metadata.get("seed_entry_ids") or []
    if not isinstance(raw_ids, list):
        raise SystemExit("seed_entry_ids must be a list of Canvas entry IDs.")
    return {
        "frontmatter_id": optional_int(metadata.get("canvas_id", metadata.get("id")), "canvas_id"),
        "frontmatter_assignment_id": optional_int(metadata.get("assignment_id"), "assignment_id"),
        "frontmatter_seed_entry_ids": [int(value) for value in raw_ids],
        "canvas_url": canonical_canvas_object_url(
            metadata.get("canvas_url", metadata.get("html_url", "")),
            canvas_origin=canvas_origin,
        ),
        "declared_fields": declared_discussion_fields(metadata),
        "metadata_fields": set(metadata),
        "topic": topic,
        "assignment": assignment,
        "root_body": root_body.strip(),
        "body_text": normalized_text(html_to_text(topic["message"])),
        "body_sha256": hashlib.sha256(root_body.strip().encode("utf-8")).hexdigest(),
        "seed_replies": seed_replies,
    }


def validate_discussion_datetimes(metadata: dict[str, Any]) -> None:
    require_valid_datetimes(
        metadata,
        {field: DATETIME for field in DISCUSSION_DATETIME_FIELDS},
        source_type="Discussion",
    )


def split_discussion_body(body: str) -> tuple[str, list[str]]:
    parts = REPLY_DELIMITER_RE.split(body)
    replies = []
    for index, part in enumerate(parts[1:], start=1):
        if not part.strip():
            raise SystemExit(f"Seeded reply {index} is empty.")
        replies.append(part.strip())
    return parts[0].strip(), replies


def markdown_heading(body: str) -> str:
    match = HEADING_RE.search(body)
    return normalized_text(match.group(1)) if match else ""


def declared_discussion_fields(metadata: dict[str, Any]) -> list[str]:
    fields = {"title", "body_text"}
    for field in metadata:
        if field in DISCUSSION_TOPIC_FIELDS or field in DISCUSSION_ASSIGNMENT_FIELDS:
            fields.add(field)
    if "canvas_url" in metadata or "html_url" in metadata:
        fields.add("canvas_url")
    if "assignment_id" in metadata:
        fields.update({"assignment_id", "assignment_linked"})
    if set(metadata) & DISCUSSION_GRADING_TRIGGER_FIELDS:
        fields.add("assignment_linked")
        if "published" in metadata:
            fields.add("assignment_published")
    return sorted(fields & DISCUSSION_COMPARE_FIELDS)


def prepare_discussion_assignment(local: dict[str, Any], source: Path) -> None:
    assignment = local["assignment"]
    if "assignment_group_name" in assignment:
        assignment["assignment_group_id"] = resolve_assignment_group_id(
            str(assignment.pop("assignment_group_name")), start=source
        )
        local["metadata_fields"].add("assignment_group_id")
        local["declared_fields"] = sorted(
            set(local["declared_fields"]) | {"assignment_group_id", "assignment_linked"}
        )
    if assignment:
        assignment.setdefault("grading_type", "points")


def discussion_create_payload(local: dict[str, Any]) -> dict[str, Any]:
    payload = dict(local["topic"])
    if local["assignment"]:
        payload["assignment"] = dict(local["assignment"])
    return payload


def discussion_update_payload(local: dict[str, Any], *, body_only: bool) -> dict[str, Any]:
    if body_only:
        return {"message": local["topic"]["message"]}
    declared = local["metadata_fields"]
    payload = {
        key: value for key, value in local["topic"].items() if key == "message" or key in declared
    }
    assignment = {
        key: value
        for key, value in local["assignment"].items()
        if key in declared or (key == "assignment_group_id" and "assignment_group_name" in declared)
    }
    if assignment:
        payload["assignment"] = assignment
    return payload


def post_seed_replies(
    topic: Any,
    replies: list[dict[str, Any]],
    *,
    progress: list[dict[str, Any]] | None = None,
    mutation_mode: MutationMode,
) -> list[dict[str, Any]]:
    assert_canvas_mutation_allowed(mutation_mode, "discussions create seed replies")
    posted_by_index: dict[int, dict[str, Any]] = {}
    # Canvas displays top-level entries newest-first in the observed teaching workflow.
    # Reverse posting preserves authored source order on screen.
    for reply in reversed(replies):
        created = topic.post_entry(message=reply["message"])
        payload = canvas_object_to_dict(created)
        entry_id = int(first_value(created, payload, "id"))
        record = {
            "source_index": reply["source_index"],
            "id": entry_id,
            "heading": reply["heading"],
        }
        posted_by_index[reply["source_index"]] = record
        if progress is not None:
            progress.append(record)
        print(f"Posted seeded reply {reply['source_index']} (entry ID {entry_id})")
    return [posted_by_index[index] for index in sorted(posted_by_index)]


def discussion_seed_records(topic: Any, entry_ids: list[int]) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    records: dict[int, dict[str, Any]] = {}
    try:
        entries = topic.get_entries(entry_ids)
        for entry in entries:
            payload = canvas_object_to_dict(entry)
            entry_id = int(first_value(entry, payload, "id"))
            message = str(first_value(entry, payload, "message") or "")
            records[entry_id] = seed_record(entry_id, message)
    except (AttributeError, ResourceDoesNotExist, KeyError):
        return []
    return [records[entry_id] for entry_id in entry_ids if entry_id in records]


def seed_record(entry_id: int, message: str) -> dict[str, Any]:
    soup = BeautifulSoup(message, "html.parser")
    heading_tag = soup.find(re.compile(r"^h[1-6]$"))
    return {
        "id": entry_id,
        "heading": normalized_text(heading_tag.get_text(" ")) if heading_tag else "",
        "body_text": normalized_text(soup.get_text(" ")),
    }


def discussion_canvas_record(
    course: Any,
    topic: Any,
    *,
    seed_records: list[dict[str, Any]] | None = None,
    seed_entry_ids_requested: list[int] | None = None,
    canvas_origin: str | None = None,
) -> dict[str, Any]:
    payload = canvas_object_to_dict(topic)
    assignment_id = first_value(topic, payload, "assignment_id")
    assignment: Any | None = None
    assignment_payload: dict[str, Any] = {}
    if assignment_id and hasattr(course, "get_assignment"):
        try:
            assignment = course.get_assignment(assignment_id)
            assignment_payload = canvas_object_to_dict(assignment)
        except (ResourceDoesNotExist, KeyError):
            assignment = None
    message = str(first_value(topic, payload, "message") or "")

    def field(name: str) -> Any:
        value = first_value(assignment, assignment_payload, name) if assignment else ""
        return value if value != "" else first_value(topic, payload, name)

    topic_fields = {
        name: first_value(topic, payload, name)
        for name in DISCUSSION_TOPIC_FIELDS
    }
    return {
        **topic_fields,
        "id": first_value(topic, payload, "id"),
        "canvas_url": canonical_canvas_object_url(
            first_value(topic, payload, "html_url"), canvas_origin=canvas_origin
        ),
        "assignment_published": (
            first_value(assignment, assignment_payload, "published") if assignment else None
        ),
        "assignment_id": assignment_id,
        "assignment_linked": bool(assignment_id),
        "assignment_group_id": field("assignment_group_id"),
        "grading_type": field("grading_type"),
        "only_visible_to_overrides": field("only_visible_to_overrides"),
        "points_possible": field("points_possible"),
        "due_at": field("due_at"),
        "unlock_at": field("unlock_at"),
        "lock_at": field("lock_at"),
        "body_text": normalized_text(html_to_text(message)),
        "updated_at": first_value(topic, payload, "updated_at"),
        "seed_entries": seed_records or [],
        "seed_entry_ids_requested": seed_entry_ids_requested or [],
    }


def resolve_discussion_identity(
    args: Any, source: Path, local: dict[str, Any], project_root: Path | None
) -> dict[str, Any]:
    return resolve_source_canvas_id(
        kind="discussion",
        source=source,
        explicit_id=getattr(args, "discussion_id", None),
        frontmatter_id=local["frontmatter_id"],
        project_root=project_root,
    )


def resolve_discussion_for_update(
    course: Any, resolved: dict[str, Any]
) -> tuple[Any | None, dict[str, Any]]:
    try:
        topic = course.get_discussion_topic(resolved["id"])
    except (ResourceDoesNotExist, KeyError):
        return None, {
            "method": resolved["source"],
            "status": "not_found",
            "reason": f"Canvas discussion ID {resolved['id']} was not found.",
        }
    payload = canvas_object_to_dict(topic)
    if bool(first_value(topic, payload, "is_announcement", "announcement")):
        return None, {
            "method": resolved["source"],
            "status": "not_discussion",
            "reason": f"Canvas topic ID {resolved['id']} is an announcement.",
        }
    return topic, {"method": resolved["source"], "status": "matched", "reason": ""}


def discussion_seed_entry_ids(local: dict[str, Any], resolved: dict[str, Any]) -> list[int]:
    if local["frontmatter_seed_entry_ids"]:
        return local["frontmatter_seed_entry_ids"]
    entry = resolved.get("source_map_entry") or {}
    canvas = entry.get("canvas") if isinstance(entry, dict) else {}
    values = canvas.get("entry_ids") if isinstance(canvas, dict) else []
    return [int(value) for value in values or []]


def local_compare_record(local: dict[str, Any]) -> dict[str, Any]:
    topic = local["topic"]
    assignment = local["assignment"]
    return {
        **{field: topic.get(field) for field in DISCUSSION_TOPIC_FIELDS},
        "canvas_url": local.get("canvas_url") or "",
        "assignment_published": (assignment.get("published") if assignment else None),
        "assignment_id": local.get("frontmatter_assignment_id"),
        "assignment_linked": bool(assignment or local.get("frontmatter_assignment_id")),
        "assignment_group_id": assignment.get("assignment_group_id"),
        "grading_type": assignment.get("grading_type"),
        "only_visible_to_overrides": assignment.get("only_visible_to_overrides"),
        "points_possible": assignment.get("points_possible"),
        "due_at": assignment.get("due_at"),
        "unlock_at": assignment.get("unlock_at"),
        "lock_at": assignment.get("lock_at", topic.get("lock_at")),
        "body_text": local["body_text"],
        "declared_fields": local["declared_fields"],
    }


def discussion_checks(
    local: dict[str, Any], canvas: dict[str, Any], fields: set[str] | None = None
) -> list[dict[str, Any]]:
    declared = set(local.get("declared_fields") or [])
    wanted = fields if fields is not None else declared
    return [
        verify_check(field, local.get(field), canvas.get(field))
        for field in sorted(wanted & DISCUSSION_COMPARE_FIELDS)
    ]


def seed_checks(local: dict[str, Any], canvas: dict[str, Any]) -> list[dict[str, Any]]:
    local_seeds = local["seed_replies"]
    canvas_seeds = canvas.get("seed_entries") or []
    requested = canvas.get("seed_entry_ids_requested") or []
    if not local_seeds or not requested:
        return []
    checks = [verify_check("seed_prompt_count", len(local_seeds), len(canvas_seeds))]
    for index, (expected, actual) in enumerate(
        zip(local_seeds, canvas_seeds, strict=False), start=1
    ):
        if expected["heading"]:
            checks.append(
                verify_check(
                    f"seed_prompt_{index}_heading", expected["heading"], actual.get("heading")
                )
            )
    return checks


def build_discussion_create_report(
    *,
    args: Any,
    source: Path,
    local: dict[str, Any],
    dry_run: bool,
    canvas_record: dict[str, Any] | None = None,
    posted: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    checks = discussion_checks(local_compare_record(local), canvas_record) if canvas_record else []
    seeds = seed_checks(local, canvas_record) if canvas_record else []
    if dry_run:
        status = "would_create"
    elif canvas_record and all(check["matches"] for check in [*checks, *seeds]):
        status = "created"
    else:
        status = "readback_mismatch"
    return {
        "evidence_schema": "discussion-source-v1",
        "course_id": int(args.course_id),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "dry_run": dry_run,
        "status": status,
        "topic_payload": safe_topic_projection(local),
        "seed_reply_count": len(local["seed_replies"]),
        "seed_headings": [row["heading"] for row in local["seed_replies"]],
        "posting_order": "reverse-source-order",
        "canvas": canvas_record or {},
        "posted_entries": posted or [],
        "checks": checks,
        "seed_checks": seeds,
    }


def build_discussion_verify_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    resolved: dict[str, Any],
    lookup: dict[str, Any],
    canvas_record: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = discussion_checks(local_compare_record(local), canvas_record) if canvas_record else []
    seeds = seed_checks(local, canvas_record) if canvas_record else []
    if lookup["status"] != "matched":
        status = "indeterminate" if lookup["status"] == "indeterminate" else "not_found"
    else:
        status = "matches" if all(row["matches"] for row in [*checks, *seeds]) else "mismatch"
    if not local["seed_replies"]:
        seed_verification = "not_applicable"
    elif seeds:
        seed_verification = "checked"
    else:
        seed_verification = "not_available"
    return {
        "evidence_schema": "discussion-source-v1",
        "course": safe_course(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "status": status,
        "discussion_id": resolved.get("id"),
        "id_resolution": safe_resolution(resolved),
        "lookup": lookup,
        "local": local_compare_record(local),
        "canvas": canvas_record or {},
        "checks": checks,
        "seed_checks": seeds,
        "seed_verification": seed_verification,
    }


def build_discussion_update_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    resolved: dict[str, Any],
    lookup: dict[str, Any],
    canvas_before: dict[str, Any] | None,
    canvas_after: dict[str, Any] | None,
    update_payload: dict[str, Any],
    body_only: bool,
    dry_run: bool,
) -> dict[str, Any]:
    local_record = local_compare_record(local)
    fields = {"body_text"} if body_only else set(local_record["declared_fields"])
    before_checks = discussion_checks(local_record, canvas_before, fields) if canvas_before else []
    after_checks = discussion_checks(local_record, canvas_after, fields) if canvas_after else []
    mismatches = [row for row in before_checks if not row["matches"]]
    if lookup["status"] != "matched":
        status = "lookup_failed"
    elif canvas_after is not None:
        status = "updated" if all(row["matches"] for row in after_checks) else "readback_mismatch"
    elif dry_run:
        status = "would_update" if mismatches else "no_change"
    else:
        status = "no_change" if not mismatches else "planned"
    return {
        "evidence_schema": "discussion-source-v1",
        "course": safe_course(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "dry_run": dry_run,
        "body_only": body_only,
        "entry_mutation": "none",
        "status": status,
        "discussion_id": resolved.get("id"),
        "id_resolution": safe_resolution(resolved),
        "lookup": lookup,
        "local": local_record,
        "canvas_before": canvas_before or {},
        "canvas_after": canvas_after or {},
        "update_payload": safe_update_projection(update_payload),
        "diff": before_checks,
        "readback": {
            "status": (
                "matches"
                if canvas_after is not None and all(row["matches"] for row in after_checks)
                else "mismatch"
                if canvas_after is not None
                else "skipped"
            ),
            "checks": after_checks,
        },
    }


def safe_topic_projection(local: dict[str, Any]) -> dict[str, Any]:
    payload = discussion_create_payload(local)
    projection = {key: value for key, value in payload.items() if key != "message"}
    projection["body_sha256"] = local["body_sha256"]
    return projection


def safe_update_projection(payload: dict[str, Any]) -> dict[str, Any]:
    projection = {key: value for key, value in payload.items() if key != "message"}
    if "message" in payload:
        projection["body_sha256"] = hashlib.sha256(
            str(payload["message"]).encode("utf-8")
        ).hexdigest()
    return projection


def safe_course(course: Any) -> dict[str, Any]:
    payload = canvas_object_to_dict(course)
    return {
        key: payload.get(key, getattr(course, key, None))
        for key in ("id", "name", "course_code")
        if payload.get(key, getattr(course, key, None)) not in {None, ""}
    }


def safe_resolution(resolved: dict[str, Any]) -> dict[str, Any]:
    return {key: resolved.get(key) for key in ("source", "path", "id")}


def write_discussion_creation_identity(
    *,
    source: Path,
    course_id: int,
    created: Any,
    created_payload: dict[str, Any],
    local: dict[str, Any],
    project_root: Path | None,
    seed_entry_ids: list[int],
    verification_status: str,
    canvas_origin: str | None,
) -> Path:
    """Persist a retry guard immediately after Canvas returns a topic identity."""
    return write_source_map_entry(
        kind="discussion",
        source=source,
        course_id=course_id,
        canvas={
            "id": first_value(created, created_payload, "id"),
            "assignment_id": first_value(created, created_payload, "assignment_id"),
            "url": canonical_canvas_object_url(
                first_value(created, created_payload, "html_url"),
                canvas_origin=canvas_origin,
            ),
            "updated_at": first_value(created, created_payload, "updated_at") or "",
            "entry_ids": seed_entry_ids,
        },
        command="discussions create",
        fields={
            "mutation_status": "topic_created",
            "verification_status": verification_status,
            "seed_prompt_count": len(local["seed_replies"]),
        },
        body_sha256=local["body_sha256"],
        project_root=project_root,
    )


def write_discussion_source_map_entry(
    *,
    source: Path,
    course_id: int,
    canvas_record: dict[str, Any],
    command: str,
    local: dict[str, Any],
    project_root: Path | None,
    seed_entry_ids: list[int] | None = None,
) -> Path:
    entry_ids = seed_entry_ids
    if entry_ids is None:
        entry_ids = [int(row["id"]) for row in canvas_record.get("seed_entries") or []]
    fields = {
        key: value
        for key, value in local_compare_record(local).items()
        if key in DISCUSSION_COMPARE_FIELDS - {"body_text"} and value not in {None, ""}
    }
    fields["seed_prompt_count"] = len(local["seed_replies"])
    fields["seed_prompt_headings"] = [row["heading"] for row in local["seed_replies"]]
    return write_source_map_entry(
        kind="discussion",
        source=source,
        course_id=course_id,
        canvas={
            "id": canvas_record.get("id"),
            "assignment_id": canvas_record.get("assignment_id"),
            "url": canvas_record.get("canvas_url") or "",
            "updated_at": canvas_record.get("updated_at") or "",
            "entry_ids": entry_ids,
        },
        command=command,
        fields=fields,
        body_sha256=local["body_sha256"],
        project_root=project_root,
    )


def write_discussion_report(args: Any, action: str, report: dict[str, Any]) -> None:
    report_run = make_discussion_report_run(args, action, report)
    if report_run is None:
        return
    try:
        json_path = report_run.write_json(f"discussions-{action}.json", report)
        md_path = report_run.write_text(
            f"discussions-{action}.md", render_discussion_report(action, report)
        )
        success_states = {
            "would_create",
            "created",
            "matches",
            "would_update",
            "no_change",
            "updated",
        }
        manifest_path = report_run.finish(
            "success" if report["status"] in success_states else "failed"
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def make_discussion_report_run(args: Any, action: str, report: dict[str, Any]) -> ReportRun | None:
    project_root = optional_path(getattr(args, "project_root", None))
    report_root = optional_path(getattr(args, "report_root", None))
    report_dir = optional_path(getattr(args, "report_dir", None))
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
        command=f"discussions {action}",
        slug=report_slug or f"discussions-{action}",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"])],
        private_data=False,
    )


def render_discussion_report(action: str, report: dict[str, Any]) -> str:
    lines = [
        f"# Discussions {action.title()}",
        "",
        f"- Status: `{report['status']}`",
        f"- Source: `{report['source']}`",
    ]
    if "discussion_id" in report:
        lines.append(f"- Discussion ID: `{report.get('discussion_id') or ''}`")
    if "body_only" in report:
        lines.extend(
            [
                f"- Body only: `{report['body_only']}`",
                "- Seeded replies and student responses: `unchanged`",
            ]
        )
    checks = report.get("checks", report.get("diff", []))
    if checks:
        lines.extend(["", "| Field | Local | Canvas | Status |", "| --- | --- | --- | --- |"])
        for check in checks:
            status = "matches" if check["matches"] else "mismatch"
            lines.append(
                f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
            )
    seed_rows = report.get("seed_checks") or []
    if seed_rows:
        lines.extend(
            [
                "",
                "## Seeded prompts",
                "",
                "| Check | Local | Canvas | Status |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in seed_rows:
            status = "matches" if check["matches"] else "mismatch"
            lines.append(
                f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
            )
    elif report.get("seed_verification") == "not_available":
        lines.extend(
            [
                "",
                "## Seeded prompts",
                "",
                "Seed verification: `not_available` (no stable Canvas entry IDs were available).",
            ]
        )
    if report.get("lookup", {}).get("reason"):
        lines.extend(["", f"Reason: {report['lookup']['reason']}"])
    return "\n".join(lines) + "\n"


def print_discussion_summary(action: str, report: dict[str, Any]) -> None:
    print(f"Discussion {action}: {report['status']}")
    checks = report.get("checks")
    if checks is None and report.get("canvas_after"):
        checks = (report.get("readback") or {}).get("checks")
    if checks is None:
        checks = report.get("diff", [])
    for check in checks:
        print(f"  {check['field']}: {'OK' if check['matches'] else 'MISMATCH'}")
    for check in report.get("seed_checks", []):
        print(f"  {check['field']}: {'OK' if check['matches'] else 'MISMATCH'}")
    if report.get("seed_verification") == "not_available":
        print("  seeded prompts: NOT CHECKED (no stable Canvas entry IDs available)")
    if report.get("lookup", {}).get("reason"):
        print(f"  {report['lookup']['reason']}")


def verify_check(field: str, local_value: Any, canvas_value: Any) -> dict[str, Any]:
    return comparison_check(
        field,
        local_value,
        canvas_value,
        policy=DISCUSSION_FIELD_POLICIES.get(field, SCALAR),
    )


def optional_int(value: Any, field: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{field} must be an integer.") from exc


def optional_path(value: Any) -> Path | None:
    return Path(value) if value else None
