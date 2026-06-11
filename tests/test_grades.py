from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from danvas.grades import (
    command_grades_post,
    command_grades_verify,
    comment_exists,
    grade_matches,
    load_grade_rows,
)


class FakeSubmission:
    def __init__(
        self,
        score: float | None = None,
        grade: str | None = None,
        comments: list[dict[str, str]] | None = None,
    ) -> None:
        self.score = score
        self.grade = grade
        self.submission_comments = comments or []
        self.edits: list[dict[str, Any]] = []

    def edit(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)


class FakeAssignment:
    def __init__(self, submissions: dict[int, FakeSubmission]) -> None:
        self.submissions = submissions

    def get_submission(self, user_id: int, include: list[str] | None = None) -> FakeSubmission:
        return self.submissions[user_id]


class FakeCanvas:
    def __init__(self, assignment: Any) -> None:
        self.assignment = assignment

    def get_course(self, course_id: int) -> FakeCanvas:
        return self

    def get_assignment(self, assignment_id: int) -> Any:
        return self.assignment


def write_grades_csv(path: Path, rows: list[str]) -> None:
    path.write_text("CanvasID,Name,Grade,Comment\n" + "\n".join(rows) + "\n", encoding="utf-8")


def post_args(grades_csv: Path, **overrides: Any) -> Any:
    from types import SimpleNamespace

    defaults = {
        "course_id": 101,
        "assignment_id": 5,
        "grades_csv": str(grades_csv),
        "dry_run": False,
        "sleep_seconds": 0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_grade_matches_numeric_score() -> None:
    assert grade_matches(FakeSubmission(score=90.0), "90")
    assert not grade_matches(FakeSubmission(score=85.0), "90")
    assert not grade_matches(FakeSubmission(), "90")


def test_grade_matches_letter_grade_with_numeric_score() -> None:
    submission = FakeSubmission(score=85.0, grade="B")

    assert grade_matches(submission, "B")
    assert grade_matches(submission, "85")
    assert not grade_matches(submission, "A")


def test_comment_exists_with_dict_and_object_comments() -> None:
    assert comment_exists(FakeSubmission(comments=[{"comment": "Good work."}]), "Good work.")
    assert not comment_exists(FakeSubmission(comments=[{"comment": "Other."}]), "Good work.")
    assert not comment_exists(FakeSubmission(), "Good work.")


def test_load_grade_rows_requires_columns(tmp_path: Path) -> None:
    path = tmp_path / "grades.csv"
    path.write_text("CanvasID,Name\n1,Doe\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must include Grade"):
        load_grade_rows(path)


def test_grades_post_skips_existing_and_posts_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,', '2,"Smith, Pat",80,'])
    posted = FakeSubmission(score=90.0, grade="90")
    unposted = FakeSubmission()
    canvas = FakeCanvas(FakeAssignment({1: posted, 2: unposted}))
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    command_grades_post(post_args(grades_csv))

    assert posted.edits == []
    assert unposted.edits == [{"submission": {"posted_grade": "80"}}]
    out = capsys.readouterr().out
    assert "already posted" in out
    assert "Posted: 1, Already present: 1, Failed: 0" in out


def test_grades_post_letter_grade_rerun_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",B,'])
    submission = FakeSubmission(score=85.0, grade="B")
    canvas = FakeCanvas(FakeAssignment({1: submission}))
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    command_grades_post(post_args(grades_csv))

    assert submission.edits == []


def test_grades_post_adds_missing_comment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,"Good work."'])
    submission = FakeSubmission(score=90.0)
    canvas = FakeCanvas(FakeAssignment({1: submission}))
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    command_grades_post(post_args(grades_csv))

    assert submission.edits == [{"comment": {"text_comment": "Good work."}}]


def test_grades_post_dry_run_does_not_touch_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    def fail(args: Any) -> Any:
        raise AssertionError("canvas_from_args should not be called in dry run")

    monkeypatch.setattr("danvas.grades.canvas_from_args", fail)

    command_grades_post(post_args(grades_csv, dry_run=True))

    assert "Dry run" in capsys.readouterr().out


def test_grades_post_reports_failures_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    class ExplodingAssignment:
        def get_submission(self, user_id: int, include: list[str] | None = None) -> Any:
            raise RuntimeError("boom")

    canvas = FakeCanvas(ExplodingAssignment())
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv))

    assert "FAILED RuntimeError" in capsys.readouterr().out


def test_grades_verify_exits_nonzero_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    canvas = FakeCanvas(FakeAssignment({1: FakeSubmission(score=70.0)}))
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    with pytest.raises(SystemExit):
        command_grades_verify(post_args(grades_csv))

    assert "MISMATCH" in capsys.readouterr().out
