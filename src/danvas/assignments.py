"""Canvas assignment import/export operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from danvas.auth import canvas_from_args
from danvas.config import resolve_assignment_group_id
from danvas.frontmatter import markdown_to_html, normalize_canvas_value, parse_frontmatter
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
    "vericite_enabled",
}


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
    print(f"Created assignment: {created.name} (ID {created.id})")
    if getattr(created, "html_url", None):
        print(f"URL: {created.html_url}")


def load_assignment_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text, source, "Assignment")
    if "title" in metadata:
        if "name" in metadata:
            raise SystemExit("Use either 'name' or 'title', not both.")
        metadata["name"] = metadata.pop("title")
    if not str(metadata.get("name", "")).strip():
        raise SystemExit("Assignment metadata must include 'name' or 'title'.")
    unknown = sorted(set(metadata) - ASSIGNMENT_METADATA_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    assignment = {key: normalize_canvas_value(value) for key, value in metadata.items()}
    assignment.setdefault("published", False)
    assignment["description"] = markdown_to_html(body)
    return assignment
