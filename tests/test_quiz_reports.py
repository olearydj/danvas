from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from canvasapi.exceptions import Conflict

from danvas.artifacts import verify_private_sidecar
from danvas.mutation import MutationMode
from danvas.quiz_reports import (
    DEFAULT_POLL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    DownloadStatus,
    OverallStatus,
    ProgressStatus,
    QuizAnalysisExportIdentity,
    RequestStatus,
    build_quiz_analysis_export_plan,
    command_quiz_export_analysis,
    execute_quiz_analysis_export,
    poll_quiz_report_progress,
    preflight_quiz_analysis_destination,
    progress_id_from_report,
    report_matches,
    request_student_analysis_report,
    validate_polling,
    validate_supported_quiz,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sprint23"
CSV_BYTES = (FIXTURES / "identified-student-analysis.csv").read_bytes()


class FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.content = content
        self.headers = headers or {}
        self.error = error

    def json(self) -> dict[str, Any] | None:
        return self.payload

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [
            self.content[index : index + chunk_size]
            for index in range(0, len(self.content), chunk_size)
        ]


class FakeRequester:
    def __init__(
        self,
        *,
        post_payload: dict[str, Any] | None = None,
        post_error: Exception | None = None,
        download: FakeResponse | None = None,
    ) -> None:
        self.post_payload = post_payload
        self.post_error = post_error
        self.download = download or FakeResponse(content=CSV_BYTES)
        self.calls: list[tuple[str, str | None, str | None, Any, Any]] = []

    def request(
        self,
        method: str,
        endpoint: str | None = None,
        *,
        _url: str | None = None,
        _kwargs: Any = None,
        use_auth: bool = True,
    ) -> FakeResponse:
        self.calls.append((method, endpoint, _url, _kwargs, use_auth))
        if method == "POST":
            if self.post_error:
                raise self.post_error
            return FakeResponse(payload=self.post_payload)
        if method == "GET" and _url:
            return self.download
        raise AssertionError((method, endpoint, _url))


class FakeQuiz:
    def __init__(
        self,
        requester: FakeRequester,
        *,
        reports: list[list[Any]] | None = None,
        readback: Any | None = None,
        quiz_id: int = 202,
        quiz_type: str = "assignment",
        anonymous_submissions: bool | None = False,
    ) -> None:
        self._requester = requester
        self.id = quiz_id
        self.quiz_type = quiz_type
        if anonymous_submissions is not None:
            self.anonymous_submissions = anonymous_submissions
        self.report_batches = reports or [[]]
        self.report_calls = 0
        self.readback = readback

    def get_all_quiz_reports(self) -> list[Any]:
        index = min(self.report_calls, len(self.report_batches) - 1)
        self.report_calls += 1
        return self.report_batches[index]

    def get_quiz_report(self, report_id: int) -> Any:
        assert self.readback is not None
        assert report_id == self.readback.id
        return self.readback


class FakeCanvas:
    def __init__(self, states: list[str] | None = None, *, error: Exception | None = None):
        self.states = states or []
        self.error = error
        self.calls: list[int] = []

    def get_progress(self, progress_id: int) -> Any:
        self.calls.append(progress_id)
        if self.error:
            raise self.error
        if not self.states:
            raise AssertionError("No progress state configured")
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return SimpleNamespace(id=progress_id, workflow_state=state)


class FakeCourse:
    def __init__(self, file_obj: Any):
        self.file_obj = file_obj
        self.calls: list[int] = []

    def get_file(self, file_id: int) -> Any:
        self.calls.append(file_id)
        return self.file_obj


def identity(*, all_versions: bool = False) -> QuizAnalysisExportIdentity:
    return QuizAnalysisExportIdentity(
        course_id=101,
        quiz_id=202,
        includes_all_versions=all_versions,
    )


def export_result(*, status: OverallStatus = OverallStatus.PLANNED) -> dict[str, Any]:
    return {
        "schema_version": "quiz-analysis-export-v1",
        "mode": "plan" if status is OverallStatus.PLANNED else "apply",
        "course_id": 101,
        "quiz_id": 202,
        "report_type": "student_analysis",
        "includes_all_versions": False,
        "overall_status": status.value,
        "request_status": RequestStatus.NOT_ATTEMPTED.value,
        "progress_status": ProgressStatus.NOT_CHECKED.value,
        "download_status": DownloadStatus.NOT_ATTEMPTED.value,
        "report_id": None,
        "progress_id": None,
        "file_id": None,
        "row_count": None,
        "question_count": None,
        "error": "",
        "safe_next_action": "Review the plan, then add --apply only after authorization.",
    }


def report(
    report_id: int = 303,
    *,
    all_versions: bool = False,
    progress_url: str | None = None,
    file_id: int | None = None,
    report_type: str = "student_analysis",
) -> Any:
    values: dict[str, Any] = {
        "id": report_id,
        "course_id": 101,
        "quiz_id": 202,
        "report_type": report_type,
        "includes_all_versions": all_versions,
    }
    if progress_url is not None:
        values["progress_url"] = progress_url
    if file_id is not None:
        values["file"] = {"id": file_id, "url": "https://canvas.example.edu/protected"}
    return SimpleNamespace(**values)


def file_object(
    requester: FakeRequester,
    *,
    file_id: int = 404,
    url: str = "https://canvas.example.edu/files/404/download?verifier=PROTECTED",
) -> Any:
    return SimpleNamespace(id=file_id, url=url, _requester=requester)


def test_identity_and_polling_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="course ID must be positive"):
        QuizAnalysisExportIdentity(course_id=0, quiz_id=202)
    with pytest.raises(ValueError, match="quiz ID must be positive"):
        QuizAnalysisExportIdentity(course_id=101, quiz_id=0)
    with pytest.raises(ValueError, match="Unsupported"):
        QuizAnalysisExportIdentity(course_id=101, quiz_id=202, report_type="item_analysis")

    validate_polling(
        poll_seconds=DEFAULT_POLL_SECONDS,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    )
    for poll_seconds, timeout_seconds in ((0, 120), (2, 0), (float("nan"), 120), (3, 2)):
        with pytest.raises(ValueError):
            validate_polling(poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)


def test_anonymous_and_ambiguous_surveys_refuse_before_report_listing() -> None:
    requested = identity()
    requester = FakeRequester()
    anonymous = FakeQuiz(
        requester, quiz_type="graded_survey", anonymous_submissions=True
    )
    ambiguous = FakeQuiz(requester, quiz_type="survey", anonymous_submissions=None)

    with pytest.raises(ValueError, match="Anonymous Survey"):
        build_quiz_analysis_export_plan(
            anonymous, requested, destination=Path("student-analysis.csv")
        )
    with pytest.raises(ValueError, match="anonymity is unavailable"):
        validate_supported_quiz(ambiguous, requested)
    assert anonymous.report_calls == 0
    assert requester.calls == []


def test_private_destination_preflight_refuses_data_sidecar_and_staging(
    tmp_path: Path,
) -> None:
    output = tmp_path / "student-analysis.csv"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preflight_quiz_analysis_destination(output, overwrite=False)

    output.unlink()
    sidecar = output.with_name(f"{output.name}.artifact.json")
    sidecar.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preflight_quiz_analysis_destination(output, overwrite=False)

    sidecar.unlink()
    staging = output.with_name(f".{output.name}.download")
    staging.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit, match="pre-existing private temporary"):
        preflight_quiz_analysis_destination(output, overwrite=False)


def test_plan_lists_only_sanitized_stable_report_fields() -> None:
    raw = SimpleNamespace(
        id=303,
        report_type="student_analysis",
        includes_all_versions=False,
        progress_url="https://canvas.example.edu/api/v1/progress/505?token=PROTECTED",
        file={
            "id": 404,
            "url": "https://canvas.example.edu/files/404?verifier=PROTECTED",
        },
    )
    quiz = FakeQuiz(FakeRequester(), reports=[[raw]])

    plan = build_quiz_analysis_export_plan(
        quiz, identity(), destination=Path("student-analysis.csv")
    )

    assert plan["overall_status"] == OverallStatus.PLANNED.value
    assert plan["matching_reports"] == [
        {
            "report_id": 303,
            "report_type": "student_analysis",
            "includes_all_versions": False,
            "progress_id": 505,
            "file_id": 404,
        }
    ]
    assert "PROTECTED" not in json.dumps(plan)


def test_report_identity_requires_type_scope_and_stable_ids() -> None:
    requested = identity(all_versions=True)

    assert report_matches(report(all_versions=True), requested)
    assert not report_matches(report(all_versions=False), requested)
    assert not report_matches(report(all_versions=True, report_type="item_analysis"), requested)
    assert not report_matches(
        SimpleNamespace(
            id=303,
            course_id=999,
            quiz_id=202,
            report_type="student_analysis",
            includes_all_versions=True,
        ),
        requested,
    )


def test_raw_report_request_encodes_nested_fields_and_requires_apply() -> None:
    payload = {
        "id": 303,
        "report_type": "student_analysis",
        "includes_all_versions": True,
    }
    requester = FakeRequester(post_payload=payload)
    quiz = FakeQuiz(requester)

    with pytest.raises(RuntimeError, match="mutation blocked"):
        request_student_analysis_report(
            quiz, identity(all_versions=True), mutation_mode=MutationMode.PLAN
        )
    assert requester.calls == []

    created = request_student_analysis_report(
        quiz, identity(all_versions=True), mutation_mode=MutationMode.APPLY
    )
    assert created.id == 303
    assert created.course_id == 101
    assert created.quiz_id == 202
    assert requester.calls == [
        (
            "POST",
            "courses/101/quizzes/202/reports",
            None,
            [
                ("quiz_report[report_type]", "student_analysis"),
                ("quiz_report[includes_all_versions]", True),
            ],
            True,
        )
    ]


def test_progress_url_requires_expected_origin_path_and_numeric_id() -> None:
    good = report(
        progress_url="https://canvas.example.edu/api/v1/progress/505?token=PROTECTED"
    )
    assert progress_id_from_report(good, api_url="https://canvas.example.edu/") == 505

    with pytest.raises(ValueError, match="unexpected origin"):
        progress_id_from_report(
            report(progress_url="https://attacker.example/api/v1/progress/505"),
            api_url="https://canvas.example.edu/",
        )
    with pytest.raises(ValueError, match="unexpected path"):
        progress_id_from_report(
            report(progress_url="https://canvas.example.edu/api/v1/files/505"),
            api_url="https://canvas.example.edu/",
        )


def test_progress_polling_handles_completion_failure_timeout_and_unknown() -> None:
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    completed = poll_quiz_report_progress(
        FakeCanvas(["queued", "running", "completed"]),
        505,
        poll_seconds=2,
        timeout_seconds=10,
        sleep=sleep,
        monotonic=lambda: clock[0],
    )
    assert completed.status is ProgressStatus.COMPLETED

    failed = poll_quiz_report_progress(
        FakeCanvas(["failed"]),
        505,
        poll_seconds=2,
        timeout_seconds=10,
    )
    assert failed.status is ProgressStatus.FAILED

    clock[0] = 0
    timed_out = poll_quiz_report_progress(
        FakeCanvas(["running"]),
        505,
        poll_seconds=2,
        timeout_seconds=3,
        sleep=sleep,
        monotonic=lambda: clock[0],
    )
    assert timed_out.status is ProgressStatus.TIMED_OUT

    unknown = poll_quiz_report_progress(
        FakeCanvas(["mystery"]),
        505,
        poll_seconds=2,
        timeout_seconds=10,
    )
    assert unknown.status is ProgressStatus.UNAVAILABLE


def test_plan_mode_performs_no_request_progress_or_download(tmp_path: Path) -> None:
    requester = FakeRequester(post_payload={})
    quiz = FakeQuiz(requester)
    canvas = FakeCanvas(["completed"])
    course = FakeCourse(file_object(requester))
    output = tmp_path / "student-analysis.csv"

    result = execute_quiz_analysis_export(
        canvas=canvas,
        course=course,
        quiz=quiz,
        identity=identity(),
        destination=output,
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.PLAN,
    )

    assert result["overall_status"] == OverallStatus.PLANNED.value
    assert requester.calls == []
    assert canvas.calls == []
    assert course.calls == []
    assert not output.exists()


def test_apply_polls_downloads_and_commits_verified_private_pair(tmp_path: Path) -> None:
    running = {
        "id": 303,
        "report_type": "student_analysis",
        "includes_all_versions": False,
        "progress_url": "https://canvas.example.edu/api/v1/progress/505?token=PROTECTED",
    }
    download = FakeResponse(
        content=CSV_BYTES,
        headers={"Content-Length": str(len(CSV_BYTES)), "Content-Type": "text/csv"},
    )
    requester = FakeRequester(post_payload=running, download=download)
    readback = report(file_id=404)
    quiz = FakeQuiz(requester, readback=readback)
    canvas = FakeCanvas(["queued", "completed"])
    course = FakeCourse(file_object(requester))
    output = tmp_path / "student-analysis.csv"

    result = execute_quiz_analysis_export(
        canvas=canvas,
        course=course,
        quiz=quiz,
        identity=identity(),
        destination=output,
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
        poll_seconds=1,
        timeout_seconds=10,
        sleep=lambda _seconds: None,
    )

    sidecar = output.with_name(f"{output.name}.artifact.json")
    assert result["overall_status"] == OverallStatus.APPLIED_VERIFIED.value
    assert result["request_status"] == RequestStatus.ACCEPTED.value
    assert result["progress_status"] == ProgressStatus.COMPLETED.value
    assert result["download_status"] == DownloadStatus.DOWNLOADED_VERIFIED.value
    assert result["row_count"] == 2
    assert result["question_count"] == 2
    assert output.read_bytes() == CSV_BYTES
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert verify_private_sidecar(output)
    retained = sidecar.read_text(encoding="utf-8")
    assert "PROTECTED" not in retained
    assert "https://" not in retained
    assert json.loads(retained)["canvas_file_id"] == 404


def test_external_signed_file_download_does_not_send_canvas_bearer(tmp_path: Path) -> None:
    post = report(file_id=404).__dict__
    requester = FakeRequester(post_payload=post, download=FakeResponse(content=CSV_BYTES))
    readback = report(file_id=404)
    quiz = FakeQuiz(requester, readback=readback)
    course = FakeCourse(
        file_object(
            requester,
            url="https://files.example-cdn.test/download?verifier=PROTECTED",
        )
    )

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(),
        course=course,
        quiz=quiz,
        identity=identity(),
        destination=tmp_path / "student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
    )

    assert result["overall_status"] == OverallStatus.APPLIED_VERIFIED.value
    get_call = next(call for call in requester.calls if call[0] == "GET")
    assert get_call[-1] is False


def test_409_continues_only_with_one_exact_in_progress_report(tmp_path: Path) -> None:
    in_progress = report(
        progress_url="https://canvas.example.edu/api/v1/progress/505"
    )
    requester = FakeRequester(post_error=Conflict("already generating"))
    quiz = FakeQuiz(
        requester,
        reports=[[], [in_progress]],
        readback=report(file_id=404),
    )
    course = FakeCourse(file_object(requester))

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(["completed"]),
        course=course,
        quiz=quiz,
        identity=identity(),
        destination=tmp_path / "student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
    )

    assert result["overall_status"] == OverallStatus.APPLIED_VERIFIED.value
    assert result["request_status"] == RequestStatus.CONFLICT.value
    assert sum(call[0] == "POST" for call in requester.calls) == 1


def test_409_with_ambiguous_matches_stops_without_download(tmp_path: Path) -> None:
    first = report(
        303, progress_url="https://canvas.example.edu/api/v1/progress/505"
    )
    second = report(
        304, progress_url="https://canvas.example.edu/api/v1/progress/506"
    )
    requester = FakeRequester(post_error=Conflict("already generating"))
    quiz = FakeQuiz(requester, reports=[[], [first, second]])
    course = FakeCourse(file_object(requester))

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(),
        course=course,
        quiz=quiz,
        identity=identity(),
        destination=tmp_path / "student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
    )

    assert result["overall_status"] == OverallStatus.CONFLICT.value
    assert course.calls == []
    assert sum(call[0] == "POST" for call in requester.calls) == 1


def test_request_exception_binds_only_one_new_report(tmp_path: Path) -> None:
    new = report(progress_url="https://canvas.example.edu/api/v1/progress/505")
    requester = FakeRequester(post_error=TimeoutError("token=SECRET https://protected"))
    quiz = FakeQuiz(
        requester,
        reports=[[], [new]],
        readback=report(file_id=404),
    )

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(["completed"]),
        course=FakeCourse(file_object(requester)),
        quiz=quiz,
        identity=identity(),
        destination=tmp_path / "student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
    )

    assert result["overall_status"] == OverallStatus.APPLIED_VERIFIED.value
    assert result["request_status"] == RequestStatus.UNKNOWN_AFTER_EXCEPTION.value
    assert "SECRET" not in result["request_error"]
    assert "https://" not in result["request_error"]
    assert sum(call[0] == "POST" for call in requester.calls) == 1


def test_unmatched_request_exception_is_accepted_unverified(tmp_path: Path) -> None:
    requester = FakeRequester(post_error=TimeoutError("network timeout"))
    quiz = FakeQuiz(requester, reports=[[], []])

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(),
        course=FakeCourse(file_object(requester)),
        quiz=quiz,
        identity=identity(),
        destination=tmp_path / "student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
    )

    assert result["overall_status"] == OverallStatus.ACCEPTED_UNVERIFIED.value
    assert result["request_status"] == RequestStatus.UNKNOWN_AFTER_EXCEPTION.value
    assert "before any new --apply" in result["safe_next_action"]
    assert sum(call[0] == "POST" for call in requester.calls) == 1


@pytest.mark.parametrize(
    ("download", "max_bytes", "error_fragment"),
    [
        (FakeResponse(content=b"not,csv\n1,2\n"), 1024, "required id/submitted"),
        (FakeResponse(content=CSV_BYTES), 8, "size limit"),
        (
            FakeResponse(error=RuntimeError("url=https://protected?token=SECRET")),
            1024,
            "RuntimeError",
        ),
    ],
)
def test_invalid_oversized_and_failed_downloads_do_not_commit(
    tmp_path: Path,
    download: FakeResponse,
    max_bytes: int,
    error_fragment: str,
) -> None:
    post = report(file_id=404).__dict__
    requester = FakeRequester(post_payload=post, download=download)
    quiz = FakeQuiz(requester, readback=report(file_id=404))
    output = tmp_path / "student-analysis.csv"

    result = execute_quiz_analysis_export(
        canvas=FakeCanvas(),
        course=FakeCourse(file_object(requester)),
        quiz=quiz,
        identity=identity(),
        destination=output,
        api_url="https://canvas.example.edu/",
        mutation_mode=MutationMode.APPLY,
        max_bytes=max_bytes,
    )

    assert result["overall_status"] == OverallStatus.FAILED.value
    assert result["download_status"] == DownloadStatus.FAILED.value
    assert error_fragment in result["error"]
    assert "SECRET" not in result["error"]
    assert "https://" not in result["error"]
    assert not output.exists()
    assert not output.with_name(f"{output.name}.artifact.json").exists()
    assert not output.with_name(f".{output.name}.download").exists()


def test_zero_row_and_zero_question_reports_commit_truthful_counts(tmp_path: Path) -> None:
    for name, expected_rows in (
        ("zero-row-student-analysis.csv", 0),
        ("zero-question-student-analysis.csv", 1),
    ):
        content = (FIXTURES / name).read_bytes()
        requester = FakeRequester(
            post_payload=report(file_id=404).__dict__,
            download=FakeResponse(content=content),
        )
        quiz = FakeQuiz(requester, readback=report(file_id=404))
        output = tmp_path / name

        result = execute_quiz_analysis_export(
            canvas=FakeCanvas(),
            course=FakeCourse(file_object(requester)),
            quiz=quiz,
            identity=identity(),
            destination=output,
            api_url="https://canvas.example.edu/",
            mutation_mode=MutationMode.APPLY,
        )

        assert result["overall_status"] == OverallStatus.APPLIED_VERIFIED.value
        assert result["row_count"] == expected_rows
        assert result["question_count"] == 0


def test_preexisting_staging_refuses_before_canvas_reads(tmp_path: Path) -> None:
    output = tmp_path / "student-analysis.csv"
    output.with_name(f".{output.name}.download").write_text("occupied", encoding="utf-8")
    requester = FakeRequester(post_payload={})
    quiz = FakeQuiz(requester)

    with pytest.raises(SystemExit, match="pre-existing private temporary"):
        execute_quiz_analysis_export(
            canvas=FakeCanvas(),
            course=FakeCourse(file_object(requester)),
            quiz=quiz,
            identity=identity(),
            destination=output,
            api_url="https://canvas.example.edu/",
            mutation_mode=MutationMode.PLAN,
        )
    assert quiz.report_calls == 0
    assert requester.calls == []


def test_command_adapter_prints_aggregate_and_writes_private_plan_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "Etc/UTC"\n',
        encoding="utf-8",
    )
    quiz = object()
    course = SimpleNamespace(get_quiz=lambda quiz_id: quiz)
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.auth.canvas_from_args", lambda args: canvas)
    observed: dict[str, Any] = {}

    def fake_execute(**kwargs: Any) -> dict[str, Any]:
        observed.update(kwargs)
        return export_result()

    monkeypatch.setattr("danvas.quiz_reports.execute_quiz_analysis_export", fake_execute)
    output = tmp_path / ".danvas" / "private" / "quizzes" / "quiz-202" / "student-analysis.csv"
    args = SimpleNamespace(
        course_id=101,
        quiz_id=202,
        includes_all_versions=False,
        output=str(output),
        output_display=".danvas/private/quizzes/quiz-202/student-analysis.csv",
        api_url="https://canvas.example.edu/",
        mutation_mode="plan",
        dry_run=True,
        overwrite=False,
        poll_seconds=2.0,
        timeout_seconds=120.0,
        project_root=str(tmp_path),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_quiz_export_analysis(args)

    rendered = capsys.readouterr().out
    assert "Classic Quiz analysis export: plan" in rendered
    assert "Status: planned" in rendered
    assert "Course ID: 101" in rendered
    assert "Quiz ID: 202" in rendered
    assert ".danvas/private/quizzes/quiz-202/student-analysis.csv" in rendered
    assert "https://" not in rendered
    assert "PROTECTED" not in rendered
    assert observed["mutation_mode"] is MutationMode.PLAN
    report_dirs = list((config_dir / "private" / "reports").iterdir())
    assert len(report_dirs) == 1
    report_dir = report_dirs[0]
    assert (report_dir / "quiz-analysis-export.json").is_file()
    assert (report_dir / "quiz-analysis-export.md").is_file()
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "quiz export-analysis"
    assert manifest["may_contain_private_student_data"] is True


def test_command_adapter_exits_nonzero_after_uncertain_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    quiz = object()
    course = SimpleNamespace(get_quiz=lambda quiz_id: quiz)
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.auth.canvas_from_args", lambda args: canvas)
    uncertain = export_result(status=OverallStatus.ACCEPTED_UNVERIFIED)
    uncertain.update(
        {
            "request_status": RequestStatus.UNKNOWN_AFTER_EXCEPTION.value,
            "error": "TimeoutError: connection outcome unavailable",
            "safe_next_action": "Verify existing reports before any new --apply.",
        }
    )
    monkeypatch.setattr(
        "danvas.quiz_reports.execute_quiz_analysis_export", lambda **kwargs: uncertain
    )
    args = SimpleNamespace(
        course_id=101,
        quiz_id=202,
        includes_all_versions=False,
        output=str(tmp_path / "student-analysis.csv"),
        output_display=str(tmp_path / "student-analysis.csv"),
        api_url="https://canvas.example.edu/",
        mutation_mode="apply",
        dry_run=False,
        overwrite=False,
        poll_seconds=2.0,
        timeout_seconds=120.0,
        project_root=str(tmp_path),
        no_report=True,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        command_quiz_export_analysis(args)

    assert exc_info.value.code == 1
    rendered = capsys.readouterr().out
    assert "Status: accepted_unverified" in rendered
    assert "before any new --apply" in rendered
