"""Transaction-safe Classic Quiz student-analysis report acquisition."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from canvasapi.exceptions import Conflict
from canvasapi.quiz import QuizReport
from canvasapi.util import combine_kwargs

from danvas import __version__
from danvas.artifacts import (
    commit_private_staged_pair,
    preflight_private_pair,
    private_staged_file,
)
from danvas.mutation import MutationMode, assert_canvas_mutation_allowed
from danvas.quiz import StudentAnalysisReport
from danvas.reports import create_report_run, should_write_report_run
from danvas.sanitize import sanitize_error

EVIDENCE_SCHEMA = "quiz-analysis-export-v1"
REPORT_TYPE = "student_analysis"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_REPORT_BYTES = 64 * 1024 * 1024
PROGRESS_PATH_RE = re.compile(r"/api/v1/progress/(?P<id>[1-9]\d*)/?$")
SURVEY_TYPES = {"survey", "graded_survey"}


class RequestStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    ACCEPTED = "accepted"
    REUSED = "reused"
    UNKNOWN_AFTER_EXCEPTION = "unknown_after_exception"
    CONFLICT = "conflict"


class ProgressStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"


class DownloadStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    DOWNLOADED_VERIFIED = "downloaded_verified"
    FAILED = "failed"
    ACCEPTED_UNVERIFIED = "accepted_unverified"


class OverallStatus(StrEnum):
    PLANNED = "planned"
    APPLIED_VERIFIED = "applied_verified"
    ACCEPTED_UNVERIFIED = "accepted_unverified"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass(frozen=True)
class QuizAnalysisExportIdentity:
    course_id: int
    quiz_id: int
    includes_all_versions: bool = False
    report_type: str = REPORT_TYPE

    def __post_init__(self) -> None:
        if self.course_id <= 0:
            raise ValueError("Canvas course ID must be positive.")
        if self.quiz_id <= 0:
            raise ValueError("Canvas quiz ID must be positive.")
        if self.report_type != REPORT_TYPE:
            raise ValueError(f"Unsupported Classic Quiz report type: {self.report_type}")


@dataclass(frozen=True)
class PollResult:
    status: ProgressStatus
    progress_id: int
    error: str = ""


def command_quiz_export_analysis(args: Any) -> None:
    """Acquire one official Classic Quiz student-analysis CSV."""
    from danvas.auth import canvas_from_args
    from danvas.mutation import mutation_mode_from_args

    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    quiz = course.get_quiz(args.quiz_id)
    identity = QuizAnalysisExportIdentity(
        course_id=int(args.course_id),
        quiz_id=int(args.quiz_id),
        includes_all_versions=bool(args.includes_all_versions),
    )
    try:
        result = execute_quiz_analysis_export(
            canvas=canvas,
            course=course,
            quiz=quiz,
            identity=identity,
            destination=Path(args.output),
            api_url=str(args.api_url),
            mutation_mode=mutation_mode_from_args(args),
            overwrite=bool(args.overwrite),
            poll_seconds=float(args.poll_seconds),
            timeout_seconds=float(args.timeout_seconds),
        )
    except FileExistsError as exc:
        raise SystemExit(
            f"Refusing to overwrite existing private output: {exc.filename or exc}"
        ) from exc
    except ValueError as exc:
        raise SystemExit(sanitize_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - sanitize remote failures at the boundary.
        raise SystemExit(f"Quiz analysis export failed: {_safe_exception(exc)}") from exc

    _print_quiz_analysis_export_result(result, output_display=str(args.output_display))
    _write_quiz_analysis_export_report(args, result)
    if result["overall_status"] not in {
        OverallStatus.PLANNED.value,
        OverallStatus.APPLIED_VERIFIED.value,
    }:
        raise SystemExit(1)


def validate_polling(*, poll_seconds: float, timeout_seconds: float) -> None:
    for name, value in (
        ("--poll-seconds", poll_seconds),
        ("--timeout-seconds", timeout_seconds),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number.")
    if poll_seconds > timeout_seconds:
        raise ValueError("--poll-seconds cannot exceed --timeout-seconds.")


def quiz_analysis_staging_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.download")


def preflight_quiz_analysis_destination(
    destination: Path, *, overwrite: bool
) -> tuple[Path, Path, Path]:
    data, sidecar = preflight_private_pair(destination, overwrite=overwrite)
    staging = quiz_analysis_staging_path(destination)
    if staging.exists() or staging.is_symlink():
        raise SystemExit(f"Refusing pre-existing private temporary file: {staging}")
    return data, sidecar, staging


def validate_supported_quiz(quiz: Any, identity: QuizAnalysisExportIdentity) -> None:
    quiz_id = _positive_int(_value(quiz, "id"))
    if quiz_id != identity.quiz_id:
        raise ValueError("Canvas returned a different Classic Quiz ID than requested.")
    quiz_type = str(_value(quiz, "quiz_type", "") or "").strip().casefold()
    if quiz_type not in SURVEY_TYPES:
        return
    anonymous = _value(quiz, "anonymous_submissions", None)
    if anonymous is True:
        raise ValueError(
            "Anonymous Survey report acquisition is not supported. Download the CSV "
            "manually and pass it to 'danvas quiz analysis'."
        )
    if anonymous is not False:
        raise ValueError(
            "Survey anonymity is unavailable; refusing to request a report. Confirm "
            "the Survey settings or use a manually downloaded CSV."
        )


def build_quiz_analysis_export_plan(
    quiz: Any,
    identity: QuizAnalysisExportIdentity,
    *,
    destination: Path,
) -> dict[str, Any]:
    validate_supported_quiz(quiz, identity)
    matches = matching_reports(quiz, identity)
    return {
        **_base_evidence(identity, destination=destination),
        "mode": MutationMode.PLAN.value,
        "overall_status": OverallStatus.PLANNED.value,
        "request_status": RequestStatus.NOT_ATTEMPTED.value,
        "progress_status": ProgressStatus.NOT_CHECKED.value,
        "download_status": DownloadStatus.NOT_ATTEMPTED.value,
        "matching_reports": [_safe_report_record(report) for report in matches],
        "safe_next_action": (
            "Review the report identity and private destination, then rerun with --apply."
        ),
    }


def execute_quiz_analysis_export(
    *,
    canvas: Any,
    course: Any,
    quiz: Any,
    identity: QuizAnalysisExportIdentity,
    destination: Path,
    api_url: str,
    mutation_mode: MutationMode,
    overwrite: bool = False,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    max_bytes: int = MAX_REPORT_BYTES,
) -> dict[str, Any]:
    validate_polling(poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)
    preflight_quiz_analysis_destination(destination, overwrite=overwrite)
    plan = build_quiz_analysis_export_plan(quiz, identity, destination=destination)
    if mutation_mode is MutationMode.PLAN:
        return plan

    evidence = {
        **plan,
        "mode": MutationMode.APPLY.value,
        "overall_status": OverallStatus.ACCEPTED_UNVERIFIED.value,
        "safe_next_action": "Inspect retained evidence and verify before retrying.",
    }
    before_ids = {
        report_id
        for record in plan["matching_reports"]
        if (report_id := _positive_int(record.get("report_id"))) is not None
    }
    report = _request_and_reconcile(
        quiz=quiz,
        identity=identity,
        before_ids=before_ids,
        mutation_mode=mutation_mode,
        evidence=evidence,
        api_url=api_url,
    )
    if report is None:
        return evidence

    report_id = _positive_int(_value(report, "id"))
    if report_id is None:
        return _settle_unverified(evidence, "Canvas report response has no stable report ID.")
    evidence["report_id"] = report_id

    initial_file_id = _report_file_id(report)
    if initial_file_id is not None:
        evidence["progress_status"] = ProgressStatus.COMPLETED.value
    else:
        try:
            progress_id = progress_id_from_report(report, api_url=api_url)
        except ValueError as exc:
            return _settle_unverified(evidence, str(exc), progress_unavailable=True)
        if progress_id is None:
            return _settle_unverified(
                evidence,
                "Canvas report is incomplete and has no stable progress identity.",
                progress_unavailable=True,
            )
        evidence["progress_id"] = progress_id
        poll = poll_quiz_report_progress(
            canvas,
            progress_id,
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
        evidence["progress_status"] = poll.status.value
        if poll.error:
            evidence["error"] = poll.error
        if poll.status is ProgressStatus.FAILED:
            evidence["overall_status"] = OverallStatus.FAILED.value
            evidence["safe_next_action"] = (
                "Canvas reports generation failed. Plan again after reviewing Canvas state."
            )
            return evidence
        if poll.status is not ProgressStatus.COMPLETED:
            return _settle_unverified(evidence, poll.error or "Report progress is unresolved.")

    try:
        authoritative = quiz.get_quiz_report(report_id)
    except Exception as exc:  # noqa: BLE001 - uncertain accepted mutation is retained.
        return _settle_unverified(
            evidence,
            f"Authoritative report readback failed: {_safe_exception(exc)}",
        )
    if not report_matches(authoritative, identity):
        return _settle_unverified(
            evidence, "Authoritative report readback does not match the requested identity."
        )

    file_id = _report_file_id(authoritative)
    if file_id is None:
        return _settle_unverified(
            evidence, "Completed report readback has no stable Canvas file ID."
        )
    evidence["file_id"] = file_id
    return _download_and_commit(
        course=course,
        identity=identity,
        evidence=evidence,
        destination=destination,
        file_id=file_id,
        api_url=api_url,
        overwrite=overwrite,
        max_bytes=max_bytes,
    )


def matching_reports(quiz: Any, identity: QuizAnalysisExportIdentity) -> list[Any]:
    return [report for report in quiz.get_all_quiz_reports() if report_matches(report, identity)]


def report_matches(report: Any, identity: QuizAnalysisExportIdentity) -> bool:
    if str(_value(report, "report_type", "") or "") != identity.report_type:
        return False
    report_quiz_id = _positive_int(_value(report, "quiz_id"))
    if report_quiz_id is not None and report_quiz_id != identity.quiz_id:
        return False
    report_course_id = _positive_int(_value(report, "course_id"))
    if report_course_id is not None and report_course_id != identity.course_id:
        return False
    observed_versions = _value(report, "includes_all_versions", None)
    if observed_versions is None:
        return identity.includes_all_versions is False
    return observed_versions is identity.includes_all_versions


def request_student_analysis_report(
    quiz: Any,
    identity: QuizAnalysisExportIdentity,
    *,
    mutation_mode: MutationMode,
) -> QuizReport:
    assert_canvas_mutation_allowed(mutation_mode, "quiz export-analysis report request")
    response = quiz._requester.request(  # noqa: SLF001
        "POST",
        f"courses/{identity.course_id}/quizzes/{identity.quiz_id}/reports",
        _kwargs=combine_kwargs(
            quiz_report={
                "report_type": identity.report_type,
                "includes_all_versions": identity.includes_all_versions,
            }
        ),
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Canvas report request returned a non-object response.")
    payload = {
        **payload,
        "course_id": identity.course_id,
        "quiz_id": identity.quiz_id,
    }
    return QuizReport(quiz._requester, payload)  # noqa: SLF001


def progress_id_from_report(report: Any, *, api_url: str) -> int | None:
    progress = _value(report, "progress", None)
    if isinstance(progress, dict):
        progress_id = _positive_int(progress.get("id"))
        if progress_id is not None:
            return progress_id
    raw_url = _value(report, "progress_url", None)
    if raw_url in (None, ""):
        return None
    parsed = urlsplit(str(raw_url))
    if _origin(parsed) != _origin(urlsplit(api_url)):
        raise ValueError("Canvas report progress URL has an unexpected origin.")
    match = PROGRESS_PATH_RE.fullmatch(parsed.path)
    if not match:
        raise ValueError("Canvas report progress URL has an unexpected path.")
    return int(match.group("id"))


def poll_quiz_report_progress(
    canvas: Any,
    progress_id: int,
    *,
    poll_seconds: float,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> PollResult:
    validate_polling(poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            progress = canvas.get_progress(progress_id)
        except Exception as exc:  # noqa: BLE001 - sanitized bounded evidence.
            return PollResult(
                ProgressStatus.UNAVAILABLE,
                progress_id,
                f"Progress read failed: {_safe_exception(exc)}",
            )
        raw_state = str(_value(progress, "workflow_state", "") or "").casefold()
        if raw_state == ProgressStatus.COMPLETED.value:
            return PollResult(ProgressStatus.COMPLETED, progress_id)
        if raw_state == ProgressStatus.FAILED.value:
            return PollResult(ProgressStatus.FAILED, progress_id, "Canvas report failed.")
        if raw_state not in {ProgressStatus.QUEUED.value, ProgressStatus.RUNNING.value}:
            return PollResult(
                ProgressStatus.UNAVAILABLE,
                progress_id,
                "Canvas report progress returned an unknown state.",
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            return PollResult(
                ProgressStatus.TIMED_OUT,
                progress_id,
                "Canvas report progress timed out; verify before retrying.",
            )
        sleep(min(poll_seconds, remaining))


def _request_and_reconcile(
    *,
    quiz: Any,
    identity: QuizAnalysisExportIdentity,
    before_ids: set[int],
    mutation_mode: MutationMode,
    evidence: dict[str, Any],
    api_url: str,
) -> Any | None:
    try:
        report = request_student_analysis_report(
            quiz, identity, mutation_mode=mutation_mode
        )
    except Conflict:
        matches = matching_reports(quiz, identity)
        candidates = [
            report
            for report in matches
            if _positive_int(_value(report, "id")) is not None
            and _report_file_id(report) is None
            and _progress_id_or_none(report, api_url=api_url) is not None
        ]
        if len(candidates) != 1:
            evidence["request_status"] = RequestStatus.CONFLICT.value
            evidence["overall_status"] = OverallStatus.CONFLICT.value
            evidence["error"] = "Canvas reported an in-progress report conflict."
            evidence["safe_next_action"] = "Plan again after the existing report settles."
            return None
        evidence["request_status"] = RequestStatus.CONFLICT.value
        return candidates[0]
    except Exception as exc:  # noqa: BLE001 - a POST may have been accepted.
        try:
            matches = matching_reports(quiz, identity)
        except Exception as read_exc:  # noqa: BLE001 - retain transport uncertainty.
            evidence["request_status"] = RequestStatus.UNKNOWN_AFTER_EXCEPTION.value
            return _no_report_after_exception(
                evidence,
                f"Report request outcome is unknown and reconciliation failed: "
                f"{_safe_exception(read_exc)}",
            )
        new_matches = [
            report
            for report in matches
            if (report_id := _positive_int(_value(report, "id"))) is not None
            and report_id not in before_ids
        ]
        evidence["request_status"] = RequestStatus.UNKNOWN_AFTER_EXCEPTION.value
        evidence["request_error"] = _safe_exception(exc)
        if len(new_matches) == 1:
            return new_matches[0]
        return _no_report_after_exception(
            evidence,
            "Report request may have been accepted, but no unique new report can be bound.",
        )

    if not report_matches(report, identity):
        evidence["request_status"] = RequestStatus.UNKNOWN_AFTER_EXCEPTION.value
        return _no_report_after_exception(
            evidence, "Canvas report response does not match the requested identity."
        )
    report_id = _positive_int(_value(report, "id"))
    evidence["request_status"] = (
        RequestStatus.REUSED.value if report_id in before_ids else RequestStatus.ACCEPTED.value
    )
    return report


def _download_and_commit(
    *,
    course: Any,
    identity: QuizAnalysisExportIdentity,
    evidence: dict[str, Any],
    destination: Path,
    file_id: int,
    api_url: str,
    overwrite: bool,
    max_bytes: int,
) -> dict[str, Any]:
    staging = quiz_analysis_staging_path(destination)
    try:
        file_obj = course.get_file(file_id)
        if _positive_int(_value(file_obj, "id")) != file_id:
            raise ValueError("Canvas returned a different file ID than requested.")
        byte_count = _download_canvas_file(
            file_obj,
            staging,
            api_url=api_url,
            max_bytes=max_bytes,
        )
        report = StudentAnalysisReport(staging)
        if not {"id", "submitted"} <= set(report.headers):
            raise ValueError(
                "Canvas student-analysis CSV is missing required id/submitted headers."
            )
        row_count = len(report.data_rows)
        question_count = len(report.question_pairs)
        completed_at = datetime.now(UTC).isoformat(timespec="seconds")
        commit_private_staged_pair(
            staging,
            destination,
            command="quiz export-analysis",
            overwrite=overwrite,
            sidecar_fields={
                "danvas_version": __version__,
                "course_id": identity.course_id,
                "quiz_id": identity.quiz_id,
                "report_id": evidence["report_id"],
                "progress_id": evidence.get("progress_id"),
                "canvas_file_id": file_id,
                "report_type": identity.report_type,
                "includes_all_versions": identity.includes_all_versions,
                "byte_count": byte_count,
                "row_count": row_count,
                "question_count": question_count,
                "completed_at": completed_at,
            },
        )
    except Exception as exc:  # noqa: BLE001 - sanitize all remote/file failures.
        if staging.exists() and not staging.is_symlink():
            staging.unlink()
        evidence["download_status"] = DownloadStatus.FAILED.value
        evidence["overall_status"] = OverallStatus.FAILED.value
        evidence["error"] = f"Private report download failed: {_safe_exception(exc)}"
        evidence["safe_next_action"] = (
            "Review the stable report/file IDs and plan again; do not blindly retry."
        )
        return evidence

    evidence.update(
        {
            "download_status": DownloadStatus.DOWNLOADED_VERIFIED.value,
            "overall_status": OverallStatus.APPLIED_VERIFIED.value,
            "byte_count": byte_count,
            "row_count": row_count,
            "question_count": question_count,
            "safe_next_action": (
                f"Run 'danvas quiz analysis {destination.name}' from the artifact directory."
            ),
        }
    )
    evidence.pop("error", None)
    return evidence


def _download_canvas_file(
    file_obj: Any,
    staging: Path,
    *,
    api_url: str,
    max_bytes: int,
) -> int:
    if max_bytes <= 0:
        raise ValueError("Maximum report size must be positive.")
    raw_url = str(_value(file_obj, "url", "") or "")
    parsed = urlsplit(raw_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Canvas report file has an unsafe download URL.")
    use_auth = _origin(parsed) == _origin(urlsplit(api_url))
    response = file_obj._requester.request(  # noqa: SLF001
        "GET", _url=raw_url, use_auth=use_auth
    )
    response.raise_for_status()
    declared = _positive_int(response.headers.get("Content-Length"))
    if declared is not None and declared > max_bytes:
        raise ValueError("Canvas report file exceeds the configured size limit.")
    total = 0
    with private_staged_file(staging) as handle:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Canvas report file exceeds the configured size limit.")
            handle.write(chunk)
    return total


def _print_quiz_analysis_export_result(
    result: dict[str, Any], *, output_display: str
) -> None:
    print(f"Classic Quiz analysis export: {result['mode']}")
    print(f"  Course ID: {result['course_id']}")
    print(f"  Quiz ID: {result['quiz_id']}")
    print(f"  Report scope: {'all versions' if result['includes_all_versions'] else 'current'}")
    print(f"  Status: {result['overall_status']}")
    print(f"  Request: {result['request_status']}")
    print(f"  Progress: {result['progress_status']}")
    print(f"  Download: {result['download_status']}")
    for label, key in (
        ("Report ID", "report_id"),
        ("Progress ID", "progress_id"),
        ("File ID", "file_id"),
    ):
        if result.get(key) is not None:
            print(f"  {label}: {result[key]}")
    if result.get("row_count") is not None:
        print(f"  Rows: {result['row_count']}")
        print(f"  Question pairs: {result['question_count']}")
    destination_label = "Private artifact" if result["mode"] == "apply" else "Private destination"
    print(f"  {destination_label}: {output_display}")
    if result.get("error"):
        print(f"  Error: {result['error']}")
    print(f"  Next: {result['safe_next_action']}")


def _write_quiz_analysis_export_report(args: Any, result: dict[str, Any]) -> None:
    project_root = Path(args.project_root)
    if not should_write_report_run(
        no_report=bool(args.no_report),
        legacy_output=False,
        report_root=Path(args.report_root) if args.report_root else None,
        report_dir=Path(args.report_dir) if args.report_dir else None,
        report_slug=str(args.report_slug) if args.report_slug else None,
        project_root=project_root,
    ):
        return
    report_run = create_report_run(
        command="quiz export-analysis",
        slug=str(args.report_slug or "quiz-analysis-export"),
        project_root=project_root,
        report_root=Path(args.report_root) if args.report_root else None,
        report_dir=Path(args.report_dir) if args.report_dir else None,
        course_id=int(result["course_id"]),
        private_data=True,
    )
    try:
        report_run.write_json("quiz-analysis-export.json", result)
        report_run.write_text(
            "quiz-analysis-export.md", _render_quiz_analysis_export_markdown(result)
        )
        status = (
            "success"
            if result["overall_status"]
            in {OverallStatus.PLANNED.value, OverallStatus.APPLIED_VERIFIED.value}
            else "failed"
        )
        report_run.finish(status)
        print(f"Private report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=_safe_exception(exc))
        raise


def _render_quiz_analysis_export_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Classic Quiz Analysis Export",
        "",
        "## Identity",
        "",
        f"- Course ID: `{result['course_id']}`",
        f"- Quiz ID: `{result['quiz_id']}`",
        f"- Report type: `{result['report_type']}`",
        f"- Includes all versions: `{str(result['includes_all_versions']).lower()}`",
        "",
        "## Result",
        "",
        f"- Overall: `{result['overall_status']}`",
        f"- Request: `{result['request_status']}`",
        f"- Progress: `{result['progress_status']}`",
        f"- Download: `{result['download_status']}`",
    ]
    for label, key in (
        ("Report ID", "report_id"),
        ("Progress ID", "progress_id"),
        ("Canvas file ID", "file_id"),
        ("Rows", "row_count"),
        ("Question pairs", "question_count"),
    ):
        if result.get(key) is not None:
            lines.append(f"- {label}: `{result[key]}`")
    lines.extend(("", "## Safe Next Action", "", str(result["safe_next_action"])))
    if result.get("error"):
        lines.extend(("", "## Error", "", str(result["error"])))
    return "\n".join(lines).rstrip() + "\n"


def _safe_report_record(report: Any) -> dict[str, Any]:
    return {
        "report_id": _positive_int(_value(report, "id")),
        "report_type": str(_value(report, "report_type", "") or ""),
        "includes_all_versions": bool(
            _value(report, "includes_all_versions", False)
        ),
        "progress_id": _progress_id_or_none(report, api_url=None),
        "file_id": _report_file_id(report),
    }


def _base_evidence(
    identity: QuizAnalysisExportIdentity, *, destination: Path
) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "course_id": identity.course_id,
        "quiz_id": identity.quiz_id,
        "report_type": identity.report_type,
        "includes_all_versions": identity.includes_all_versions,
        "artifact_name": destination.name,
    }


def _settle_unverified(
    evidence: dict[str, Any],
    error: str,
    *,
    progress_unavailable: bool = False,
) -> dict[str, Any]:
    evidence["overall_status"] = OverallStatus.ACCEPTED_UNVERIFIED.value
    evidence["download_status"] = DownloadStatus.ACCEPTED_UNVERIFIED.value
    if progress_unavailable:
        evidence["progress_status"] = ProgressStatus.UNAVAILABLE.value
    evidence["error"] = sanitize_error(error)
    evidence["safe_next_action"] = (
        "Plan again or inspect the stable report ID before any new --apply."
    )
    return evidence


def _no_report_after_exception(
    evidence: dict[str, Any], error: str
) -> None:
    _settle_unverified(evidence, error)
    return None


def _report_file_id(report: Any) -> int | None:
    file_value = _value(report, "file", None)
    return _positive_int(_value(file_value, "id"))


def _progress_id_or_none(report: Any, *, api_url: str | None) -> int | None:
    try:
        if api_url is None:
            progress = _value(report, "progress", None)
            if isinstance(progress, dict):
                return _positive_int(progress.get("id"))
            raw_url = str(_value(report, "progress_url", "") or "")
            match = PROGRESS_PATH_RE.fullmatch(urlsplit(raw_url).path)
            return int(match.group("id")) if match else None
        return progress_id_from_report(report, api_url=api_url)
    except ValueError:
        return None


def _safe_exception(exc: Exception) -> str:
    return sanitize_error(f"{type(exc).__name__}: {exc}")


def _origin(parsed: Any) -> tuple[str, str, int | None]:
    scheme = str(parsed.scheme).casefold()
    host = str(parsed.hostname or "").casefold()
    port = parsed.port
    if port is None and scheme == "https":
        port = 443
    return scheme, host, port


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
