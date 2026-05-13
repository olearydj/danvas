"""Canvas course and roster operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
                "Email": user.get("login_id", ""),
                "SIS_ID": user.get("sis_user_id", ""),
            }
        )
    rows.sort(key=lambda row: row["Name"])
    write_rows(Path(args.output), rows, ["CanvasID", "Name", "Email", "SIS_ID"])
    print(f"Wrote {len(rows)} students to {args.output}")
