"""Canvas grade posting, cleanup, rollback, and verification operations."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any

from canvasapi.util import combine_kwargs

from danvas.auth import canvas_from_args
from danvas.grade_evidence import (
    HALT_OUTCOMES,
    SUCCESS_OUTCOMES,
    assignment_release_context,
    classify_effect_outcome,
    classify_release_state,
    make_grade_report_run,
    safe_plan_rows,
    safe_result_rows,
    summarize_outcomes,
    write_failed_grade_report,
    write_grade_report,
    write_recovery_artifacts,
)
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

    report_run = make_grade_report_run(args, command="grades post", source=source)
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
        write_failed_grade_report(
            report_run, command="grades post", error=exc, artifact="grades-plan"
        )
        raise SystemExit(f"Grade preflight failed: {safe_error(str(exc))}") from exc
    print_grade_plan(plan, dry_run=bool(args.dry_run))
    if plan_has_blockers(plan):
        write_grade_report(
            report_run,
            build_grade_plan_report(plan, command="grades post", status="blocked"),
            artifact="grades-plan",
            success=False,
        )
        fail_for_blocked_plan(plan)
    if args.dry_run:
        write_grade_report(
            report_run,
            build_grade_plan_report(plan, command="grades post", status="dry_run"),
            artifact="grades-plan",
            success=True,
        )
        return

    rollback_paths = capture_grade_rollback(
        source, plan, args=args, report_run=report_run, command="grades post"
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
    results = apply_grade_plan(
        assignment, plan, mode="post", sleep_seconds=args.sleep_seconds
    )
    recovery_paths, recovery_error = capture_grade_recovery(
        report_run=report_run,
        source=source,
        mode="post",
        actions=plan["actions"],
        results=results,
    )
    report = build_grade_result_report(
        plan,
        results,
        command="grades post",
        rollback_paths=rollback_paths,
        recovery_paths=recovery_paths,
        include_release=True,
        evidence_error=recovery_error,
    )
    success = recovery_error is None and all(
        result["outcome"] in SUCCESS_OUTCOMES for result in results
    )
    write_grade_report(
        report_run, report, artifact="grades-result", success=success
    )
    if not success:
        raise SystemExit(1)


def command_grades_clear(args: Any) -> None:
    source = Path(args.grades_csv)
    rows = load_clear_rows(source)
    report_run = make_grade_report_run(args, command="grades clear", source=source)
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
        write_failed_grade_report(
            report_run, command="grades clear", error=exc, artifact="grades-plan"
        )
        raise SystemExit(f"Grade-clear preflight failed: {safe_error(str(exc))}") from exc
    print_grade_plan(plan, dry_run=bool(args.dry_run))
    if plan_has_blockers(plan):
        write_grade_report(
            report_run,
            build_grade_plan_report(plan, command="grades clear", status="blocked"),
            artifact="grades-plan",
            success=False,
        )
        fail_for_blocked_plan(plan)
    if args.dry_run:
        write_grade_report(
            report_run,
            build_grade_plan_report(plan, command="grades clear", status="dry_run"),
            artifact="grades-plan",
            success=True,
        )
        return

    rollback_paths = capture_grade_rollback(
        source, plan, args=args, report_run=report_run, command="grades clear"
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
    results = apply_grade_plan(
        assignment, plan, mode="clear", sleep_seconds=args.sleep_seconds
    )
    recovery_paths, recovery_error = capture_grade_recovery(
        report_run=report_run,
        source=source,
        mode="clear",
        actions=plan["actions"],
        results=results,
    )
    report = build_grade_result_report(
        plan,
        results,
        command="grades clear",
        rollback_paths=rollback_paths,
        recovery_paths=recovery_paths,
        include_release=False,
        evidence_error=recovery_error,
    )
    success = recovery_error is None and all(
        result["outcome"] in SUCCESS_OUTCOMES for result in results
    )
    write_grade_report(
        report_run, report, artifact="grades-result", success=success
    )
    if not success:
        raise SystemExit(1)


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
    source = Path(args.grades_csv)
    rows = load_grade_rows(source)
    report_run = make_grade_report_run(args, command="grades verify", source=source)
    try:
        canvas = canvas_from_args(args)
        assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
        results = []
        for row in rows:
            submission = assignment.get_submission(
                int(row["CanvasID"]), include=["submission_comments", "visibility"]
            )
            grade_ok = grade_matches(submission, row["Grade"].strip())
            comment = row.get("Comment", "").strip()
            comment_ok = not comment or comment_exists(submission, comment)
            desired_verified = grade_ok and comment_ok
            status = "OK" if desired_verified else "MISMATCH"
            print(f"  {row.get('Name') or row['CanvasID']}: {status}")
            results.append(
                {
                    "canvas_id": int(row["CanvasID"]),
                    "name": row.get("Name") or "",
                    "outcome": "verified" if desired_verified else "mismatch",
                    "desired_verified": desired_verified,
                    "intended_grade": row["Grade"].strip(),
                    "comment_action": "verify_exact" if comment else "none",
                    "intended_comment": comment,
                    "target_comment_id": None,
                    "observed": observe_submission(submission),
                    "effect_status": {
                        "grade": "desired" if grade_ok else "other",
                        "comment": "desired" if comment_ok else "other",
                    },
                    "phase": "verify",
                    "error": None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        write_failed_grade_report(
            report_run, command="grades verify", error=exc, artifact="grades-verify"
        )
        raise SystemExit(f"Grade verification failed: {safe_error(str(exc))}") from exc

    release_state = classify_release_state(
        results,
        assignment_context=assignment_release_context(assignment),
        require_desired_verified=True,
        basis="verified_target_state",
    )
    print_release_state(release_state)
    failures = sum(not result["desired_verified"] for result in results)
    report = {
        "command": "grades verify",
        "status": "verified" if not failures else "mismatch",
        "assignment_id": int(getattr(assignment, "id", args.assignment_id)),
        "assignment_title": str(getattr(assignment, "name", "") or ""),
        "summary": summarize_outcomes(results),
        "rows": safe_result_rows(results),
        "release_state": release_state,
    }
    write_grade_report(
        report_run,
        report,
        artifact="grades-verify",
        success=not failures,
    )
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
        submission = assignment.get_submission(
            canvas_id, include=["submission_comments", "visibility"]
        )
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
        submission = assignment.get_submission(
            canvas_id, include=["submission_comments", "visibility"]
        )
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
        action["comment"] = exact_text
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
        "assignment_context": assignment_release_context(assignment),
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
        "prewrite_observation": observe_submission(submission),
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


def apply_grade_plan(
    assignment: Any,
    plan: dict[str, Any],
    *,
    mode: str,
    sleep_seconds: float,
) -> list[dict[str, Any]]:
    """Apply post/clear actions with authoritative per-effect readback."""
    results: list[dict[str, Any]] = []
    halted = False
    for action in plan["actions"]:
        label = action_label(action)
        if halted:
            result = base_result(action, "not_attempted")
            result["phase"] = "halted"
            results.append(result)
            print(f"  {label}: not attempted after an unsafe prior outcome")
            continue
        if not action["grade_change"] and not action["comment_change"]:
            result = base_result(action, "already_applied")
            result["observed"] = action["prewrite_observation"]
            result["desired_verified"] = True
            result["phase"] = "preflight"
            results.append(result)
            print(f"  {label}: already applied")
            continue

        error: Exception | None = None
        phase = "mutation"
        try:
            apply_grade_action(action, mode=mode)
            phase = "readback"
        except Exception as exc:  # noqa: BLE001
            error = exc
            phase = str(action.get("_mutation_phase") or "mutation")
        try:
            submission = assignment.get_submission(
                action["canvas_id"], include=["submission_comments", "visibility"]
            )
            observed = observe_submission(submission)
        except Exception as exc:  # noqa: BLE001
            readback_error = exc
            result = base_result(action, "indeterminate")
            result.update(
                {
                    "phase": "readback",
                    "error": safe_error(str(error or readback_error)),
                    "readback_error": safe_error(str(readback_error)),
                    "observed": {
                        "readback_available": False,
                        "error": safe_error(str(readback_error)),
                    },
                }
            )
        else:
            effect_status = classify_action_effects(action, observed, mode=mode)
            outcome, detail = classify_effect_outcome(
                effect_status, had_error=error is not None
            )
            result = base_result(action, outcome)
            result.update(
                {
                    "detail": detail,
                    "phase": phase,
                    "error": safe_error(str(error)) if error else None,
                    "effect_status": effect_status,
                    "observed": observed,
                    "desired_verified": outcome in SUCCESS_OUTCOMES,
                }
            )
        results.append(result)
        print_grade_result(label, result)
        if result["outcome"] in HALT_OUTCOMES:
            halted = True
        if result["outcome"] == "verified_applied":
            time.sleep(sleep_seconds)

    summary = summarize_outcomes(results)
    totals = ", ".join(f"{name}: {count}" for name, count in summary.items())
    print(f"Done. {totals}")
    return results


def apply_grade_action(action: dict[str, Any], *, mode: str) -> None:
    submission = action["submission"]
    if mode == "post":
        kwargs: dict[str, Any] = {}
        if action["grade_change"]:
            kwargs["submission"] = {"posted_grade": action["proposed_grade"]}
        if action["comment_action"] == "append" and action["comment_change"]:
            kwargs["comment"] = {"text_comment": action["comment"]}
        if kwargs:
            action["_mutation_phase"] = "submission_edit"
            submission.edit(**kwargs)
        if action["comment_action"] == "replace_exact" and action["comment_change"]:
            action["_mutation_phase"] = "comment_replace"
            edit_submission_comment(
                submission, action["target_comment"]["id"], action["comment"]
            )
        return

    if action["grade_change"]:
        action["_mutation_phase"] = "grade_clear"
        submission.edit(submission={"posted_grade": ""})
    if action.get("comment_change"):
        action["_mutation_phase"] = "comment_delete"
        delete_submission_comment(submission, action["target_comment"]["id"])


def classify_action_effects(
    action: dict[str, Any], observed: dict[str, Any], *, mode: str
) -> dict[str, str]:
    grade_status = "not_planned"
    if action.get("grade_change"):
        desired_grade = action.get("proposed_grade")
        if observation_grade_matches(observed, desired_grade):
            grade_status = "desired"
        elif observation_grade_matches(
            observed, action.get("current_grade"), action.get("current_score")
        ):
            grade_status = "original"
        else:
            grade_status = "other"

    comment_status = "not_planned"
    if action.get("comment_change"):
        comments = observed.get("comments") or []
        if mode == "post" and action.get("comment_action") == "append":
            desired = comment_record_exists(comments, text=action.get("comment"))
            original = not comment_record_exists(
                action["prewrite_observation"].get("comments") or [],
                text=action.get("comment"),
            )
            comment_status = "desired" if desired else ("original" if original else "other")
        else:
            target = action.get("target_comment") or {}
            observed_target = find_comment_record(
                comments, comment_id_value=target.get("id")
            )
            if mode == "clear":
                comment_status = "desired" if not observed_target else "original"
            elif observed_target and str(observed_target.get("comment") or "").strip() == str(
                action.get("comment") or ""
            ).strip():
                comment_status = "desired"
            elif observed_target and str(observed_target.get("comment") or "").strip() == str(
                target.get("comment") or ""
            ).strip():
                comment_status = "original"
            else:
                comment_status = "other"
    return {"grade": grade_status, "comment": comment_status}


def observe_submission(submission: Any) -> dict[str, Any]:
    return {
        "readback_available": True,
        "grade": current_grade(submission),
        "score": getattr(submission, "score", None),
        "comments": [comment_record(comment) for comment in submission_comments(submission)],
        "posted_at_available": hasattr(submission, "posted_at"),
        "posted_at": getattr(submission, "posted_at", None),
        "assignment_visible_available": hasattr(submission, "assignment_visible"),
        "assignment_visible": getattr(submission, "assignment_visible", None),
    }


def grade_value_matches(observed: Any, expected: Any) -> bool:
    if expected in {None, ""}:
        return observed in {None, ""}
    if observed in {None, ""}:
        return False
    try:
        return abs(float(observed) - float(expected)) < 0.0001
    except (TypeError, ValueError):
        return str(observed).strip() == str(expected).strip()


def observation_grade_matches(observation: dict[str, Any], *expected_values: Any) -> bool:
    observed_values = (observation.get("grade"), observation.get("score"))
    nonempty_expected = [value for value in expected_values if value not in {None, ""}]
    if not nonempty_expected:
        return all(value in {None, ""} for value in observed_values)
    return any(
        grade_value_matches(observed, expected)
        for observed in observed_values
        for expected in nonempty_expected
    )


def comment_record_exists(
    comments: list[dict[str, Any]],
    *,
    text: Any = None,
    comment_id_value: Any = None,
) -> bool:
    return find_comment_record(
        comments, text=text, comment_id_value=comment_id_value
    ) is not None


def find_comment_record(
    comments: list[dict[str, Any]],
    *,
    text: Any = None,
    comment_id_value: Any = None,
) -> dict[str, Any] | None:
    for comment in comments:
        id_matches = comment_id_value is None or str(comment.get("id")) == str(
            comment_id_value
        )
        text_matches = text is None or str(comment.get("comment") or "").strip() == str(
            text
        ).strip()
        if id_matches and text_matches:
            return comment
    return None


def base_result(action: dict[str, Any], outcome: str) -> dict[str, Any]:
    target = action.get("target_comment") or {}
    return {
        "canvas_id": action["canvas_id"],
        "name": action.get("name") or "",
        "outcome": outcome,
        "detail": None,
        "phase": None,
        "error": None,
        "readback_error": None,
        "intended_grade": action.get("proposed_grade"),
        "comment_action": action.get("comment_action", "none"),
        "intended_comment": action.get("comment") or "",
        "target_comment_id": target.get("id"),
        "effect_status": {},
        "desired_verified": outcome in SUCCESS_OUTCOMES,
        "observed": {"readback_available": False},
    }


def build_grade_plan_report(
    plan: dict[str, Any], *, command: str, status: str
) -> dict[str, Any]:
    release_rows = [
        {"observed": action["prewrite_observation"], "desired_verified": True}
        for action in plan["actions"]
    ]
    release_state = classify_release_state(
        release_rows,
        assignment_context=plan["assignment_context"],
        require_desired_verified=False,
        basis="current_target_state",
    )
    summary = {
        "target_rows": len(plan["actions"]),
        "grade_changes": sum(bool(action.get("grade_change")) for action in plan["actions"]),
        "comment_changes": sum(
            bool(action.get("comment_change")) for action in plan["actions"]
        ),
        "blocked_rows": sum(bool(action.get("blockers")) for action in plan["actions"]),
        "assignment_blockers": len(plan["blockers"]),
    }
    return {
        "command": command,
        "status": status,
        "assignment_id": plan["assignment_id"],
        "assignment_title": plan["assignment_title"],
        "summary": summary,
        "rows": safe_plan_rows(plan["actions"]),
        "release_state": release_state,
    }


def build_grade_result_report(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    command: str,
    rollback_paths: tuple[Path, Path],
    recovery_paths: list[Path],
    include_release: bool,
    evidence_error: str | None,
) -> dict[str, Any]:
    success = evidence_error is None and all(
        result["outcome"] in SUCCESS_OUTCOMES for result in results
    )
    release_state = None
    if include_release:
        release_state = classify_release_state(
            results,
            assignment_context=plan["assignment_context"],
            require_desired_verified=True,
            basis="verified_target_state",
        )
        print_release_state(release_state)
    return {
        "command": command,
        "status": "success" if success else "failed",
        "assignment_id": plan["assignment_id"],
        "assignment_title": plan["assignment_title"],
        "summary": summarize_outcomes(results),
        "rows": safe_result_rows(results),
        "rollback_artifacts": [str(path) for path in rollback_paths],
        "recovery_artifacts": [str(path) for path in recovery_paths],
        "evidence_error": evidence_error,
        "release_state": release_state,
    }


def capture_grade_rollback(
    source: Path,
    plan: dict[str, Any],
    *,
    args: Any,
    report_run: Any,
    command: str,
) -> tuple[Path, Path]:
    try:
        return write_grade_rollback(
            source,
            plan,
            rollback_dir=(
                Path(args.rollback_dir) if getattr(args, "rollback_dir", None) else None
            ),
        )
    except Exception as exc:  # noqa: BLE001
        write_failed_grade_report(
            report_run, command=command, error=exc, artifact="grades-result"
        )
        raise SystemExit(f"Grade rollback capture failed: {safe_error(str(exc))}") from exc


def capture_grade_recovery(
    *,
    report_run: Any,
    source: Path,
    mode: str,
    actions: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> tuple[list[Path], str | None]:
    try:
        return (
            write_recovery_artifacts(
                report_run,
                source=source,
                mode=mode,
                actions=actions,
                results=results,
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001
        error = safe_error(str(exc))
        print(f"Private recovery evidence could not be written: {error}")
        return [], error


def plan_has_blockers(plan: dict[str, Any]) -> bool:
    return bool(plan["blockers"]) or any(action["blockers"] for action in plan["actions"])


def print_grade_result(label: str, result: dict[str, Any]) -> None:
    detail = f" ({result['detail']})" if result.get("detail") else ""
    error = f": {result['error']}" if result.get("error") else ""
    print(f"  {label}: {result['outcome']}{detail}{error}")


def print_release_state(release_state: dict[str, Any]) -> None:
    conclusion = release_state["conclusion"]
    reason = f" ({release_state['reason']})" if release_state.get("reason") else ""
    print(f"Grade release state: {conclusion}{reason}")


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
        rows: list[dict[str, str]] = []
        seen_canvas_ids: dict[int, int] = {}
        for raw_row in reader:
            if all(not str(value or "").strip() for value in raw_row.values()):
                continue
            extra_values = raw_row.get(None)
            if isinstance(extra_values, list) and any(str(value).strip() for value in extra_values):
                raise SystemExit(f"Grades CSV row {reader.line_num} has unexpected extra columns.")
            canvas_id_text = str(raw_row.get("CanvasID") or "").strip()
            if not canvas_id_text:
                raise SystemExit(f"Grades CSV row {reader.line_num} must include CanvasID.")
            try:
                canvas_id = int(canvas_id_text)
            except ValueError as exc:
                raise SystemExit(
                    f"Grades CSV row {reader.line_num} has invalid CanvasID: {canvas_id_text!r}."
                ) from exc
            if canvas_id <= 0:
                raise SystemExit(
                    f"Grades CSV row {reader.line_num} has invalid CanvasID: {canvas_id_text!r}."
                )
            first_line = seen_canvas_ids.get(canvas_id)
            if first_line is not None:
                raise SystemExit(
                    f"Grades CSV has duplicate CanvasID {canvas_id} on rows "
                    f"{first_line} and {reader.line_num}."
                )
            if require_grade_value and not str(raw_row.get("Grade") or "").strip():
                raise SystemExit(f"Grades CSV row {reader.line_num} must include Grade.")
            seen_canvas_ids[canvas_id] = reader.line_num
            row = {
                str(key): str(value or "")
                for key, value in raw_row.items()
                if key is not None
            }
            row["CanvasID"] = str(canvas_id)
            if require_grade_value:
                row["Grade"] = row["Grade"].strip()
            rows.append(row)
        if not rows:
            raise SystemExit("Grades CSV contains no data rows.")
        return rows


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
        _kwargs=combine_kwargs(comment=text),
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
