"""Canvas grade posting and verification operations."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from danvas.auth import canvas_from_args
from danvas.utils import print_mutation_banner


def command_grades_post(args: Any) -> None:
    rows = load_grade_rows(Path(args.grades_csv))
    if args.dry_run:
        print("Dry run - no grades posted:")
        for row in rows:
            print(
                f"  {row.get('Name') or row['CanvasID']} (CanvasID {row['CanvasID']}): {row['Grade']}"
            )
        return
    print_mutation_banner(
        "post grades",
        {
            "course": args.course_id,
            "assignment": args.assignment_id,
            "rows": len(rows),
            "comments": sum(1 for row in rows if row.get("Comment", "").strip()),
        },
    )
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    success = skipped = failed = 0
    for row in rows:
        canvas_id = int(row["CanvasID"])
        grade = row["Grade"].strip()
        comment = row.get("Comment", "").strip()
        label = f"{row.get('Name') or canvas_id} (CanvasID {canvas_id})"
        try:
            submission = assignment.get_submission(canvas_id, include=["submission_comments"])
            has_grade = grade_matches(submission, grade)
            has_comment = not comment or comment_exists(submission, comment)
            if has_grade and has_comment:
                skipped += 1
                print(f"  {label}: already posted")
                continue
            kwargs: dict[str, Any] = {}
            if not has_grade:
                kwargs["submission"] = {"posted_grade": grade}
            if not has_comment:
                kwargs["comment"] = {"text_comment": comment}
            submission.edit(**kwargs)
            success += 1
            print(f"  {label}: posted")
            time.sleep(args.sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {label}: FAILED {type(exc).__name__}: {exc}")
    print(f"Done. Posted: {success}, Already present: {skipped}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


def command_grades_verify(args: Any) -> None:
    rows = load_grade_rows(Path(args.grades_csv))
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    failures = 0
    for row in rows:
        submission = assignment.get_submission(
            int(row["CanvasID"]), include=["submission_comments"]
        )
        grade_ok = grade_matches(submission, row["Grade"].strip())
        comment = row.get("Comment", "").strip()
        comment_ok = not comment or comment_exists(submission, comment)
        status = "OK" if grade_ok and comment_ok else "MISMATCH"
        print(f"  {row.get('Name') or row['CanvasID']}: {status}")
        failures += 0 if status == "OK" else 1
    if failures:
        raise SystemExit(1)


def load_grade_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Grades CSV not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for column in ("CanvasID", "Grade"):
            if column not in headers:
                raise SystemExit(f"Grades CSV must include {column}. Found: {', '.join(headers)}")
        return [row for row in reader if row.get("CanvasID") and row.get("Grade")]


def grade_matches(submission: Any, expected: str) -> bool:
    expected = expected.strip()
    for value in (getattr(submission, "score", None), getattr(submission, "grade", None)):
        if value is None:
            continue
        try:
            if abs(float(value) - float(expected)) < 0.0001:
                return True
        except ValueError:
            if str(value).strip() == expected:
                return True
    return False


def comment_exists(submission: Any, expected: str) -> bool:
    for comment in getattr(submission, "submission_comments", []) or []:
        text = (
            comment.get("comment", "")
            if isinstance(comment, dict)
            else getattr(comment, "comment", "")
        )
        if str(text).strip() == expected.strip():
            return True
    return False
