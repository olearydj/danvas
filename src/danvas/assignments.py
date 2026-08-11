"""Canvas assignment import/export operations."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.auth import canvas_from_args
from danvas.canvas_links import (
    canonical_canvas_object_url,
    extract_canvas_file_references,
    stable_course_file_url,
)
from danvas.config import resolve_assignment_group_id, resolve_course_timezone
from danvas.frontmatter import markdown_to_html, normalize_canvas_value, parse_frontmatter
from danvas.overrides import private_assignment_overrides
from danvas.reports import ReportRun, create_report_run, safe_error, should_write_report_run
from danvas.source_map import resolve_source_canvas_id, write_source_map_entry
from danvas.utils import (
    canvas_object_to_dict,
    html_to_text,
    mark_private,
    print_mutation_banner,
    slugify,
    write_json,
    write_rows,
)

ASSIGNMENT_METADATA_FIELDS = {
    "allowed_attempts",
    "allowed_extensions",
    "anonymous_grading",
    "anonymous_peer_reviews",
    "assignment_group_id",
    "assignment_group",
    "assignment_group_name",
    "automatic_peer_reviews",
    "due_at",
    "due_date",
    "external_tool_tag_attributes",
    "final_grader_id",
    "grade_group_students_individually",
    "grader_comments_visible_to_graders",
    "grader_count",
    "graders_anonymous_to_graders",
    "graders_names_visible_to_final_grader",
    "grading_standard_id",
    "grading_type",
    "group_category_id",
    "hide_in_gradebook",
    "integration_data",
    "integration_id",
    "lock_at",
    "lock_date",
    "moderated_grading",
    "name",
    "notify_of_update",
    "omit_from_final_grade",
    "only_visible_to_overrides",
    "peer_reviews",
    "points_possible",
    "position",
    "published",
    "submission_types",
    "turnitin_enabled",
    "turnitin_settings",
    "unlock_at",
    "unlock_date",
    "vericite_enabled",
}

ASSIGNMENT_LOCAL_FIELDS = {"availability_overrides_ref"}

DECLARED_FIELD_ALIASES = {
    "name": "title",
    "due_date": "due_at",
    "unlock_date": "unlock_at",
    "lock_date": "lock_at",
    "assignment_group": "assignment_group_name",
}
ASSIGNMENT_VERIFY_SUPPORTED_FIELDS = {
    "title",
    "canvas_url",
    "points_possible",
    "due_at",
    "unlock_at",
    "lock_at",
    "published",
    "assignment_group_id",
    "assignment_group_name",
    "submission_types",
    "grading_type",
    "group_category_id",
    "allowed_extensions",
    "body_text",
}
ASSIGNMENT_PROVENANCE_FIELDS = {"assignment_id", "canvas_id", "id"}
SENSITIVE_ASSIGNMENT_TEXT_RE = re.compile(
    r"(?i)\b(?:secure_params|verifier|access_token|api_key|authorization|bearer|"
    r"signature|policy|x-amz-[a-z0-9-]+|x-goog-[a-z0-9-]+)\b"
    r"(?:\s*[=:]\s*[^\s&\"']+)?"
)


def command_assignments_verify(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = assignment_verify_local_source(
        source,
        getattr(args, "assignment_id", None),
        course_id=int(args.course_id),
        canvas_origin=canvas_origin,
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    canvas_record: dict[str, Any] | None = None
    fetch_error = ""
    fetch_status = "ok"
    try:
        assignment = course.get_assignment(local["assignment_id"])
        canvas_record = assignment_verify_canvas_record(
            course, assignment, canvas_origin=canvas_origin
        )
    except ResourceDoesNotExist:
        fetch_status = "not_found"
        fetch_error = "assignment_not_found"
    except Exception as exc:  # noqa: BLE001 - verification retains sanitized evidence.
        fetch_status = "indeterminate"
        fetch_error = safe_assignment_lookup_reason(exc)
    report = build_assignment_verify_report(
        course=course,
        source=source,
        local=local,
        canvas_record=canvas_record,
        fetch_error=fetch_error,
        fetch_status=fetch_status,
        canvas_origin=canvas_origin,
    )
    write_assignment_verify_report_run(make_assignment_verify_report_run(args, report), report)
    print_assignment_verify_summary(report)
    if report["status"] != "matches":
        raise SystemExit(1)


def command_assignments_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    course_payload = safe_course_record(course)
    groups = {
        int(group.id): safe_assignment_group_record(group)
        for group in course.get_assignment_groups()
    }
    rows = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        payload = canvas_object_to_dict(assignment)
        group = groups.get(int(getattr(assignment, "assignment_group_id", 0) or 0), {})
        description = str(getattr(assignment, "description", "") or "")
        raw_file_links = extract_canvas_file_references(
            description,
            current_course_id=int(getattr(course, "id", args.course_id)),
            canvas_origin=str(getattr(args, "api_url", "") or ""),
        )
        valid_links = [link for link in raw_file_links if link.get("status") == "valid"]
        file_links = [safe_file_link(link) for link in raw_file_links]
        row = {
            "id": getattr(assignment, "id", ""),
            "name": safe_assignment_text(getattr(assignment, "name", "")),
            "assignment_group_id": getattr(assignment, "assignment_group_id", ""),
            "assignment_group_name": group.get("name", ""),
            "points_possible": getattr(assignment, "points_possible", ""),
            "due_at": getattr(assignment, "due_at", ""),
            "unlock_at": getattr(assignment, "unlock_at", ""),
            "lock_at": getattr(assignment, "lock_at", ""),
            "published": getattr(assignment, "published", ""),
            "html_url": canonical_canvas_object_url(
                getattr(assignment, "html_url", ""),
                canvas_origin=str(getattr(args, "api_url", "") or ""),
            ),
            "submission_types": ",".join(getattr(assignment, "submission_types", []) or []),
            "description_text": safe_assignment_text(html_to_text(description)),
            "file_ids": ",".join(str(link["file_id"]) for link in valid_links),
            "file_urls": ",".join(str(link.get("canvas_url") or "") for link in valid_links),
            "file_links": file_links,
        }
        if args.full:
            row["extended"] = safe_assignment_export_extended(payload)
            row["assignment_group"] = group
        rows.append(row)
    rows.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    output = Path(args.output)
    fmt = resolve_format(output, args.format)
    if fmt == "csv":
        fields = [
            "id",
            "name",
            "assignment_group_id",
            "assignment_group_name",
            "points_possible",
            "due_at",
            "unlock_at",
            "lock_at",
            "published",
            "html_url",
            "submission_types",
            "description_text",
            "file_ids",
            "file_urls",
        ]
        write_rows(
            output,
            [{key: row.get(key, "") for key in fields} for row in rows],
            fields,
        )
    elif fmt == "markdown":
        write_assignments_markdown(output, course_payload, groups, rows)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} assignments to {output}")


def command_assignments_overrides(args: Any) -> None:
    output = Path(args.output)
    if output.exists() and not getattr(args, "overwrite", False):
        raise SystemExit(f"Refusing to overwrite existing private output: {output}")
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(
        args.assignment_id, include=["all_dates", "overrides"]
    )
    payload = private_assignment_overrides(
        assignment, source=str(getattr(args, "source", "") or "")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in {".yaml", ".yml"}:
        output.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        write_json(output, payload)
    mark_private(output)
    print(f"Wrote private assignment override export: {output}")


def resolve_format(output: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = output.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if not suffix:
        return "markdown"
    raise SystemExit(
        f"Cannot infer assignments export format from '{output.name}'. "
        "Use .json, .csv, an extensionless directory, or pass --format."
    )


def write_assignments_markdown(
    output: Path,
    course_payload: dict[str, Any],
    groups: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "course": course_payload,
        "assignment_groups": list(groups.values()),
        "assignment_count": len(rows),
        "points_possible_total": sum(float(row["points_possible"] or 0) for row in rows),
    }
    (output / "course.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for index, row in enumerate(rows, start=1):
        slug = slugify(str(row["name"]), f"assignment-{row['id']}")
        path = output / f"{index:03d}-{slug}-{row['id']}.md"
        metadata = {key: row[key] for key in row if key != "description_text"}
        text = "---\n" + json.dumps(metadata, indent=2, ensure_ascii=False) + "\n---\n\n"
        text += row["description_text"] or ""
        path.write_text(text, encoding="utf-8")


def command_assignments_create(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    assignment = load_assignment_markdown(source)
    if "assignment_group" in assignment:
        if "assignment_group_name" in assignment:
            raise SystemExit("Use either assignment_group or assignment_group_name, not both.")
        assignment["assignment_group_name"] = assignment.pop("assignment_group")
    if "assignment_group_name" in assignment:
        assignment["assignment_group_id"] = resolve_assignment_group_id(
            str(assignment.pop("assignment_group_name")),
            explicit_id=assignment.get("assignment_group_id"),
            start=source,
        )
    if args.dry_run:
        print("Dry run - no assignment created.")
        print(
            json.dumps(
                safe_assignment_mutation_projection(
                    assignment,
                    course_id=int(args.course_id),
                    canvas_origin=str(getattr(args, "api_url", "") or ""),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    create_assignment_from_loaded_source(
        args,
        source,
        assignment_update_local_source(
            source,
            course_id=int(args.course_id),
            canvas_origin=str(getattr(args, "api_url", "") or ""),
        ),
        assignment,
    )


def create_assignment_from_loaded_source(
    args: Any,
    source: Path,
    local: dict[str, Any],
    assignment: dict[str, Any] | None = None,
    course: Any | None = None,
) -> None:
    assignment = assignment or local["assignment"]
    print_mutation_banner(
        "create assignment",
        {
            "course": args.course_id,
            "name": safe_assignment_text(assignment.get("name", "")),
            "published": assignment.get("published", False),
            "source": source,
        },
    )
    if course is None:
        canvas = canvas_from_args(args)
        course = canvas.get_course(args.course_id)
    created = course.create_assignment(assignment)
    created_id = int(first_value(created, canvas_object_to_dict(created), "id"))
    readback = course.get_assignment(created_id)
    canvas_record = assignment_verify_canvas_record(
        course,
        readback,
        canvas_origin=str(getattr(args, "api_url", "") or ""),
    )
    print(f"Created assignment: {safe_assignment_text(created.name)} (ID {created.id})")
    created_url = canonical_canvas_object_url(
        getattr(created, "html_url", ""),
        canvas_origin=str(getattr(args, "api_url", "") or ""),
    )
    if created_url:
        print(f"URL: {created_url}")
    source_map_path = write_assignment_source_map_entry(
        source=source,
        course_id=getattr(args, "course_id", None),
        canvas_record=canvas_record,
        command="assignments create",
        local=local,
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else source,
    )
    print(f"Wrote {source_map_path}")


def command_assignments_update(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = assignment_update_local_source(
        source,
        course_id=int(args.course_id),
        canvas_origin=canvas_origin,
    )
    resolved = resolve_source_canvas_id(
        kind="assignment",
        source=source,
        explicit_id=getattr(args, "assignment_id", None),
        frontmatter_id=local["frontmatter_id"],
        project_root=project_root,
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    assignment, lookup = resolve_assignment_for_update(
        course, local, resolved, bool(args.match_title)
    )
    canvas_before = (
        assignment_verify_canvas_record(
            course,
            assignment,
            canvas_origin=canvas_origin,
        )
        if assignment
        else None
    )
    if assignment is None:
        report = build_assignment_update_report(
            course=course,
            source=source,
            local=local,
            resolved=resolved,
            lookup=lookup,
            canvas_before=None,
            canvas_after=None,
            update_payload={},
            dry_run=bool(args.dry_run),
            readback_status="skipped",
            canvas_origin=canvas_origin,
        )
        write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
        print_assignment_update_summary(report)
        raise SystemExit(1)

    update_payload = assignment_update_payload(local["assignment"])
    report = build_assignment_update_report(
        course=course,
        source=source,
        local=local,
        resolved=resolved,
        lookup=lookup,
        canvas_before=canvas_before,
        canvas_after=None,
        update_payload=update_payload,
        dry_run=bool(args.dry_run),
        readback_status="skipped",
        canvas_origin=canvas_origin,
    )
    if args.dry_run:
        write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
        print_assignment_update_summary(report)
        return
    if report["status"] == "no_change" or not update_payload:
        write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
        print_assignment_update_summary(report)
        return

    assert canvas_before is not None
    update_assignment_from_loaded_source(
        args=args,
        source=source,
        course=course,
        project_root=project_root,
        local=local,
        resolved=resolved,
        lookup=lookup,
        assignment=assignment,
        canvas_before=canvas_before,
    )


def update_assignment_from_loaded_source(
    *,
    args: Any,
    source: Path,
    course: Any,
    project_root: Path | None,
    local: dict[str, Any],
    resolved: dict[str, Any],
    lookup: dict[str, Any],
    assignment: Any,
    canvas_before: dict[str, Any],
) -> None:
    canvas_origin = str(getattr(args, "api_url", "") or "")
    update_payload = assignment_update_payload(local["assignment"])
    update_lookup = {**lookup, "status": "matched"} if lookup["status"] == "would_update" else lookup
    planned_report = build_assignment_update_report(
        course=course,
        source=source,
        local=local,
        resolved=resolved,
        lookup=update_lookup,
        canvas_before=canvas_before,
        canvas_after=None,
        update_payload=update_payload,
        dry_run=False,
        readback_status="skipped",
        canvas_origin=canvas_origin,
    )
    print_assignment_update_summary(planned_report)
    print_mutation_banner(
        "update assignment",
        {
            "course": args.course_id,
            "assignment_id": planned_report["assignment_id"],
            "name": safe_assignment_text(
                update_payload.get("name", canvas_before.get("title") if canvas_before else "")
            ),
            "source": source,
        },
    )
    updated = assignment.edit(assignment=update_payload)
    updated_id = int(
        first_value(updated, canvas_object_to_dict(updated), "id")
        or planned_report["assignment_id"]
    )
    readback = course.get_assignment(updated_id)
    canvas_after = assignment_verify_canvas_record(
        course,
        readback,
        canvas_origin=canvas_origin,
    )
    report = build_assignment_update_report(
        course=course,
        source=source,
        local=local,
        resolved={**resolved, "id": updated_id},
        lookup=update_lookup,
        canvas_before=canvas_before,
        canvas_after=canvas_after,
        update_payload=update_payload,
        dry_run=False,
        readback_status="matches",
        canvas_origin=canvas_origin,
    )
    write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
    print_assignment_update_summary(report)
    if report["status"] != "updated":
        raise SystemExit(1)
    source_map_path = write_assignment_source_map_entry(
        source=source,
        course_id=getattr(args, "course_id", None),
        canvas_record=canvas_after,
        command="assignments update",
        local=local,
        project_root=project_root,
    )
    print(f"Wrote {source_map_path}")


def command_assignments_upsert(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    confirm = str(getattr(args, "confirm", "") or "").strip()
    if not args.dry_run and confirm not in {"create", "update"}:
        raise SystemExit("Live assignments upsert requires --confirm create or --confirm update.")
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    canvas_origin = str(getattr(args, "api_url", "") or "")
    local = assignment_update_local_source(
        source,
        course_id=int(args.course_id),
        canvas_origin=canvas_origin,
    )
    resolved = resolve_source_canvas_id(
        kind="assignment",
        source=source,
        explicit_id=getattr(args, "assignment_id", None),
        frontmatter_id=local["frontmatter_id"],
        project_root=project_root,
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    assignment, lookup = resolve_assignment_for_upsert(
        course, local, resolved, bool(args.match_title)
    )
    canvas_before = (
        assignment_verify_canvas_record(
            course,
            assignment,
            canvas_origin=canvas_origin,
        )
        if assignment
        else None
    )
    report = build_assignment_upsert_report(
        course=course,
        source=source,
        local=local,
        resolved=resolved,
        lookup=lookup,
        canvas_before=canvas_before,
        canvas_origin=canvas_origin,
    )
    print_assignment_upsert_summary(report)
    if report["status"] == "error":
        write_assignment_upsert_report_run(make_assignment_upsert_report_run(args, report), report)
        raise SystemExit(1)
    if args.dry_run:
        write_assignment_upsert_report_run(make_assignment_upsert_report_run(args, report), report)
        return
    if confirm != report["planned_action"]:
        raise SystemExit(
            f"Upsert planned action is {report['planned_action']!r}; "
            f"refusing --confirm {confirm!r}."
        )
    if report["planned_action"] == "create":
        create_assignment_from_loaded_source(args, source, local, course=course)
    elif assignment is not None:
        assert canvas_before is not None
        update_assignment_from_loaded_source(
            args=args,
            source=source,
            course=course,
            project_root=project_root,
            local=local,
            resolved=resolved,
            lookup=lookup,
            assignment=assignment,
            canvas_before=canvas_before,
        )


def load_assignment_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text, source, "Assignment")
    if "title" in metadata:
        if "name" in metadata:
            raise SystemExit("Use either 'name' or 'title', not both.")
        metadata["name"] = metadata.pop("title")
    expand_date_only_metadata(metadata, source)
    if not str(metadata.get("name", "")).strip():
        raise SystemExit("Assignment metadata must include 'name' or 'title'.")
    unknown = sorted(set(metadata) - ASSIGNMENT_METADATA_FIELDS - ASSIGNMENT_LOCAL_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    assignment = {
        key: normalize_canvas_value(value)
        for key, value in metadata.items()
        if key not in ASSIGNMENT_LOCAL_FIELDS
    }
    assignment.setdefault("published", False)
    assignment["description"] = markdown_to_html(body)
    return assignment


def assignment_update_local_source(
    source: Path,
    *,
    course_id: int | None = None,
    canvas_origin: str | None = None,
) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text, source, "Assignment")
    declared_fields = normalized_declared_assignment_fields(set(metadata))
    if "title" in metadata:
        if "name" in metadata:
            raise SystemExit("Use either 'name' or 'title', not both.")
        metadata["name"] = metadata.pop("title")
    frontmatter_id = metadata.get("assignment_id", metadata.get("canvas_id", metadata.get("id")))
    declared_canvas_url = canonical_canvas_object_url(
        metadata.get("canvas_url", metadata.get("html_url", "")),
        canvas_origin=canvas_origin,
    )
    declared_assignment_group_name = str(
        metadata.get("assignment_group_name", metadata.get("assignment_group", "")) or ""
    )
    assignment = assignment_payload_from_metadata(source, metadata, body, default_published=False)
    if "assignment_group" in assignment:
        if "assignment_group_name" in assignment:
            raise SystemExit("Use either assignment_group or assignment_group_name, not both.")
        assignment["assignment_group_name"] = assignment.pop("assignment_group")
    if "assignment_group_name" in assignment:
        assignment["assignment_group_id"] = resolve_assignment_group_id(
            str(assignment.pop("assignment_group_name")),
            explicit_id=assignment.get("assignment_group_id"),
            start=source,
        )
    return {
        "frontmatter_id": int(frontmatter_id) if frontmatter_id not in {None, ""} else None,
        "assignment": assignment,
        "canvas_url": declared_canvas_url,
        "assignment_group_name": declared_assignment_group_name,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body_text": normalized_text(html_to_text(assignment.get("description") or "")),
        "rendered_html": str(assignment.get("description") or ""),
        "declared_fields": sorted(declared_fields | {"title", "body_text"}),
        "file_links": (
            extract_canvas_file_references(
                str(assignment.get("description") or ""),
                current_course_id=course_id,
                canvas_origin=canvas_origin,
            )
            if course_id is not None
            else []
        ),
    }


def assignment_payload_from_metadata(
    source: Path, metadata: dict[str, Any], body: str, *, default_published: bool
) -> dict[str, Any]:
    expand_date_only_metadata(metadata, source)
    if not str(metadata.get("name", "")).strip():
        raise SystemExit("Assignment metadata must include 'name' or 'title'.")
    provenance_fields = {
        "assignment_id",
        "canvas_id",
        "id",
        "canvas_url",
        "html_url",
        *ASSIGNMENT_LOCAL_FIELDS,
    }
    unknown = sorted(set(metadata) - ASSIGNMENT_METADATA_FIELDS - provenance_fields)
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    assignment = {
        key: normalize_canvas_value(value)
        for key, value in metadata.items()
        if key not in provenance_fields
    }
    if default_published:
        assignment.setdefault("published", False)
    assignment["description"] = markdown_to_html(body)
    return assignment


def assignment_update_payload(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in assignment.items()
        if key in ASSIGNMENT_METADATA_FIELDS or key == "description"
    }


def assignment_verify_local_source(
    source: Path,
    assignment_id: int | None = None,
    *,
    course_id: int | None = None,
    canvas_origin: str | None = None,
) -> dict[str, Any]:
    metadata, body = parse_frontmatter(source.read_text(encoding="utf-8-sig"), source, "Assignment")
    unknown = sorted(
        set(metadata)
        - ASSIGNMENT_METADATA_FIELDS
        - ASSIGNMENT_LOCAL_FIELDS
        - {"title", "assignment_id", "canvas_id", "id", "canvas_url", "html_url"}
    )
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    declared_fields = normalized_declared_assignment_fields(set(metadata))
    expand_date_only_metadata(metadata, source)
    canvas_id = assignment_id
    if canvas_id is None:
        canvas_id = metadata.get("assignment_id", metadata.get("canvas_id", metadata.get("id")))
    if canvas_id is None or str(canvas_id).strip() == "":
        raise SystemExit(
            "Assignment verification requires --assignment-id or assignment_id front matter."
        )
    title = metadata.get("title", metadata.get("name", ""))
    rendered_html = markdown_to_html(body)
    return {
        "assignment_id": int(canvas_id),
        "canvas_url": canonical_canvas_object_url(
            metadata.get("canvas_url", metadata.get("html_url", "")),
            canvas_origin=canvas_origin,
        ),
        "title": str(title or ""),
        "points_possible": metadata.get("points_possible"),
        "due_at": metadata_text(metadata.get("due_at")),
        "unlock_at": metadata_text(metadata.get("unlock_at")),
        "lock_at": metadata_text(metadata.get("lock_at")),
        "published": metadata.get("published"),
        "assignment_group_id": metadata.get("assignment_group_id"),
        "assignment_group_name": str(
            metadata.get("assignment_group_name", metadata.get("assignment_group", "")) or ""
        ),
        "submission_types": metadata.get("submission_types"),
        "grading_type": str(metadata.get("grading_type") or ""),
        "group_category_id": metadata.get("group_category_id"),
        "allowed_extensions": metadata.get("allowed_extensions"),
        "body_text": normalized_text(html_to_text(rendered_html)),
        "rendered_html": rendered_html,
        "declared_fields": sorted(declared_fields | {"title", "body_text"}),
        "file_links": (
            extract_canvas_file_references(
                rendered_html,
                current_course_id=course_id,
                canvas_origin=canvas_origin,
            )
            if course_id is not None
            else []
        ),
    }


def assignment_verify_canvas_record(
    course: Any, assignment: Any, *, canvas_origin: str | None = None
) -> dict[str, Any]:
    payload = canvas_object_to_dict(assignment)
    group_id = first_value(assignment, payload, "assignment_group_id")
    group_name = assignment_group_name(course, group_id)
    description = str(first_value(assignment, payload, "description") or "")
    course_id = int(getattr(course, "id", 0) or payload.get("course_id") or 0)
    return {
        "id": first_value(assignment, payload, "id"),
        "title": first_value(assignment, payload, "name", "title"),
        "canvas_url": canonical_canvas_object_url(
            first_value(assignment, payload, "html_url"), canvas_origin=canvas_origin
        ),
        "points_possible": first_value(assignment, payload, "points_possible"),
        "due_at": first_value(assignment, payload, "due_at"),
        "unlock_at": first_value(assignment, payload, "unlock_at"),
        "lock_at": first_value(assignment, payload, "lock_at"),
        "published": first_value(assignment, payload, "published"),
        "assignment_group_id": group_id,
        "assignment_group_name": group_name,
        "submission_types": first_value(assignment, payload, "submission_types"),
        "grading_type": first_value(assignment, payload, "grading_type"),
        "group_category_id": first_value(assignment, payload, "group_category_id"),
        "allowed_extensions": first_value(assignment, payload, "allowed_extensions"),
        "body_text": normalized_text(html_to_text(description)),
        "description_html": description,
        "file_links": (
            extract_canvas_file_references(
                description,
                current_course_id=course_id,
                canvas_origin=canvas_origin,
            )
            if course_id
            else []
        ),
        "updated_at": first_value(assignment, payload, "updated_at"),
    }


def normalized_declared_assignment_fields(fields: set[str]) -> set[str]:
    return {
        DECLARED_FIELD_ALIASES.get(field, "canvas_url" if field == "html_url" else field)
        for field in fields
        if field not in ASSIGNMENT_PROVENANCE_FIELDS and field not in ASSIGNMENT_LOCAL_FIELDS
    }


def safe_course_record(course: Any) -> dict[str, Any]:
    payload = canvas_object_to_dict(course)
    return safe_assignment_value({
        key: payload.get(key, getattr(course, key, None))
        for key in ("id", "name", "course_code")
        if payload.get(key, getattr(course, key, None)) not in {None, ""}
    })


def safe_assignment_group_record(group: Any) -> dict[str, Any]:
    payload = canvas_object_to_dict(group)
    return safe_assignment_value({
        key: payload.get(key, getattr(group, key, None))
        for key in ("id", "name", "position", "group_weight")
        if payload.get(key, getattr(group, key, None)) not in {None, ""}
    })


def safe_file_link(link: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "reason",
        "course_id",
        "file_id",
        "canvas_url",
        "tag",
        "attributes",
        "occurrence",
        "conflicting_identities",
        "value_sha256",
        "volatile_query_present",
    }
    return {key: link[key] for key in allowed if key in link}


def safe_assignment_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    allowed = ASSIGNMENT_VERIFY_SUPPORTED_FIELDS | {"id", "updated_at", "file_links"}
    result = {
        key: (
            record.get(key)
            if key in {"canvas_url", "file_links"}
            else safe_assignment_value(record.get(key))
        )
        for key in allowed
        if key in record
    }
    result["file_links"] = [safe_file_link(link) for link in record.get("file_links") or []]
    return result


def safe_local_assignment_record(local: dict[str, Any]) -> dict[str, Any]:
    allowed = ASSIGNMENT_VERIFY_SUPPORTED_FIELDS | {
        "assignment_id",
        "declared_fields",
        "file_links",
    }
    result = {
        key: (
            local.get(key)
            if key in {"canvas_url", "file_links"}
            else safe_assignment_value(local.get(key))
        )
        for key in allowed
        if key in local
    }
    result["file_links"] = [safe_file_link(link) for link in local.get("file_links") or []]
    return result


def safe_assignment_export_extended(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "allowed_attempts",
        "allowed_extensions",
        "anonymous_grading",
        "assignment_group_id",
        "automatic_peer_reviews",
        "created_at",
        "due_at",
        "grade_group_students_individually",
        "grading_type",
        "group_category_id",
        "hide_in_gradebook",
        "id",
        "lock_at",
        "moderated_grading",
        "name",
        "omit_from_final_grade",
        "only_visible_to_overrides",
        "peer_reviews",
        "points_possible",
        "position",
        "published",
        "submission_types",
        "unlock_at",
        "updated_at",
    }
    return safe_assignment_value({key: payload.get(key) for key in allowed if key in payload})


def safe_assignment_text(value: Any) -> str:
    return SENSITIVE_ASSIGNMENT_TEXT_RE.sub(
        "[redacted-sensitive-value]", safe_error(str(value or ""))
    )


def safe_assignment_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): safe_assignment_value(item)
            for key, item in value.items()
            if not SENSITIVE_ASSIGNMENT_TEXT_RE.search(str(key))
        }
    if isinstance(value, list):
        return [safe_assignment_value(item) for item in value]
    if isinstance(value, tuple):
        return [safe_assignment_value(item) for item in value]
    if isinstance(value, str):
        return safe_assignment_text(value)
    return value


def safe_assignment_mutation_projection(
    assignment: dict[str, Any], *, course_id: int, canvas_origin: str | None
) -> dict[str, Any]:
    if not assignment:
        return {}
    result = safe_assignment_value({
        key: assignment.get(key)
        for key in ASSIGNMENT_VERIFY_SUPPORTED_FIELDS - {"title", "body_text", "canvas_url"}
        if key in assignment
    })
    if "name" in assignment:
        result["name"] = safe_assignment_value(assignment.get("name"))
    description = str(assignment.get("description") or "")
    result["body_text"] = safe_assignment_text(normalized_text(html_to_text(description)))
    result["body_sha256"] = hashlib.sha256(description.encode("utf-8")).hexdigest()
    result["file_links"] = [
        safe_file_link(link)
        for link in extract_canvas_file_references(
            description,
            current_course_id=course_id,
            canvas_origin=canvas_origin,
        )
    ]
    omitted = sorted(
        set(assignment)
        - {
            "name",
            "description",
            *(ASSIGNMENT_VERIFY_SUPPORTED_FIELDS - {"title", "body_text", "canvas_url"}),
        }
    )
    if omitted:
        result["omitted_unsafe_or_unverified_fields"] = safe_assignment_value(omitted)
    return result


def resolve_assignment_for_update(
    course: Any, local: dict[str, Any], resolved: dict[str, Any], match_title: bool
) -> tuple[Any | None, dict[str, Any]]:
    assignment_id = resolved.get("id")
    if assignment_id is not None:
        try:
            assignment = course.get_assignment(assignment_id)
        except ResourceDoesNotExist:
            return None, {
                "method": resolved["source"],
                "status": "not_found",
                "reason": f"Canvas assignment ID {assignment_id} was not found.",
            }
        return assignment, {"method": resolved["source"], "status": "matched", "reason": ""}
    if not match_title:
        return None, {
            "method": "none",
            "status": "missing_id",
            "reason": "Assignment update requires --assignment-id, assignment_id/canvas_id front matter, source-map entry, or --match-title.",
        }
    title = str(local["assignment"].get("name") or "")
    matches = []
    for assignment in course.get_assignments():
        payload = canvas_object_to_dict(assignment)
        candidate = first_value(assignment, payload, "name", "title")
        if str(candidate or "").strip() == title:
            matches.append(assignment)
    if len(matches) == 1:
        return matches[0], {"method": "title", "status": "matched", "reason": ""}
    if not matches:
        return None, {
            "method": "title",
            "status": "not_found",
            "reason": f"No Canvas assignment title matched {title!r}.",
        }
    ids = ", ".join(str(first_value(item, canvas_object_to_dict(item), "id")) for item in matches)
    return None, {
        "method": "title",
        "status": "ambiguous",
        "reason": f"Multiple Canvas assignments matched {title!r}: {ids}.",
    }


def resolve_assignment_for_upsert(
    course: Any, local: dict[str, Any], resolved: dict[str, Any], match_title: bool
) -> tuple[Any | None, dict[str, Any]]:
    assignment_id = resolved.get("id")
    if assignment_id is not None:
        try:
            assignment = course.get_assignment(assignment_id)
        except ResourceDoesNotExist:
            return None, {
                "method": resolved["source"],
                "status": "would_create",
                "reason": f"Canvas assignment ID {assignment_id} was not found.",
            }
        return assignment, {"method": resolved["source"], "status": "would_update", "reason": ""}
    if not match_title:
        return None, {
            "method": "none",
            "status": "would_create",
            "reason": "No assignment ID resolved; upsert would create a new assignment.",
        }
    title = str(local["assignment"].get("name") or "")
    matches = []
    for assignment in course.get_assignments():
        payload = canvas_object_to_dict(assignment)
        candidate = first_value(assignment, payload, "name", "title")
        if str(candidate or "").strip() == title:
            matches.append(assignment)
    if len(matches) == 1:
        return matches[0], {"method": "title", "status": "would_update", "reason": ""}
    if not matches:
        return None, {
            "method": "title",
            "status": "would_create",
            "reason": f"No Canvas assignment title matched {title!r}; upsert would create.",
        }
    ids = ", ".join(str(first_value(item, canvas_object_to_dict(item), "id")) for item in matches)
    return None, {
        "method": "title",
        "status": "ambiguous",
        "reason": f"Multiple Canvas assignments matched {title!r}: {ids}.",
    }


def assignment_group_name(course: Any, group_id: Any) -> str:
    if group_id in {"", None}:
        return ""
    try:
        groups = course.get_assignment_groups()
    except Exception:
        return ""
    for group in groups:
        payload = canvas_object_to_dict(group)
        if str(first_value(group, payload, "id")) == str(group_id):
            return str(first_value(group, payload, "name") or "")
    return ""


def first_value(obj: Any, payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None and value != "":
            return value
        value = payload.get(name)
        if value is not None and value != "":
            return value
    return ""


def metadata_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat()).replace("+00:00", "Z")
    return str(value)


DATE_ONLY_ALIASES = {
    "due_date": ("due_at", time(23, 59)),
    "unlock_date": ("unlock_at", time(0, 0)),
    "lock_date": ("lock_at", time(23, 59)),
}
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def expand_date_only_metadata(metadata: dict[str, Any], source: Path) -> None:
    for alias, (target, default_time) in DATE_ONLY_ALIASES.items():
        if alias not in metadata:
            continue
        if target in metadata and not is_blank_metadata_value(metadata.get(target)):
            raise SystemExit(f"Use either {alias} or {target}, not both.")
        value = metadata.pop(alias)
        if is_blank_metadata_value(value):
            continue
        timezone = resolve_course_timezone(source)
        day = parse_date_only_value(alias, value)
        metadata[target] = datetime.combine(day, default_time, tzinfo=timezone).isoformat(
            timespec="seconds"
        )


def parse_date_only_value(field: str, value: Any) -> date:
    if isinstance(value, datetime):
        raise SystemExit(f"{field} must be a date-only value in YYYY-MM-DD format.")
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not DATE_ONLY_RE.match(text):
        raise SystemExit(f"{field} must be a date-only value in YYYY-MM-DD format.")
    return date.fromisoformat(text)


def is_blank_metadata_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def build_assignment_verify_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    canvas_record: dict[str, Any] | None,
    fetch_error: str = "",
    fetch_status: str = "ok",
    canvas_origin: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    file_links = empty_assignment_file_link_report()
    if canvas_record is None:
        status = "mismatch" if fetch_status == "not_found" else "indeterminate"
    else:
        checks = assignment_verify_checks(local, canvas_record, include_unsupported=True)
        file_links = verify_assignment_file_links(
            course,
            local.get("file_links") or [],
            canvas_record.get("file_links") or [],
            canvas_origin=canvas_origin,
        )
        if any(check["status"] == "mismatch" for check in checks) or file_links[
            "status"
        ] == "mismatch":
            status = "mismatch"
        elif any(check["status"] == "unsupported" for check in checks) or file_links[
            "status"
        ] == "partial":
            status = "partial"
        else:
            status = "matches"
    coverage = {
        "declared": len(local.get("declared_fields") or []),
        "checked": sum(check["status"] in {"matches", "mismatch"} for check in checks),
        "unsupported": sum(check["status"] == "unsupported" for check in checks),
        "file_targets": len(local.get("file_links") or []),
    }
    return {
        "evidence_schema": "assignment-release-v1",
        "course": safe_course_record(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "assignment_id": local["assignment_id"],
        "status": status,
        "fetch_error": fetch_error,
        "fetch_status": fetch_status,
        "local": safe_local_assignment_record(local),
        "canvas": safe_assignment_record(canvas_record),
        "checks": checks,
        "file_links": file_links,
        "coverage": coverage,
    }


def empty_assignment_file_link_report() -> dict[str, Any]:
    return {
        "status": "not_checked",
        "local": [],
        "canvas": [],
        "local_file_id_counts": {},
        "canvas_file_id_counts": {},
        "files": [],
    }


def verify_assignment_file_links(
    course: Any,
    local_links: list[dict[str, Any]],
    canvas_links: list[dict[str, Any]],
    *,
    canvas_origin: str | None,
) -> dict[str, Any]:
    safe_local = [safe_file_link(link) for link in local_links]
    safe_canvas = [safe_file_link(link) for link in canvas_links]
    local_counts = Counter(
        int(link["file_id"])
        for link in local_links
        if link.get("status") == "valid" and link.get("file_id") is not None
    )
    canvas_counts = Counter(
        int(link["file_id"])
        for link in canvas_links
        if link.get("status") == "valid" and link.get("file_id") is not None
    )
    mismatch = local_counts != canvas_counts
    partial = False
    for link in [*local_links, *canvas_links]:
        link_status = link.get("status")
        if link_status == "relative_asset":
            partial = True
        elif link_status != "valid":
            mismatch = True

    folders_by_id: dict[int, str] | None = None
    files = []
    for file_id in sorted(local_counts):
        if not hasattr(course, "get_file"):
            files.append(
                {"file_id": file_id, "status": "indeterminate", "reason": "file_lookup_unavailable"}
            )
            partial = True
            continue
        try:
            file_obj = course.get_file(file_id)
        except ResourceDoesNotExist:
            files.append({"file_id": file_id, "status": "not_found"})
            mismatch = True
            continue
        except Exception as exc:  # noqa: BLE001 - retain only bounded failure classification.
            files.append(
                {
                    "file_id": file_id,
                    "status": "indeterminate",
                    "reason": safe_assignment_exception_reason(exc),
                }
            )
            partial = True
            continue
        payload = canvas_object_to_dict(file_obj)
        folder_id = first_value(file_obj, payload, "folder_id")
        display_name = str(
            first_value(file_obj, payload, "display_name", "filename") or f"file-{file_id}"
        )
        if folders_by_id is None:
            folders_by_id = safe_course_folder_names(course)
        folder_name = folders_by_id.get(int(folder_id), "") if folder_id is not None else ""
        canvas_path = f"{folder_name.rstrip('/')}/{display_name}" if folder_name else display_name
        stable_url = ""
        if canvas_origin:
            try:
                stable_url = stable_course_file_url(
                    canvas_origin, int(getattr(course, "id", 0)), file_id
                )
            except ValueError:
                partial = True
        files.append(
            {
                "file_id": file_id,
                "status": "exists" if stable_url else "indeterminate",
                "folder_id": folder_id,
                "display_name": display_name,
                "canvas_path": canvas_path,
                "canvas_url": stable_url,
            }
        )
        if not stable_url:
            partial = True
    status = "mismatch" if mismatch else "partial" if partial else "matches"
    return {
        "status": status,
        "local": safe_local,
        "canvas": safe_canvas,
        "local_file_id_counts": {str(key): value for key, value in sorted(local_counts.items())},
        "canvas_file_id_counts": {str(key): value for key, value in sorted(canvas_counts.items())},
        "files": files,
    }


def safe_course_folder_names(course: Any) -> dict[int, str]:
    if not hasattr(course, "get_folders"):
        return {}
    try:
        folders = course.get_folders()
    except Exception:  # noqa: BLE001 - file existence remains authoritative without a path label.
        return {}
    return {
        int(folder_id): str(first_value(folder, payload, "full_name") or "")
        for folder in folders
        if (payload := canvas_object_to_dict(folder))
        and (folder_id := first_value(folder, payload, "id")) is not None
    }


def safe_assignment_exception_reason(exc: Exception) -> str:
    name = type(exc).__name__.casefold()
    if "unauthorized" in name or "forbidden" in name or "access" in name:
        return "file_lookup_unauthorized"
    if "rate" in name or "throttle" in name:
        return "file_lookup_rate_limited"
    return "file_lookup_failed"


def safe_assignment_lookup_reason(exc: Exception) -> str:
    name = type(exc).__name__.casefold()
    if "unauthorized" in name or "forbidden" in name or "access" in name:
        return "assignment_lookup_unauthorized"
    if "rate" in name or "throttle" in name:
        return "assignment_lookup_rate_limited"
    return "assignment_lookup_failed"


def build_assignment_update_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    resolved: dict[str, Any],
    lookup: dict[str, Any],
    canvas_before: dict[str, Any] | None,
    canvas_after: dict[str, Any] | None,
    update_payload: dict[str, Any],
    dry_run: bool,
    readback_status: str,
    canvas_origin: str | None,
) -> dict[str, Any]:
    local_record = assignment_update_local_compare_record(local)
    before_checks = assignment_verify_checks(local_record, canvas_before) if canvas_before else []
    after_checks = assignment_verify_checks(local_record, canvas_after) if canvas_after else []
    mismatches = [check for check in before_checks if not check["matches"]]
    if lookup["status"] != "matched":
        status = "lookup_failed"
    elif canvas_after is not None:
        readback_status = (
            "matches" if all(check["matches"] for check in after_checks) else "mismatch"
        )
        status = "updated" if readback_status == "matches" else "readback_mismatch"
    elif dry_run:
        status = "would_update" if mismatches else "no_change"
    else:
        status = "no_change" if not mismatches else "planned"
    return {
        "evidence_schema": "assignment-release-v1",
        "course": safe_course_record(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "dry_run": dry_run,
        "status": status,
        "assignment_id": resolved.get("id") or first_value_from_record(canvas_before, "id"),
        "id_resolution": safe_assignment_value({
            "source": resolved.get("source"),
            "path": resolved.get("path"),
            "id": resolved.get("id"),
        }),
        "lookup": safe_assignment_value(lookup),
        "local": safe_local_assignment_record(local_record),
        "canvas_before": safe_assignment_record(canvas_before),
        "canvas_after": safe_assignment_record(canvas_after),
        "update_payload": safe_assignment_mutation_projection(
            update_payload,
            course_id=int(getattr(course, "id", 0)),
            canvas_origin=canvas_origin,
        ),
        "diff": before_checks,
        "readback": {
            "status": readback_status,
            "checks": after_checks,
        },
    }


def build_assignment_upsert_report(
    *,
    course: Any,
    source: Path,
    local: dict[str, Any],
    resolved: dict[str, Any],
    lookup: dict[str, Any],
    canvas_before: dict[str, Any] | None,
    canvas_origin: str | None,
) -> dict[str, Any]:
    local_record = assignment_update_local_compare_record(local)
    diff = assignment_verify_checks(local_record, canvas_before) if canvas_before else []
    if lookup["status"] == "would_update":
        action = "update"
        status = "would_update"
    elif lookup["status"] == "would_create":
        action = "create"
        status = "would_create"
    else:
        action = "none"
        status = "error"
    return {
        "evidence_schema": "assignment-release-v1",
        "course": safe_course_record(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "dry_run": True,
        "status": status,
        "planned_action": action,
        "assignment_id": resolved.get("id") or first_value_from_record(canvas_before, "id"),
        "id_resolution": safe_assignment_value({
            "source": resolved.get("source"),
            "path": resolved.get("path"),
            "id": resolved.get("id"),
        }),
        "lookup": safe_assignment_value(lookup),
        "local": safe_local_assignment_record(local_record),
        "canvas_before": safe_assignment_record(canvas_before),
        "create_payload": (
            safe_assignment_mutation_projection(
                local["assignment"],
                course_id=int(getattr(course, "id", 0)),
                canvas_origin=canvas_origin,
            )
            if action == "create"
            else {}
        ),
        "update_payload": (
            safe_assignment_mutation_projection(
                assignment_update_payload(local["assignment"]),
                course_id=int(getattr(course, "id", 0)),
                canvas_origin=canvas_origin,
            )
            if action == "update"
            else {}
        ),
        "diff": diff,
    }


def assignment_update_local_compare_record(local: dict[str, Any]) -> dict[str, Any]:
    assignment = local["assignment"]
    return {
        "title": assignment.get("name"),
        "points_possible": assignment.get("points_possible"),
        "due_at": assignment.get("due_at"),
        "unlock_at": assignment.get("unlock_at"),
        "lock_at": assignment.get("lock_at"),
        "published": assignment.get("published"),
        "assignment_group_id": assignment.get("assignment_group_id"),
        "assignment_group_name": local.get("assignment_group_name"),
        "canvas_url": local.get("canvas_url"),
        "submission_types": assignment.get("submission_types"),
        "grading_type": assignment.get("grading_type"),
        "group_category_id": assignment.get("group_category_id"),
        "allowed_extensions": assignment.get("allowed_extensions"),
        "body_text": local["body_text"],
        "declared_fields": local.get("declared_fields") or [],
        "file_links": local.get("file_links") or [],
    }


def assignment_source_map_fields(local: dict[str, Any]) -> dict[str, Any]:
    return safe_assignment_value({
        key: value
        for key, value in assignment_update_local_compare_record(local).items()
        if key in ASSIGNMENT_VERIFY_SUPPORTED_FIELDS and value is not None and value != ""
    })


def write_assignment_source_map_entry(
    *,
    source: Path,
    course_id: int | None,
    canvas_record: dict[str, Any],
    command: str,
    local: dict[str, Any],
    project_root: Path | None,
) -> Path:
    return write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=course_id,
        canvas={
            "id": canvas_record.get("id"),
            "url": canvas_record.get("canvas_url") or "",
            "updated_at": canvas_record.get("updated_at") or "",
        },
        command=command,
        fields=assignment_source_map_fields(local),
        body_sha256=local["body_sha256"],
        project_root=project_root,
    )


def first_value_from_record(record: dict[str, Any] | None, key: str) -> Any:
    if not record:
        return None
    return record.get(key)


def assignment_verify_checks(
    local: dict[str, Any],
    canvas_record: dict[str, Any],
    *,
    include_unsupported: bool = False,
) -> list[dict[str, Any]]:
    declared = set(local.get("declared_fields") or [])
    values = {
        field: (local.get(field), canvas_record.get(field))
        for field in ASSIGNMENT_VERIFY_SUPPORTED_FIELDS
    }
    checks = []
    for field in sorted(values):
        local_value, canvas_value = values[field]
        if declared:
            if field not in declared:
                continue
        elif local_value is None or local_value == "":
            continue
        checks.append(verify_check(field, local_value, canvas_value))
    if include_unsupported:
        for field in sorted(
            declared - ASSIGNMENT_VERIFY_SUPPORTED_FIELDS - ASSIGNMENT_PROVENANCE_FIELDS
        ):
            checks.append(
                {
                    "field": field,
                    "status": "unsupported",
                    "matches": False,
                    "local": None,
                    "canvas": None,
                    "reason": "declared_field_not_verified",
                }
            )
    return checks


def verify_check(field: str, local_value: Any, canvas_value: Any) -> dict[str, Any]:
    local = comparable_field_value(field, local_value)
    canvas = comparable_field_value(field, canvas_value)
    matches = local == canvas
    return {
        "field": field,
        "status": "matches" if matches else "mismatch",
        "matches": matches,
        "local": safe_assignment_value(local),
        "canvas": safe_assignment_value(canvas),
    }


def comparable_field_value(field: str, value: Any) -> Any:
    if field == "allowed_extensions":
        if value is None or value == "":
            return []
        if isinstance(value, str):
            value = [item for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return sorted({str(item).strip().removeprefix(".").casefold() for item in value})
    return comparable_value(value)


def comparable_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    if isinstance(value, tuple):
        return sorted(str(item) for item in value)
    if isinstance(value, (int, float)):
        return value
    text = normalized_text(str(value)).replace("+00:00", "Z")
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def normalized_text(value: str) -> str:
    return " ".join(value.split())


def make_assignment_verify_report_run(args: Any, report: dict[str, Any]) -> ReportRun | None:
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
        command="assignments verify",
        slug=report_slug or "assignments-verify",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"])],
        private_data=False,
    )


def write_assignment_verify_report_run(
    report_run: ReportRun | None, report: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        json_path = report_run.write_json("assignments-verify.json", report)
        md_path = report_run.write_text(
            "assignments-verify.md", render_assignment_verify_markdown(report)
        )
        manifest_path = report_run.finish("success" if report["status"] == "matches" else "failed")
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def make_assignment_update_report_run(args: Any, report: dict[str, Any]) -> ReportRun | None:
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
        command="assignments update",
        slug=report_slug or "assignments-update",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"])],
        private_data=False,
    )


def write_assignment_update_report_run(
    report_run: ReportRun | None, report: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        json_path = report_run.write_json("assignments-update.json", report)
        md_path = report_run.write_text(
            "assignments-update.md", render_assignment_update_markdown(report)
        )
        manifest_status = (
            "success" if report["status"] in {"would_update", "no_change", "updated"} else "failed"
        )
        manifest_path = report_run.finish(manifest_status)
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def make_assignment_upsert_report_run(args: Any, report: dict[str, Any]) -> ReportRun | None:
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
        command="assignments upsert",
        slug=report_slug or "assignments-upsert",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"])],
        private_data=False,
    )


def write_assignment_upsert_report_run(
    report_run: ReportRun | None, report: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        json_path = report_run.write_json("assignments-upsert.json", report)
        md_path = report_run.write_text(
            "assignments-upsert.md", render_assignment_upsert_markdown(report)
        )
        manifest_path = report_run.finish(
            "success" if report["status"] in {"would_create", "would_update"} else "failed"
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def render_assignment_verify_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Assignments Verify",
        "",
        f"- Status: `{report['status']}`",
        f"- Source: `{report['source']}`",
        f"- Assignment ID: `{report['assignment_id']}`",
        "",
        "| Field | Local | Canvas | Status |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        status = check.get("status") or ("matches" if check["matches"] else "mismatch")
        lines.append(
            f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
        )
    lines.extend(
        [
            "",
            "## Canvas File Targets",
            "",
            f"- Status: `{report['file_links']['status']}`",
            f"- Local targets: `{sum(report['file_links']['local_file_id_counts'].values())}`",
            f"- Canvas targets: `{sum(report['file_links']['canvas_file_id_counts'].values())}`",
        ]
    )
    if report.get("fetch_status") == "not_found":
        lines.extend(["", "Canvas assignment was not found by ID."])
    if report.get("fetch_error"):
        lines.extend(["", f"Fetch error: `{report['fetch_error']}`"])
    return "\n".join(lines) + "\n"


def render_assignment_update_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Assignments Update",
        "",
        f"- Status: `{report['status']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Source: `{report['source']}`",
        f"- Assignment ID: `{report.get('assignment_id') or ''}`",
        f"- ID resolution: `{report['id_resolution']['source']}`",
        f"- Lookup: `{report['lookup']['status']}` via `{report['lookup']['method']}`",
    ]
    if report["lookup"].get("reason"):
        lines.append(f"- Reason: {report['lookup']['reason']}")
    lines.extend(
        [
            "",
            "## Planned Diff",
            "",
            "| Field | Local | Canvas before | Status |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report["diff"]:
        for check in report["diff"]:
            status = "matches" if check["matches"] else "would change"
            lines.append(
                f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
            )
    else:
        lines.append("| | | | |")
    if report["readback"]["checks"]:
        lines.extend(
            [
                "",
                "## Readback",
                "",
                f"- Status: `{report['readback']['status']}`",
                "",
                "| Field | Local | Canvas after | Status |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in report["readback"]["checks"]:
            status = "matches" if check["matches"] else "mismatch"
            lines.append(
                f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
            )
    return "\n".join(lines) + "\n"


def render_assignment_upsert_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Assignments Upsert",
        "",
        f"- Status: `{report['status']}`",
        f"- Planned action: `{report['planned_action']}`",
        f"- Dry run: `{report['dry_run']}`",
        f"- Source: `{report['source']}`",
        f"- Assignment ID: `{report.get('assignment_id') or ''}`",
        f"- ID resolution: `{report['id_resolution']['source']}`",
        f"- Lookup: `{report['lookup']['status']}` via `{report['lookup']['method']}`",
    ]
    if report["lookup"].get("reason"):
        lines.append(f"- Reason: {report['lookup']['reason']}")
    if report["planned_action"] == "update":
        lines.extend(
            [
                "",
                "## Planned Update Diff",
                "",
                "| Field | Local | Canvas before | Status |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in report["diff"]:
            status = "matches" if check["matches"] else "would change"
            lines.append(
                f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
            )
    elif report["planned_action"] == "create":
        lines.extend(
            [
                "",
                "## Planned Create",
                "",
                "| Field | Value |",
                "| --- | --- |",
            ]
        )
        for key, value in sorted(report["local"].items()):
            if value is not None and value != "":
                lines.append(f"| {key} | `{value}` |")
    return "\n".join(lines) + "\n"


def print_assignment_verify_summary(report: dict[str, Any]) -> None:
    print(f"Assignment verify: {report['status']}")
    for check in report["checks"]:
        marker = str(check.get("status") or ("matches" if check["matches"] else "mismatch")).upper()
        print(f"  {check['field']}: {marker}")
    print(f"  file targets: {report['file_links']['status'].upper()}")


def print_assignment_update_summary(report: dict[str, Any]) -> None:
    print(f"Assignment update: {report['status']}")
    if report["lookup"].get("reason"):
        print(f"  {report['lookup']['reason']}")
    for check in report["diff"]:
        marker = "OK" if check["matches"] else "CHANGE"
        print(f"  {check['field']}: {marker}")
    if report["readback"]["status"] != "skipped":
        print(f"  readback: {report['readback']['status']}")


def print_assignment_upsert_summary(report: dict[str, Any]) -> None:
    print(f"Assignment upsert: {report['status']}")
    print(f"  planned action: {report['planned_action']}")
    if report["lookup"].get("reason"):
        print(f"  {report['lookup']['reason']}")
    for check in report["diff"]:
        marker = "OK" if check["matches"] else "CHANGE"
        print(f"  {check['field']}: {marker}")
