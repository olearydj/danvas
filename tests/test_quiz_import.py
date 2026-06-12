from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.quiz_import import command_quiz_import_qti


class FakeQuiz:
    def __init__(self, quiz_id: int, title: str, **attrs: Any) -> None:
        self.id = quiz_id
        self.title = title
        self.assignment_id = attrs.pop("assignment_id", None)
        self.html_url = attrs.pop("html_url", "")
        self.published = attrs.pop("published", False)
        for key, value in attrs.items():
            setattr(self, key, value)
        self.edits: list[dict[str, Any]] = []

    def edit(self, quiz: dict[str, Any] | None = None) -> FakeQuiz:
        payload = quiz or {}
        self.edits.append(payload)
        for key, value in payload.items():
            setattr(self, key, value)
        return self


class FakeCourse:
    def __init__(
        self,
        quizzes: list[FakeQuiz],
        migration_states: list[str],
        new_quizzes: list[FakeQuiz],
    ) -> None:
        self.quizzes = list(quizzes)
        self.migration_states = list(migration_states)
        self.new_quizzes = list(new_quizzes)
        self.migration_kwargs: dict[str, Any] | None = None

    def get_quizzes(self) -> list[FakeQuiz]:
        return list(self.quizzes)

    def get_quiz(self, quiz_id: int) -> FakeQuiz:
        return next(quiz for quiz in self.quizzes if quiz.id == quiz_id)

    def create_content_migration(self, **kwargs: Any) -> Any:
        self.migration_kwargs = kwargs
        return SimpleNamespace(
            id=900,
            pre_attachment={
                "upload_url": "https://upload.test/qti",
                "upload_params": {"key": "abc"},
            },
        )

    def get_content_migration(self, migration_id: int) -> Any:
        state = self.migration_states.pop(0) if self.migration_states else "running"
        if state == "completed":
            for quiz in self.new_quizzes:
                if quiz not in self.quizzes:
                    self.quizzes.append(quiz)
        migration = SimpleNamespace(id=migration_id, workflow_state=state)
        migration.get_migration_issues = lambda: [
            SimpleNamespace(description="unsupported question type")
        ]
        return migration


class FakeRequests:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, data: Any = None, files: Any = None, timeout: Any = None) -> Any:
        self.posts.append({"url": url, "data": data, "files": list(files or {})})
        return SimpleNamespace(status_code=self.status_code)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def import_args(package: Path, **overrides: Any) -> Any:
    defaults: dict[str, Any] = {
        "course_id": 101,
        "package": str(package),
        "title": None,
        "assignment_group_id": None,
        "due_at": None,
        "unlock_at": None,
        "lock_at": None,
        "time_limit": None,
        "allowed_attempts": None,
        "publish": None,
        "match_title": None,
        "poll_seconds": 0.5,
        "timeout_seconds": 10.0,
        "dry_run": False,
        "output": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def setup_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    course: FakeCourse,
) -> tuple[Path, FakeRequests, FakeTime]:
    package = tmp_path / "chap07.zip"
    package.write_bytes(b"qti-zip-bytes")
    fake_requests = FakeRequests()
    fake_time = FakeTime()
    monkeypatch.setattr(
        "danvas.quiz_import.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )
    monkeypatch.setattr("danvas.quiz_import.requests", fake_requests)
    monkeypatch.setattr("danvas.quiz_import.time", fake_time)
    return package, fake_requests, fake_time


def test_dry_run_previews_without_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    package = tmp_path / "chap07.zip"
    package.write_bytes(b"qti")

    def fail(args: Any) -> Any:
        raise AssertionError("canvas_from_args should not be called in dry run")

    monkeypatch.setattr("danvas.quiz_import.canvas_from_args", fail)

    command_quiz_import_qti(import_args(package, dry_run=True, publish=True, time_limit=30))

    out = capsys.readouterr().out
    assert "Dry run" in out
    assert '"published": true' in out
    assert '"time_limit": 30' in out


def test_import_applies_settings_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    existing = FakeQuiz(1, "Old Quiz")
    imported = FakeQuiz(
        2,
        "Chapter 7 Quiz",
        assignment_id=98,
        html_url="https://canvas.test/quizzes/2",
        points_possible=20,
        question_count=10,
        due_at="",
        unlock_at="",
        lock_at="",
        time_limit=None,
        allowed_attempts=None,
        quiz_type="assignment",
    )
    course = FakeCourse([existing], ["running", "completed"], [imported])
    package, fake_requests, fake_time = setup_import(monkeypatch, tmp_path, course)
    output = tmp_path / "report.json"
    args = import_args(
        package, due_at="2026-06-20T04:59:00Z", publish=True, output=str(output)
    )

    command_quiz_import_qti(args)

    assert course.migration_kwargs == {
        "migration_type": "qti_converter",
        "pre_attachment": {"name": "chap07.zip", "size": len(b"qti-zip-bytes")},
    }
    assert fake_requests.posts == [
        {"url": "https://upload.test/qti", "data": {"key": "abc"}, "files": ["file"]}
    ]
    assert imported.edits == [{"due_at": "2026-06-20T04:59:00Z", "published": True}]
    assert fake_time.sleeps == [0.5]

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "verified"
    assert report["quiz"]["id"] == 2
    assert report["quiz"]["assignment_id"] == 98
    assert report["migration_id"] == 900
    out = capsys.readouterr().out
    assert "Verification: verified" in out


def test_failed_migration_reports_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse([], ["failed"], [])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)

    with pytest.raises(SystemExit, match="failed.*unsupported question type"):
        command_quiz_import_qti(import_args(package))


def test_migration_timeout_exits_with_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse([], [], [])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)

    with pytest.raises(SystemExit, match="did not finish within 2s"):
        command_quiz_import_qti(import_args(package, timeout_seconds=2.0, poll_seconds=1.5))


def test_ambiguous_new_quizzes_require_match_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = FakeQuiz(2, "Chapter 7 Quiz")
    second = FakeQuiz(3, "Chapter 7 Quiz Practice")
    course = FakeCourse([], ["completed"], [first, second])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)

    with pytest.raises(SystemExit, match="Pass --match-title"):
        command_quiz_import_qti(import_args(package))


def test_match_title_selects_quiz_and_refuses_ambiguity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = FakeQuiz(2, "Chapter 7 Quiz")
    second = FakeQuiz(3, "Chapter 7 Quiz Practice")
    course = FakeCourse([], ["completed"], [first, second])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)

    command_quiz_import_qti(import_args(package, match_title="chapter 7 quiz"))

    duplicate = FakeQuiz(4, "Chapter 7 Quiz")
    course = FakeCourse([], ["completed"], [first, duplicate])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)
    with pytest.raises(SystemExit, match="ambiguous"):
        command_quiz_import_qti(import_args(package, match_title="Chapter 7 Quiz"))


def test_settings_mismatch_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class StubbornQuiz(FakeQuiz):
        def edit(self, quiz: dict[str, Any] | None = None) -> FakeQuiz:
            payload = dict(quiz or {})
            payload.pop("published", None)
            return super().edit(payload)

    imported = StubbornQuiz(2, "Chapter 7 Quiz", published=False)
    course = FakeCourse([], ["completed"], [imported])
    package, _requests, _time = setup_import(monkeypatch, tmp_path, course)

    with pytest.raises(SystemExit):
        command_quiz_import_qti(import_args(package, publish=True))

    out = capsys.readouterr().out
    assert "published: MISMATCH" in out
    assert "Verification: settings mismatch" in out


def test_upload_failure_exits_with_http_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse([], ["completed"], [])
    package, fake_requests, _time = setup_import(monkeypatch, tmp_path, course)
    fake_requests.status_code = 403

    with pytest.raises(SystemExit, match="HTTP 403"):
        command_quiz_import_qti(import_args(package))
