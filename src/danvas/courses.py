"""Canvas course and roster operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from danvas.artifacts import (
    resolve_private_path,
    warn_if_external_private_path,
    write_private_rows,
)
from danvas.auth import canvas_from_args
from danvas.utils import write_rows


def command_courses(args: Any) -> None:
    canvas = canvas_from_args(args)
    user = canvas.get_current_user()
    rows = []
    for course in user.get_courses(enrollment_state="active"):
        rows.append(
            {
                "id": getattr(course, "id", ""),
                "name": getattr(course, "name", ""),
                "course_code": getattr(course, "course_code", ""),
                "start_at": getattr(course, "start_at", ""),
                "end_at": getattr(course, "end_at", ""),
            }
        )
    rows.sort(key=lambda row: (str(row["course_code"]), str(row["name"])))
    write_rows(Path(args.output), rows, ["id", "name", "course_code", "start_at", "end_at"])
    print(f"Wrote {len(rows)} courses to {args.output}")


def command_roster(args: Any) -> None:
    resolved = resolve_private_path(
        explicit=getattr(args, "output", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative="roster.csv",
        option_name="--output",
    )
    warn_if_external_private_path(resolved)
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    enrollments = course.get_enrollments(type=[args.enrollment_type], state=["active"])
    rows = []
    for enrollment in enrollments:
        user = enrollment.user
        rows.append(
            {
                "CanvasID": user["id"],
                "Name": user.get("sortable_name", user.get("name", "")),
                "LoginID": user.get("login_id", ""),
                "SIS_ID": user.get("sis_user_id", ""),
            }
        )
    rows.sort(key=lambda row: row["Name"])
    schema = getattr(args, "schema", "v2")
    if schema == "legacy-v1":
        print(
            "WARNING: roster schema legacy-v1 labels Canvas login_id as Email; migrate to "
            "--schema v2."
        )
        rows = [
            {
                "CanvasID": row["CanvasID"],
                "Name": row["Name"],
                "Email": row["LoginID"],
                "SIS_ID": row["SIS_ID"],
            }
            for row in rows
        ]
        fields = ["CanvasID", "Name", "Email", "SIS_ID"]
    else:
        fields = ["CanvasID", "Name", "LoginID", "SIS_ID"]
    try:
        write_private_rows(
            resolved.path,
            rows,
            fields,
            command="roster",
        )
    except FileExistsError as exc:
        raise SystemExit(
            f"Refusing to overwrite existing private roster output: {resolved.path}"
        ) from exc
    print(f"Wrote {len(rows)} private roster rows")
    print(f"Private artifact: {resolved.path}")
