"""Canvas grade posting, cleanup, rollback, and verification operations."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any

from danvas.auth import canvas_from_args
from danvas.reports import safe_error
from danvas.utils import mark_private, print_mutation_banner, write_json, write_rows

DEDUCTION_RE = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*(?:-|\s)?points?\s+additional\s+deduction\b"
)
ROLLBACK_FIELDS = [
    "CanvasID",
    "Name",
    "OriginalGrade",
    "OriginalScore",
    "OriginalCommentsJSON",
]


def command_grades_post(args: Any) -> None:
    source = Path(args.grades_csv)
    rows = load_grade_rows(source)
    if getattr(args, "offline_preview", False):
        print_offline_preview(rows)
        return

    try:
        canvas = canvas_from_args(args)
        assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
        current_user_id = current_user_id_for(canvas) if needs_comment_ownership(rows) else None
        plan = build_grade_post_plan(
            assignment,
            rows,
            expected_assignment_title=getattr(args, "expected_assignment_title", None),
            current_user_id=current_user_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Grade preflight failed: {safe_error(str(exc))}") from exc
    print_grade_plan(plan, dry_run=bool(args.dry_run))
    fail_for_blocked_plan(plan)
    if args.dry_run:
        return

    rollback_paths = write_grade_rollback(
        source,
        plan,
        rollback_dir=Path(args.rollback_dir) if getattr(args, "rollback_dir", None) else None,
    )
    print_mutation_banner(
        "post grades",
        {
            "course": args.course_id,
            "assignment": args.assignment_id,
            "assignment_title": plan["assignment_title"],
            "rows": len(rows),
            "rollback": rollback_paths[0],
        },
    )
    apply_grade_post_plan(assignment, plan, sleep_seconds=args.sleep_seconds)


def command_grades_clear(args: Any) -> None:
    source = Path(args.grades_csv)
    rows = load_clear_rows(source)
    try:
        canvas = canvas_from_args(args)
        assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
        current_user_id = current_user_id_for(canvas)
        plan = build_grade_clear_plan(
            assignment,
            rows,
            expected_assignment_title=getattr(args, "expected_assignment_title", None),
            current_user_id=current_user_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Grade-clear preflight failed: {safe_error(str(exc))}") from exc
    print_grade_plan(plan, dry_run=bool(args.dry_run))
    fail_for_blocked_plan(plan)
    if args.dry_run:
        return

    rollback_paths = write_grade_rollback(
        source,
        plan,
        rollback_dir=Path(args.rollback_dir) if getattr(args, "rollback_dir", None) else None,
    )
    print_mutation_banner(
        "clear grades/comments",
        {
            "course": args.course_id,
            "assignment": args.assignment_id,
            "assignment_title": plan["assignment_title"],
            "rows": len(rows),
            "rollback": rollback_paths[0],
        },
    )
    apply_grade_clear_plan(assignment, plan, sleep_seconds=args.sleep_seconds)


def command_grades_comments(args: Any) -> None:
    canvas = canvas_from_args(args)
    current_user_id = current_user_id_for(canvas)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    submission = assignment.get_submission(args.canvas_id, include=["submission_comments"])
    payload = {
        "course_id": args.course_id,
        "assignment_id": args.assignment_id,
        "assignment_title": str(getattr(assignment, "name", "") or ""),
        "canvas_id": args.canvas_id,
        "comments": [
            {**comment_record(comment), "owned_by_current_user": comment_author_id(comment) == current_user_id}
            for comment in submission_comments(submission)
        ],
    }
    output = Path(args.output)
    if output.exists() and not getattr(args, "overwrite", False):
        raise SystemExit(f"Refusing to overwrite existing output: {output}")
    write_json(output, payload)
    mark_private(output)
    print(f"Wrote {output}")


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


def build_grade_post_plan(
    assignment: Any,
    rows: list[dict[str, str]],
    *,
    expected_assignment_title: str | None,
    current_user_id: int | None,
) -> dict[str, Any]:
    title = str(getattr(assignment, "name", "") or "")
    blockers = assignment_title_blockers(title, expected_assignment_title)
    actions = []
    for row in rows:
        canvas_id = int(row["CanvasID"])
        submission = assignment.get_submission(canvas_id, include=["submission_comments"])
        action = base_action(row, submission)
        proposed = row["Grade"].strip()
        action["proposed_grade"] = proposed
        action["grade_change"] = not grade_matches(submission, proposed)
        expected = row.get("ExpectedCurrentGrade", "").strip()
        if expected and not grade_matches(submission, expected):
            action["blockers"].append(
                f"Expected current grade {expected!r}, found {current_grade(submission)!r}."
            )
        comment = row.get("Comment", "").strip()
        comment_action = (row.get("CommentAction") or ("append" if comment else "none")).strip().lower()
        action["comment_action"] = comment_action
        action["comment"] = comment
        if comment_action not in {"none", "append", "replace_exact"}:
            action["blockers"].append(f"Unsupported CommentAction {comment_action!r}.")
        elif comment_action == "append":
            action["comment_change"] = bool(comment) and not comment_exists(submission, comment)
        elif comment_action == "replace_exact":
            target = resolve_owned_comment(
                submission,
                current_user_id=current_user_id,
                target_comment_id=row.get("CommentID", ""),
                exact_text=row.get("ExpectedComment", ""),
            )
            if isinstance(target, str):
                action["blockers"].append(target)
            elif not comment:
                action["blockers"].append("replace_exact requires Comment text.")
            else:
                action["target_comment"] = comment_record(target)
                action["comment_change"] = comment_text(target).strip() != comment
        check_deduction_consistency(action, submission, proposed, comment)
        actions.append(action)
    return assignment_plan(assignment, title, actions, blockers)


def build_grade_clear_plan(
    assignment: Any,
    rows: list[dict[str, str]],
    *,
    expected_assignment_title: str | None,
    current_user_id: int,
) -> dict[str, Any]:
    title = str(getattr(assignment, "name", "") or "")
    blockers = assignment_title_blockers(title, expected_assignment_title)
    actions = []
    for row in rows:
        canvas_id = int(row["CanvasID"])
        submission = assignment.get_submission(canvas_id, include=["submission_comments"])
        action = base_action(row, submission)
        expected = row.get("ExpectedCurrentGrade", "").strip()
        if expected and not grade_matches(submission, expected):
            action["blockers"].append(
                f"Expected current grade {expected!r}, found {current_grade(submission)!r}."
            )
        action["clear_grade"] = parse_bool(row.get("ClearGrade", "true"), default=True)
        action["proposed_grade"] = "" if action["clear_grade"] else current_grade(submission)
        action["grade_change"] = action["clear_grade"] and current_grade(submission) not in {None, ""}
        comment_id = row.get("CommentID", "").strip()
        exact_text = row.get("Comment", "").strip()
        if comment_id or exact_text:
            target = resolve_owned_comment(
                submission,
                current_user_id=current_user_id,
                target_comment_id=comment_id,
                exact_text=exact_text,
            )
            if isinstance(target, str):
                action["blockers"].append(target)
            else:
                action["target_comment"] = comment_record(target)
                action["comment_action"] = "delete_exact"
                action["comment_change"] = True
        else:
            action["comment_action"] = "none"
        if not action["grade_change"] and not action.get("comment_change"):
            action["already_applied"] = True
        actions.append(action)
    return assignment_plan(assignment, title, actions, blockers)


def assignment_plan(
    assignment: Any, title: str, actions: list[dict[str, Any]], blockers: list[str]
) -> dict[str, Any]:
    return {
        "assignment_id": int(getattr(assignment, "id", 0) or 0),
        "assignment_title": title,
        "blockers": blockers,
        "actions": actions,
    }


def base_action(row: dict[str, str], submission: Any) -> dict[str, Any]:
    return {
        "canvas_id": int(row["CanvasID"]),
        "name": row.get("Name", "").strip(),
        "current_grade": current_grade(submission),
        "current_score": getattr(submission, "score", None),
        "current_comments": [comment_record(comment) for comment in submission_comments(submission)],
        "submission": submission,
        "blockers": [],
        "grade_change": False,
        "comment_change": False,
        "already_applied": False,
    }


def assignment_title_blockers(title: str, expected: str | None) -> list[str]:
    if expected and title.strip() != expected.strip():
        return [f"Expected assignment title {expected!r}, found {title!r}."]
    return []


def check_deduction_consistency(
    action: dict[str, Any], submission: Any, proposed: str, comment: str
) -> None:
    match = DEDUCTION_RE.search(comment)
    if not match:
        return
    try:
        current = float(current_numeric_grade(submission))
        planned = float(proposed)
    except (TypeError, ValueError):
        return
    stated = float(match.group(1))
    actual = current - planned
    if abs(stated - actual) > 0.0001:
        action["blockers"].append(
            f"Comment states {stated:g} point additional deduction; grade delta is {actual:g}."
        )


def apply_grade_post_plan(assignment: Any, plan: dict[str, Any], *, sleep_seconds: float) -> None:
    posted = skipped = failed = 0
    for action in plan["actions"]:
        label = action_label(action)
        if not action["grade_change"] and not action["comment_change"]:
            skipped += 1
            print(f"  {label}: already posted")
            continue
        try:
            submission = action["submission"]
            kwargs: dict[str, Any] = {}
            if action["grade_change"]:
                kwargs["submission"] = {"posted_grade": action["proposed_grade"]}
            if action["comment_action"] == "append" and action["comment_change"]:
                kwargs["comment"] = {"text_comment": action["comment"]}
            if kwargs:
                submission.edit(**kwargs)
            if action["comment_action"] == "replace_exact" and action["comment_change"]:
                edit_submission_comment(submission, action["target_comment"]["id"], action["comment"])
            verify_post_action(assignment, action)
            posted += 1
            print(f"  {label}: posted and verified")
            time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {label}: FAILED {type(exc).__name__}: {safe_error(str(exc))}")
    print(f"Done. Posted: {posted}, Already present: {skipped}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


def apply_grade_clear_plan(assignment: Any, plan: dict[str, Any], *, sleep_seconds: float) -> None:
    changed = skipped = failed = 0
    for action in plan["actions"]:
        label = action_label(action)
        if action["already_applied"]:
            skipped += 1
            print(f"  {label}: already clear")
            continue
        try:
            submission = action["submission"]
            if action["grade_change"]:
                submission.edit(submission={"posted_grade": ""})
            if action.get("comment_change"):
                delete_submission_comment(submission, action["target_comment"]["id"])
            verify_clear_action(assignment, action)
            changed += 1
            print(f"  {label}: cleared and verified")
            time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {label}: FAILED {type(exc).__name__}: {safe_error(str(exc))}")
    print(f"Done. Changed: {changed}, Already clear: {skipped}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


def verify_post_action(assignment: Any, action: dict[str, Any]) -> None:
    submission = assignment.get_submission(action["canvas_id"], include=["submission_comments"])
    if not grade_matches(submission, action["proposed_grade"]):
        raise RuntimeError("grade readback mismatch")
    if action["comment"] and not comment_exists(submission, action["comment"]):
        raise RuntimeError("comment readback mismatch")


def verify_clear_action(assignment: Any, action: dict[str, Any]) -> None:
    submission = assignment.get_submission(action["canvas_id"], include=["submission_comments"])
    if action["clear_grade"] and current_grade(submission) not in {None, ""}:
        raise RuntimeError("grade clear readback mismatch")
    target = action.get("target_comment")
    if target and any(comment_id(comment) == target["id"] for comment in submission_comments(submission)):
        raise RuntimeError("comment delete readback mismatch")


def write_grade_rollback(
    source: Path, plan: dict[str, Any], *, rollback_dir: Path | None
) -> tuple[Path, Path]:
    directory = rollback_dir or source.parent
    directory.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"{source.stem}.rollback-{stamp}"
    suffix = 0
    while Path(f"{base}.json").exists() or Path(f"{base}.csv").exists():
        suffix += 1
        base = directory / f"{source.stem}.rollback-{stamp}-{suffix:02d}"
    json_path = Path(f"{base}.json")
    csv_path = Path(f"{base}.csv")
    payload = {
        "private_student_data": True,
        "captured_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "assignment_id": plan["assignment_id"],
        "assignment_title": plan["assignment_title"],
        "rows": [rollback_record(action) for action in plan["actions"]],
    }
    write_json(json_path, payload)
    write_rows(csv_path, payload["rows"], ROLLBACK_FIELDS)
    mark_private(json_path)
    mark_private(csv_path)
    print(f"Wrote private rollback evidence: {json_path}")
    print(f"Wrote private rollback evidence: {csv_path}")
    return json_path, csv_path


def rollback_record(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "CanvasID": action["canvas_id"],
        "Name": action["name"],
        "OriginalGrade": action["current_grade"],
        "OriginalScore": action["current_score"],
        "OriginalCommentsJSON": json.dumps(action["current_comments"], ensure_ascii=False),
    }


def fail_for_blocked_plan(plan: dict[str, Any]) -> None:
    blockers = list(plan["blockers"])
    for action in plan["actions"]:
        blockers.extend(f"{action_label(action)}: {item}" for item in action["blockers"])
    if blockers:
        print("Preflight blocked:")
        for blocker in blockers:
            print(f"  - {blocker}")
        raise SystemExit(1)


def print_grade_plan(plan: dict[str, Any], *, dry_run: bool) -> None:
    print("Grade preflight - no Canvas writes:" if dry_run else "Grade preflight:")
    print(f"  Assignment: {plan['assignment_title']} (ID {plan['assignment_id']})")
    for action in plan["actions"]:
        delta = numeric_delta(action["current_grade"], action.get("proposed_grade"))
        delta_text = f", delta {delta:+g}" if delta is not None else ""
        print(
            f"  {action_label(action)}: {action['current_grade']!r} -> "
            f"{action.get('proposed_grade')!r}{delta_text}; comment={action.get('comment_action', 'none')}"
        )


def print_offline_preview(rows: list[dict[str, str]]) -> None:
    print("Offline preview - Canvas was not contacted:")
    for row in rows:
        print(f"  {row.get('Name') or row['CanvasID']} (CanvasID {row['CanvasID']}): {row['Grade']}")


def load_grade_rows(path: Path) -> list[dict[str, str]]:
    return load_csv_rows(path, required=("CanvasID", "Grade"), require_grade_value=True)


def load_clear_rows(path: Path) -> list[dict[str, str]]:
    return load_csv_rows(path, required=("CanvasID",), require_grade_value=False)


def load_csv_rows(
    path: Path, *, required: tuple[str, ...], require_grade_value: bool
) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Grades CSV not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for column in required:
            if column not in headers:
                raise SystemExit(f"Grades CSV must include {column}. Found: {', '.join(headers)}")
        return [
            row
            for row in reader
            if row.get("CanvasID") and (not require_grade_value or row.get("Grade"))
        ]


def current_user_id_for(canvas: Any) -> int:
    return int(canvas.get_current_user().id)


def needs_comment_ownership(rows: list[dict[str, str]]) -> bool:
    return any((row.get("CommentAction") or "").strip().lower() == "replace_exact" for row in rows)


def current_grade(submission: Any) -> Any:
    grade = getattr(submission, "grade", None)
    return grade if grade not in {None, ""} else getattr(submission, "score", None)


def current_numeric_grade(submission: Any) -> Any:
    score = getattr(submission, "score", None)
    return score if score not in {None, ""} else getattr(submission, "grade", None)


def numeric_delta(current: Any, proposed: Any) -> float | None:
    try:
        return float(proposed) - float(current)
    except (TypeError, ValueError):
        return None


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


def submission_comments(submission: Any) -> list[Any]:
    return list(getattr(submission, "submission_comments", []) or [])


def comment_text(comment: Any) -> str:
    return str(comment.get("comment", "") if isinstance(comment, dict) else getattr(comment, "comment", ""))


def comment_id(comment: Any) -> int | None:
    raw = comment.get("id") if isinstance(comment, dict) else getattr(comment, "id", None)
    return int(raw) if raw not in {None, ""} else None


def comment_author_id(comment: Any) -> int | None:
    raw = comment.get("author_id") if isinstance(comment, dict) else getattr(comment, "author_id", None)
    return int(raw) if raw not in {None, ""} else None


def comment_record(comment: Any) -> dict[str, Any]:
    return {
        "id": comment_id(comment),
        "author_id": comment_author_id(comment),
        "author_name": (
            comment.get("author_name", "")
            if isinstance(comment, dict)
            else getattr(comment, "author_name", "")
        ),
        "comment": comment_text(comment),
        "created_at": (
            comment.get("created_at")
            if isinstance(comment, dict)
            else getattr(comment, "created_at", None)
        ),
    }


def comment_exists(submission: Any, expected: str) -> bool:
    return any(comment_text(comment).strip() == expected.strip() for comment in submission_comments(submission))


def resolve_owned_comment(
    submission: Any,
    *,
    current_user_id: int | None,
    target_comment_id: str,
    exact_text: str,
) -> Any | str:
    if current_user_id is None:
        return "Current-user identity is required for comment replacement/deletion."
    wanted_id = int(target_comment_id) if str(target_comment_id).strip() else None
    wanted_text = str(exact_text).strip()
    candidates = [
        comment
        for comment in submission_comments(submission)
        if (wanted_id is None or comment_id(comment) == wanted_id)
        and (not wanted_text or comment_text(comment).strip() == wanted_text)
    ]
    if not wanted_id and not wanted_text:
        return "Exact comment ID or text is required."
    if len(candidates) != 1:
        return f"Expected one exact comment match, found {len(candidates)}."
    if comment_author_id(candidates[0]) != current_user_id:
        return "Matched comment is not owned by the authenticated user."
    return candidates[0]


def edit_submission_comment(submission: Any, target_id: int, text: str) -> None:
    if hasattr(submission, "edit_comment"):
        submission.edit_comment(target_id, text)
        return
    submission._requester.request(  # noqa: SLF001
        "PUT",
        f"courses/{submission.course_id}/assignments/{submission.assignment_id}/"
        f"submissions/{submission.user_id}/comments/{target_id}",
        _kwargs={"comment": text},
    )


def delete_submission_comment(submission: Any, target_id: int) -> None:
    if hasattr(submission, "delete_comment"):
        submission.delete_comment(target_id)
        return
    submission._requester.request(  # noqa: SLF001
        "DELETE",
        f"courses/{submission.course_id}/assignments/{submission.assignment_id}/"
        f"submissions/{submission.user_id}/comments/{target_id}",
    )


def parse_bool(value: str, *, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise SystemExit(f"Expected boolean value, found {value!r}.")


def action_label(action: dict[str, Any]) -> str:
    return f"{action['name'] or action['canvas_id']} (CanvasID {action['canvas_id']})"
