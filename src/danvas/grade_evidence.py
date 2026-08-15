"""Private evidence, recovery, and release-state helpers for grade workflows."""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from danvas.artifacts import (
    ensure_private_directory,
    write_private_json,
    write_private_pair,
    write_private_rows,
)
from danvas.reports import ReportRun, create_report_run, safe_error, should_write_report_run
from danvas.sanitize import contains_sensitive_text

SUCCESS_OUTCOMES = {"verified_applied", "already_applied"}
HALT_OUTCOMES = {"partially_applied", "applied_unverified", "indeterminate"}
POST_RECOVERY_FIELDS = [
    "CanvasID",
    "Name",
    "Grade",
    "Comment",
    "ExpectedCurrentGrade",
    "CommentAction",
    "CommentID",
    "ExpectedComment",
]
CLEAR_RECOVERY_FIELDS = [
    "CanvasID",
    "Name",
    "ExpectedCurrentGrade",
    "ClearGrade",
    "CommentID",
    "Comment",
]


def classify_effect_outcome(
    effect_status: dict[str, str], *, had_error: bool
) -> tuple[str, str | None]:
    """Classify authoritative effect readback without knowing Canvas object types."""
    planned = {name: status for name, status in effect_status.items() if status != "not_planned"}
    if not planned:
        return "already_applied", None
    desired = [name for name, status in planned.items() if status == "desired"]
    if len(desired) == len(planned):
        return "verified_applied", None
    if had_error and all(status == "original" for status in planned.values()):
        return "unchanged_failure", None
    if desired:
        detail = f"{'_and_'.join(sorted(desired))}_only"
        return "partially_applied", detail
    return "applied_unverified", None


def summarize_outcomes(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("outcome") or "unknown") for row in rows)
    return dict(sorted(counts.items()))


def assignment_release_context(assignment: Any) -> dict[str, Any]:
    fields = ("published", "unlock_at", "due_at", "lock_at", "post_manually")
    return {
        field: {
            "available": object_has(assignment, field),
            "value": object_value(assignment, field),
        }
        for field in fields
    }


def classify_release_state(
    rows: list[dict[str, Any]],
    *,
    assignment_context: dict[str, Any],
    require_desired_verified: bool,
    basis: str,
) -> dict[str, Any]:
    """Conservatively classify targeted-row grade release evidence."""
    base = {
        "conclusion": "not_determined",
        "basis": basis,
        "target_count": len(rows),
        "posted_count": 0,
        "hidden_count": 0,
        "assignment_visible_count": 0,
        "assignment_not_visible_count": 0,
        "assignment_context": assignment_context,
        "reason": None,
    }
    if not rows:
        base["reason"] = "no_target_rows"
        return base
    if require_desired_verified and not all(bool(row.get("desired_verified")) for row in rows):
        base["reason"] = "desired_grade_or_comment_state_not_verified"
        return base
    observations = [row.get("observed") or {} for row in rows]
    if not all(
        observation.get("readback_available")
        and observation.get("posted_at_available")
        and observation.get("assignment_visible_available")
        for observation in observations
    ):
        base["reason"] = "required_submission_visibility_fields_unavailable"
        return base

    posted = [observation.get("posted_at") not in {None, ""} for observation in observations]
    visible = [observation.get("assignment_visible") is True for observation in observations]
    base["posted_count"] = sum(posted)
    base["hidden_count"] = len(posted) - sum(posted)
    base["assignment_visible_count"] = sum(visible)
    base["assignment_not_visible_count"] = len(visible) - sum(visible)
    if not any(posted):
        base["conclusion"] = "verified_hidden"
    elif not all(posted):
        base["conclusion"] = "mixed"
        base["reason"] = "mixed_posted_state"
    elif all(visible):
        base["conclusion"] = "verified_visible"
    elif any(visible):
        base["conclusion"] = "mixed"
        base["reason"] = "mixed_assignment_visibility"
    else:
        base["reason"] = "posted_grades_but_assignments_not_visible"
    return base


def make_grade_report_run(args: Any, *, command: str, source: Path) -> ReportRun | None:
    project_root = Path(getattr(args, "project_root", ".")).resolve()
    report_root = path_option(args, "report_root")
    report_dir = path_option(args, "report_dir")
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
    slug = report_slug or command.replace(" ", "-")
    return create_report_run(
        command=command,
        slug=slug,
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[source],
        private_data=True,
    )


def write_grade_report(
    report_run: ReportRun | None,
    report: dict[str, Any],
    *,
    artifact: str,
    success: bool,
) -> list[Path]:
    if report_run is None:
        return []
    json_path = report_run.write_json(f"{artifact}.json", report)
    md_path = report_run.write_text(f"{artifact}.md", render_grade_markdown(report))
    manifest_path = report_run.finish("success" if success else "failed")
    print("Private report artifacts: 3")
    print(f"Report directory: {report_run.path}")
    return [json_path, md_path, manifest_path]


def write_failed_grade_report(
    report_run: ReportRun | None,
    *,
    command: str,
    error: Exception | str,
    artifact: str,
) -> None:
    if report_run is None:
        return
    report = {
        "command": command,
        "status": "failed",
        "error": safe_error(str(error)),
        "summary": {},
        "rows": [],
        "release_state": None,
    }
    write_grade_report(report_run, report, artifact=artifact, success=False)


def safe_plan_rows(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [safe_plan_row(action) for action in actions]


def safe_plan_row(action: dict[str, Any]) -> dict[str, Any]:
    target = action.get("target_comment") or {}
    return {
        "canvas_id": action["canvas_id"],
        "name": action.get("name") or "",
        "current_grade": action.get("current_grade"),
        "current_score": action.get("current_score"),
        "proposed_grade": action.get("proposed_grade"),
        "grade_change": bool(action.get("grade_change")),
        "comment_action": action.get("comment_action", "none"),
        "comment_change": bool(action.get("comment_change")),
        "comment_sha256": hash_text(action.get("comment")),
        "target_comment_id": target.get("id"),
        "target_comment_sha256": hash_text(target.get("comment")),
        "blockers": list(action.get("blockers") or []),
        "observed": safe_observation(action.get("prewrite_observation") or {}),
    }


def safe_result_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "canvas_id": row["canvas_id"],
            "name": row.get("name") or "",
            "outcome": row["outcome"],
            "detail": row.get("detail"),
            "phase": row.get("phase"),
            "error": row.get("error"),
            "readback_error": row.get("readback_error"),
            "intended_grade": row.get("intended_grade"),
            "comment_action": row.get("comment_action", "none"),
            "intended_comment_sha256": hash_text(row.get("intended_comment")),
            "target_comment_id": row.get("target_comment_id"),
            "effect_status": row.get("effect_status") or {},
            "desired_verified": bool(row.get("desired_verified")),
            "observed": safe_observation(row.get("observed") or {}),
        }
        for row in results
    ]


def safe_observation(observation: dict[str, Any]) -> dict[str, Any]:
    comments = observation.get("comments") or []
    return {
        "readback_available": bool(observation.get("readback_available")),
        "grade": observation.get("grade"),
        "score": observation.get("score"),
        "comments": [
            {
                "id": comment.get("id"),
                "author_id": comment.get("author_id"),
                "comment_sha256": hash_text(comment.get("comment")),
            }
            for comment in comments
        ],
        "posted_at_available": bool(observation.get("posted_at_available")),
        "posted_at": observation.get("posted_at"),
        "assignment_visible_available": bool(observation.get("assignment_visible_available")),
        "assignment_visible": observation.get("assignment_visible"),
    }


def write_recovery_artifacts(
    report_run: ReportRun | None,
    *,
    source: Path,
    mode: str,
    actions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    private_dir: Path | None,
) -> list[Path]:
    action_by_id: dict[int, dict[str, Any]] = {}
    for action in actions:
        canvas_id = int(action["canvas_id"])
        if canvas_id in action_by_id:
            raise ValueError(f"Duplicate CanvasID in grade recovery actions: {canvas_id}")
        action_by_id[canvas_id] = action
    affected = [row for row in results if row.get("outcome") in HALT_OUTCOMES]
    if not affected:
        return []
    recovery_rows = [
        recovery_record(action_by_id[int(result["canvas_id"])], result, mode=mode)
        for result in affected
    ]
    payload = {
        "private_student_data": True,
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "source_name": source.name,
        "rows": recovery_rows,
    }
    csv_rows = [
        candidate
        for record in recovery_rows
        if (candidate := record.get("forward_recovery_row")) is not None
    ]
    paths: list[Path] = []
    if report_run is not None:
        paths.append(report_run.write_json("grades-recovery.json", payload))
        paths.append(report_run.write_text("grades-recovery.md", render_recovery_markdown(payload)))
        if csv_rows:
            fields = POST_RECOVERY_FIELDS if mode == "post" else CLEAR_RECOVERY_FIELDS
            paths.append(report_run.write_rows("grades-recovery-forward.csv", csv_rows, fields))
        print_recovery_paths(paths)
        return paths

    if private_dir is None:
        raise RuntimeError("Grade recovery evidence requires a private destination.")
    directory = ensure_private_directory(private_dir)
    base = collision_safe_recovery_base(directory)
    json_path = Path(f"{base}.json")
    md_path = Path(f"{base}.md")
    write_private_json(json_path, payload, command="grades recovery")
    write_private_pair(
        md_path,
        render_recovery_markdown(payload).encode("utf-8"),
        command="grades recovery",
    )
    paths.extend([json_path, md_path])
    if csv_rows:
        csv_path = Path(f"{base}.forward.csv")
        fields = POST_RECOVERY_FIELDS if mode == "post" else CLEAR_RECOVERY_FIELDS
        write_private_rows(
            csv_path,
            csv_rows,
            fields,
            command="grades recovery",
        )
        paths.append(csv_path)
    print_recovery_paths(paths)
    return paths


def recovery_record(action: dict[str, Any], result: dict[str, Any], *, mode: str) -> dict[str, Any]:
    observed = result.get("observed") or {}
    authoritative = bool(observed.get("readback_available"))
    record = {
        "canvas_id": action["canvas_id"],
        "name": action.get("name") or "",
        "outcome": result["outcome"],
        "detail": result.get("detail"),
        "phase": result.get("phase"),
        "error": result.get("error"),
        "readback_error": result.get("readback_error"),
        "observation_authoritative": authoritative,
        "prewrite": recovery_observation(action.get("prewrite_observation") or {}),
        "intended": {
            "grade": action.get("proposed_grade"),
            "grade_change": bool(action.get("grade_change")),
            "comment_action": action.get("comment_action", "none"),
            "comment": recovery_text(action.get("comment")),
            "target_comment": recovery_comment(action.get("target_comment") or {}),
        },
        "observed": recovery_observation(observed),
        "safe_next_action": (
            "Review authoritative readback and the guarded forward-recovery CSV before rerunning."
            if authoritative
            else "Run a fresh grades verify/comments readback before any further mutation."
        ),
        "forward_recovery_row": None,
    }
    if authoritative:
        record["forward_recovery_row"] = candidate_recovery_row(action, result, mode=mode)
    return record


def candidate_recovery_row(
    action: dict[str, Any], result: dict[str, Any], *, mode: str
) -> dict[str, Any] | None:
    observed = result.get("observed") or {}
    if not observed.get("readback_available"):
        return None
    effect_status = result.get("effect_status") or {}
    observed_grade = observed_guard_grade(observed)
    if mode == "post":
        if observed_grade in {None, ""}:
            return None
        comment_action = "none"
        comment = ""
        comment_id: Any = ""
        expected_comment = ""
        if action.get("comment_change") and effect_status.get("comment") != "desired":
            comment_action = str(action.get("comment_action") or "none")
            comment = str(action.get("comment") or "")
            if contains_sensitive_text(comment):
                return None
            if comment_action == "replace_exact":
                target = action.get("target_comment") or {}
                comment_id = target.get("id") or ""
                match = comment_with_id(observed.get("comments") or [], comment_id)
                if not match:
                    return None
                expected_comment = str(match.get("comment") or "")
                if contains_sensitive_text(expected_comment):
                    return None
        return {
            "CanvasID": action["canvas_id"],
            "Name": action.get("name") or "",
            "Grade": action.get("proposed_grade") or "",
            "Comment": comment,
            "ExpectedCurrentGrade": observed_grade,
            "CommentAction": comment_action,
            "CommentID": comment_id,
            "ExpectedComment": expected_comment,
        }

    target = action.get("target_comment") or {}
    grade_still_needed = effect_status.get("grade") != "desired"
    if grade_still_needed and observed_grade in {None, ""}:
        return None
    remaining_comment = None
    if action.get("comment_change") and effect_status.get("comment") != "desired":
        remaining_comment = comment_with_id(observed.get("comments") or [], target.get("id"))
        if not remaining_comment:
            return None
        if contains_sensitive_text(remaining_comment.get("comment")):
            return None
    return {
        "CanvasID": action["canvas_id"],
        "Name": action.get("name") or "",
        "ExpectedCurrentGrade": observed_grade if grade_still_needed else "",
        "ClearGrade": "true" if grade_still_needed else "false",
        "CommentID": target.get("id") if remaining_comment else "",
        "Comment": remaining_comment.get("comment", "") if remaining_comment else "",
    }


def render_grade_markdown(report: dict[str, Any]) -> str:
    release = report.get("release_state") or {}
    lines = [
        f"# {str(report.get('command') or 'Grades').title()}",
        "",
        f"- Status: {report.get('status', 'unknown')}",
        f"- Assignment: {report.get('assignment_title', '')} ({report.get('assignment_id', '')})",
    ]
    if release:
        lines.append(f"- Release conclusion: {release.get('conclusion', 'not_determined')}")
        if release.get("reason"):
            lines.append(f"- Release limitation: {release['reason']}")
    summary = report.get("summary") or {}
    if summary:
        lines.extend(["", "## Outcomes", ""])
        lines.extend(f"- {name}: {count}" for name, count in summary.items())
    rows = report.get("rows") or []
    if rows:
        lines.extend(["", "## Targeted Rows", ""])
        for row in rows:
            outcome = row.get("outcome") or ("blocked" if row.get("blockers") else "planned")
            lines.append(f"- {row.get('name') or row.get('canvas_id')}: {outcome}")
    lines.extend(["", "This report contains private student grade evidence."])
    return "\n".join(lines) + "\n"


def render_recovery_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Grade mutation recovery",
        "",
        "This file contains private student grade/comment evidence.",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"## {row.get('name') or row['canvas_id']}",
                "",
                f"- Outcome: {row['outcome']}",
                f"- Failed phase: {row.get('phase') or 'unknown'}",
                f"- Authoritative readback: {row['observation_authoritative']}",
                f"- Next action: {row['safe_next_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def recovery_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in observation.items() if key not in {"comments", "error"}
    } | {
        "comments": [recovery_comment(comment) for comment in observation.get("comments") or []],
        "error": safe_error(str(observation["error"])) if observation.get("error") else None,
    }


def recovery_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in comment.items() if key != "comment"} | {
        "comment": recovery_text(comment.get("comment"))
    }


def recovery_text(value: Any) -> str | dict[str, Any]:
    text = str(value or "")
    if not contains_sensitive_text(text):
        return text
    return {
        "status": "redacted_sensitive_value",
        "sha256": hash_text(text),
    }


def print_recovery_paths(paths: list[Path]) -> None:
    if paths:
        print(f"Private recovery evidence: {paths[0].parent}")


def collision_safe_recovery_base(directory: Path) -> Path:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"recovery-{stamp}"
    suffix = 0
    endings = (
        ".json",
        ".md",
        ".md.artifact.json",
        ".forward.csv",
        ".forward.csv.artifact.json",
    )
    while any(Path(f"{base}{ending}").exists() for ending in endings):
        suffix += 1
        base = directory / f"recovery-{stamp}-{suffix:02d}"
    return base


def hash_text(value: Any) -> str | None:
    text = str(value or "")
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def comment_with_id(comments: list[dict[str, Any]], wanted: Any) -> dict[str, Any] | None:
    for comment in comments:
        if str(comment.get("id")) == str(wanted):
            return comment
    return None


def observed_guard_grade(observation: dict[str, Any]) -> Any:
    grade = observation.get("grade")
    return grade if grade not in {None, ""} else observation.get("score")


def object_has(obj: Any, name: str) -> bool:
    return name in obj if isinstance(obj, dict) else hasattr(obj, name)


def object_value(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def path_option(args: Any, name: str) -> Path | None:
    value = getattr(args, name, None)
    return Path(value) if value else None
