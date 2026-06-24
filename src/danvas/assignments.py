"""Canvas assignment import/export operations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from canvasapi.exceptions import ResourceDoesNotExist

from danvas.auth import canvas_from_args
from danvas.config import resolve_assignment_group_id, resolve_course_timezone
from danvas.frontmatter import markdown_to_html, normalize_canvas_value, parse_frontmatter
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.source_map import resolve_source_canvas_id, write_source_map_entry
from danvas.utils import (
    canvas_object_to_dict,
    html_to_text,
    print_mutation_banner,
    slugify,
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


def command_assignments_verify(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    local = assignment_verify_local_source(source, getattr(args, "assignment_id", None))
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    canvas_record: dict[str, Any] | None = None
    fetch_error = ""
    try:
        assignment = course.get_assignment(local["assignment_id"])
        canvas_record = assignment_verify_canvas_record(course, assignment)
    except ResourceDoesNotExist as exc:
        fetch_error = str(exc)
    report = build_assignment_verify_report(
        course=course,
        source=source,
        local=local,
        canvas_record=canvas_record,
        fetch_error=fetch_error,
    )
    write_assignment_verify_report_run(make_assignment_verify_report_run(args, report), report)
    print_assignment_verify_summary(report)
    if report["status"] != "matches":
        raise SystemExit(1)


def command_assignments_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    course_payload = canvas_object_to_dict(course)
    groups = {
        int(group.id): canvas_object_to_dict(group) for group in course.get_assignment_groups()
    }
    rows = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        payload = canvas_object_to_dict(assignment)
        group = groups.get(int(getattr(assignment, "assignment_group_id", 0) or 0), {})
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
            "submission_types": ",".join(getattr(assignment, "submission_types", []) or []),
            "description_text": html_to_text(getattr(assignment, "description", "")),
            "description_html": getattr(assignment, "description", "") or "",
        }
        if args.full:
            row["assignment"] = payload
            row["assignment_group"] = group
        rows.append(row)
    rows.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    output = Path(args.output)
    fmt = resolve_format(output, args.format)
    if fmt == "csv":
        write_rows(
            output,
            rows,
            [
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
                "description_html",
            ],
        )
    elif fmt == "markdown":
        write_assignments_markdown(output, course_payload, groups, rows)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} assignments to {output}")


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
        metadata = {
            key: row[key] for key in row if key not in {"description_html", "description_text"}
        }
        text = "---\n" + json.dumps(metadata, indent=2, ensure_ascii=False) + "\n---\n\n"
        text += row["description_text"] or row["description_html"] or ""
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
        print(json.dumps(assignment, indent=2, ensure_ascii=False))
        return
    print_mutation_banner(
        "create assignment",
        {
            "course": args.course_id,
            "name": assignment.get("name", ""),
            "published": assignment.get("published", False),
            "source": source,
        },
    )
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    created = course.create_assignment(assignment)
    created_id = int(first_value(created, canvas_object_to_dict(created), "id"))
    readback = course.get_assignment(created_id)
    canvas_record = assignment_verify_canvas_record(course, readback)
    print(f"Created assignment: {created.name} (ID {created.id})")
    if getattr(created, "html_url", None):
        print(f"URL: {created.html_url}")
    local = assignment_update_local_source(source)
    source_map_path = write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=getattr(args, "course_id", None),
        canvas={
            "id": created_id,
            "url": canvas_record.get("canvas_url") or getattr(created, "html_url", "") or "",
            "updated_at": canvas_record.get("assignment", {}).get("updated_at") or "",
        },
        command="assignments create",
        fields=assignment_source_map_fields(local),
        body_sha256=local["body_sha256"],
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else source,
    )
    print(f"Wrote {source_map_path}")


def command_assignments_update(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    local = assignment_update_local_source(source)
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
    canvas_before = assignment_verify_canvas_record(course, assignment) if assignment else None
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
    )
    if args.dry_run:
        write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
        print_assignment_update_summary(report)
        return
    if report["status"] == "no_change" or not update_payload:
        write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
        print_assignment_update_summary(report)
        return

    print_assignment_update_summary(report)
    print_mutation_banner(
        "update assignment",
        {
            "course": args.course_id,
            "assignment_id": report["assignment_id"],
            "name": update_payload.get("name", canvas_before.get("title") if canvas_before else ""),
            "source": source,
        },
    )
    updated = assignment.edit(assignment=update_payload)
    updated_id = int(
        first_value(updated, canvas_object_to_dict(updated), "id") or report["assignment_id"]
    )
    readback = course.get_assignment(updated_id)
    canvas_after = assignment_verify_canvas_record(course, readback)
    report = build_assignment_update_report(
        course=course,
        source=source,
        local=local,
        resolved={**resolved, "id": updated_id},
        lookup=lookup,
        canvas_before=canvas_before,
        canvas_after=canvas_after,
        update_payload=update_payload,
        dry_run=False,
        readback_status="matches",
    )
    write_assignment_update_report_run(make_assignment_update_report_run(args, report), report)
    print_assignment_update_summary(report)
    if report["status"] != "updated":
        raise SystemExit(1)
    source_map_path = write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=getattr(args, "course_id", None),
        canvas={
            "id": updated_id,
            "url": canvas_after.get("canvas_url") or "",
            "updated_at": canvas_after.get("assignment", {}).get("updated_at") or "",
        },
        command="assignments update",
        fields=assignment_source_map_fields(local),
        body_sha256=local["body_sha256"],
        project_root=project_root,
    )
    print(f"Wrote {source_map_path}")


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
    unknown = sorted(set(metadata) - ASSIGNMENT_METADATA_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    assignment = {key: normalize_canvas_value(value) for key, value in metadata.items()}
    assignment.setdefault("published", False)
    assignment["description"] = markdown_to_html(body)
    return assignment


def assignment_update_local_source(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text, source, "Assignment")
    if "title" in metadata:
        if "name" in metadata:
            raise SystemExit("Use either 'name' or 'title', not both.")
        metadata["name"] = metadata.pop("title")
    frontmatter_id = metadata.get("assignment_id", metadata.get("canvas_id", metadata.get("id")))
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
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body_text": normalized_text(html_to_text(assignment.get("description") or "")),
    }


def assignment_payload_from_metadata(
    source: Path, metadata: dict[str, Any], body: str, *, default_published: bool
) -> dict[str, Any]:
    expand_date_only_metadata(metadata, source)
    if not str(metadata.get("name", "")).strip():
        raise SystemExit("Assignment metadata must include 'name' or 'title'.")
    provenance_fields = {"assignment_id", "canvas_id", "id", "canvas_url", "html_url"}
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
    source: Path, assignment_id: int | None = None
) -> dict[str, Any]:
    metadata, body = parse_frontmatter(source.read_text(encoding="utf-8-sig"), source, "Assignment")
    expand_date_only_metadata(metadata, source)
    canvas_id = assignment_id
    if canvas_id is None:
        canvas_id = metadata.get("assignment_id", metadata.get("canvas_id", metadata.get("id")))
    if canvas_id is None or str(canvas_id).strip() == "":
        raise SystemExit(
            "Assignment verification requires --assignment-id or assignment_id front matter."
        )
    title = metadata.get("title", metadata.get("name", ""))
    return {
        "assignment_id": int(canvas_id),
        "canvas_url": str(metadata.get("canvas_url", metadata.get("html_url", "")) or ""),
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
        "body_text": normalized_text(html_to_text(markdown_to_html(body))),
    }


def assignment_verify_canvas_record(course: Any, assignment: Any) -> dict[str, Any]:
    payload = canvas_object_to_dict(assignment)
    group_id = first_value(assignment, payload, "assignment_group_id")
    group_name = assignment_group_name(course, group_id)
    return {
        "id": first_value(assignment, payload, "id"),
        "title": first_value(assignment, payload, "name", "title"),
        "canvas_url": first_value(assignment, payload, "html_url"),
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
        "body_text": normalized_text(
            html_to_text(first_value(assignment, payload, "description") or "")
        ),
        "assignment": payload,
    }


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
) -> dict[str, Any]:
    checks = []
    if canvas_record is None:
        status = "not_found"
    else:
        checks = assignment_verify_checks(local, canvas_record)
        status = "matches" if all(check["matches"] for check in checks) else "mismatch"
    return {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "assignment_id": local["assignment_id"],
        "status": status,
        "fetch_error": fetch_error,
        "local": local,
        "canvas": canvas_record or {},
        "checks": checks,
    }


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
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "dry_run": dry_run,
        "status": status,
        "assignment_id": resolved.get("id") or first_value_from_record(canvas_before, "id"),
        "id_resolution": {
            "source": resolved.get("source"),
            "path": resolved.get("path"),
            "id": resolved.get("id"),
        },
        "lookup": lookup,
        "local": local_record,
        "canvas_before": canvas_before or {},
        "canvas_after": canvas_after or {},
        "update_payload": update_payload,
        "diff": before_checks,
        "readback": {
            "status": readback_status,
            "checks": after_checks,
        },
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
        "submission_types": assignment.get("submission_types"),
        "grading_type": assignment.get("grading_type"),
        "group_category_id": assignment.get("group_category_id"),
        "body_text": local["body_text"],
    }


def assignment_source_map_fields(local: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in assignment_update_local_compare_record(local).items()
        if value is not None and value != ""
    }


def first_value_from_record(record: dict[str, Any] | None, key: str) -> Any:
    if not record:
        return None
    return record.get(key)


def assignment_verify_checks(
    local: dict[str, Any], canvas_record: dict[str, Any]
) -> list[dict[str, Any]]:
    checks = [
        verify_check("title", local.get("title"), canvas_record.get("title")),
        verify_check("canvas_url", local.get("canvas_url"), canvas_record.get("canvas_url")),
        verify_check(
            "points_possible", local.get("points_possible"), canvas_record.get("points_possible")
        ),
        verify_check("due_at", local.get("due_at"), canvas_record.get("due_at")),
        verify_check("unlock_at", local.get("unlock_at"), canvas_record.get("unlock_at")),
        verify_check("lock_at", local.get("lock_at"), canvas_record.get("lock_at")),
        verify_check("published", local.get("published"), canvas_record.get("published")),
        verify_check(
            "assignment_group_id",
            local.get("assignment_group_id"),
            canvas_record.get("assignment_group_id"),
        ),
        verify_check(
            "assignment_group_name",
            local.get("assignment_group_name"),
            canvas_record.get("assignment_group_name"),
        ),
        verify_check(
            "submission_types",
            local.get("submission_types"),
            canvas_record.get("submission_types"),
        ),
        verify_check("grading_type", local.get("grading_type"), canvas_record.get("grading_type")),
        verify_check(
            "group_category_id",
            local.get("group_category_id"),
            canvas_record.get("group_category_id"),
        ),
        verify_check("body_text", local.get("body_text"), canvas_record.get("body_text")),
    ]
    return [check for check in checks if has_local_expectation(check)]


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


def has_local_expectation(check: dict[str, Any]) -> bool:
    return check["local"] is not None and check["local"] != ""


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
        status = "matches" if check["matches"] else "mismatch"
        lines.append(
            f"| {check['field']} | `{check['local']}` | `{check['canvas']}` | `{status}` |"
        )
    if report["status"] == "not_found":
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


def print_assignment_verify_summary(report: dict[str, Any]) -> None:
    print(f"Assignment verify: {report['status']}")
    for check in report["checks"]:
        marker = "OK" if check["matches"] else "MISMATCH"
        print(f"  {check['field']}: {marker}")


def print_assignment_update_summary(report: dict[str, Any]) -> None:
    print(f"Assignment update: {report['status']}")
    if report["lookup"].get("reason"):
        print(f"  {report['lookup']['reason']}")
    for check in report["diff"]:
        marker = "OK" if check["matches"] else "CHANGE"
        print(f"  {check['field']}: {marker}")
    if report["readback"]["status"] != "skipped":
        print(f"  readback: {report['readback']['status']}")
