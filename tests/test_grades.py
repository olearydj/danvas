from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from danvas.grades import (
    command_grades_clear,
    command_grades_comments,
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
        comments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.score = score
        self.grade = grade
        self.submission_comments = comments or []
        self.edits: list[dict[str, Any]] = []

    def edit(self, **kwargs: Any) -> None:
        self.edits.append(kwargs)
        posted_grade = kwargs.get("submission", {}).get("posted_grade")
        if posted_grade is not None:
            self.grade = posted_grade
            self.score = float(posted_grade) if posted_grade else None
        text = kwargs.get("comment", {}).get("text_comment")
        if text:
            self.submission_comments.append(
                {"id": 100 + len(self.submission_comments), "author_id": 99, "comment": text}
            )

    def delete_comment(self, comment_id: int) -> None:
        self.submission_comments = [
            comment for comment in self.submission_comments if int(comment["id"]) != comment_id
        ]

    def edit_comment(self, comment_id: int, text: str) -> None:
        for comment in self.submission_comments:
            if int(comment["id"]) == comment_id:
                comment["comment"] = text


class FakeAssignment:
    def __init__(self, submissions: dict[int, FakeSubmission]) -> None:
        self.id = 5
        self.name = "Case Study 1"
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

    def get_current_user(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(id=99)


def write_grades_csv(path: Path, rows: list[str]) -> None:
    path.write_text("CanvasID,Name,Grade,Comment\n" + "\n".join(rows) + "\n", encoding="utf-8")


def post_args(grades_csv: Path, **overrides: Any) -> Any:
    from types import SimpleNamespace

    defaults = {
        "course_id": 101,
        "assignment_id": 5,
        "grades_csv": str(grades_csv),
        "dry_run": False,
        "offline_preview": False,
        "expected_assignment_title": None,
        "rollback_dir": None,
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
    assert "== Canvas write: post grades ==" in out
    assert "rows: 2" in out
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


def test_grades_post_dry_run_reads_canvas_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    submission = FakeSubmission(score=80.0)
    canvas = FakeCanvas(FakeAssignment({1: submission}))
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    command_grades_post(post_args(grades_csv, dry_run=True))

    out = capsys.readouterr().out
    assert "Grade preflight - no Canvas writes" in out
    assert "Case Study 1" in out
    assert "delta +10" in out
    assert submission.edits == []


def test_grades_post_offline_preview_does_not_touch_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    def fail(args: Any) -> Any:
        raise AssertionError("canvas_from_args should not be called")

    monkeypatch.setattr("danvas.grades.canvas_from_args", fail)
    command_grades_post(post_args(grades_csv, offline_preview=True))
    assert "Offline preview" in capsys.readouterr().out


def test_grades_post_reports_failures_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    class ExplodingAssignment:
        def get_submission(self, user_id: int, include: list[str] | None = None) -> Any:
            raise RuntimeError("boom")

    canvas = FakeCanvas(ExplodingAssignment())
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: canvas)

    with pytest.raises(SystemExit, match="Grade preflight failed: boom"):
        command_grades_post(post_args(grades_csv))


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


def test_grades_post_blocks_expected_grade_and_comment_delta_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "patch.csv"
    grades_csv.write_text(
        "CanvasID,Name,Grade,Comment,ExpectedCurrentGrade\n"
        '1,"Doe, Jane",71,"14 point additional deduction",80\n',
        encoding="utf-8",
    )
    submission = FakeSubmission(score=80.0, grade="80")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv, dry_run=True))

    out = capsys.readouterr().out
    assert "Comment states 14 point additional deduction; grade delta is 9" in out
    assert submission.edits == []


def test_grades_post_blocks_wrong_expected_assignment_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: FakeSubmission(score=80.0)})),
    )

    with pytest.raises(SystemExit):
        command_grades_post(
            post_args(grades_csv, dry_run=True, expected_assignment_title="Other Assignment")
        )

    assert "Expected assignment title" in capsys.readouterr().out


def test_grades_post_writes_rollback_before_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    submission = FakeSubmission(score=80.0, grade="80")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_post(post_args(grades_csv))

    rollback_json = list(tmp_path.glob("patch.rollback-*.json"))
    rollback_csv = list(tmp_path.glob("patch.rollback-*.csv"))
    assert len(rollback_json) == 1
    assert len(rollback_csv) == 1
    assert '"OriginalGrade": "80"' in rollback_json[0].read_text(encoding="utf-8")
    assert submission.score == 90.0


def test_grades_post_replaces_exact_owned_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "patch.csv"
    grades_csv.write_text(
        "CanvasID,Name,Grade,Comment,CommentAction,CommentID\n"
        '1,"Doe, Jane",80,"Revised.",replace_exact,7\n',
        encoding="utf-8",
    )
    submission = FakeSubmission(
        score=80.0,
        comments=[{"id": "7", "author_id": "99", "comment": "Original."}],
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_post(post_args(grades_csv))

    assert submission.submission_comments[0]["comment"] == "Revised."


def test_grades_clear_clears_grade_and_exact_owned_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_csv = tmp_path / "clear.csv"
    clear_csv.write_text(
        "CanvasID,Name,ExpectedCurrentGrade,CommentID\n"
        '1,"Doe, Jane",80,7\n',
        encoding="utf-8",
    )
    submission = FakeSubmission(
        score=80.0,
        grade="80",
        comments=[{"id": "7", "author_id": "99", "comment": "Remove me."}],
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_clear(post_args(clear_csv))

    assert submission.score is None
    assert submission.grade == ""
    assert submission.submission_comments == []


def test_grades_clear_refuses_comment_owned_by_other_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_csv = tmp_path / "clear.csv"
    clear_csv.write_text("CanvasID,CommentID\n1,7\n", encoding="utf-8")
    submission = FakeSubmission(
        score=80.0,
        comments=[{"id": "7", "author_id": "88", "comment": "Keep me."}],
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    with pytest.raises(SystemExit):
        command_grades_clear(post_args(clear_csv, dry_run=True))

    assert "not owned by the authenticated user" in capsys.readouterr().out


def test_grades_comments_marks_current_user_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    output = tmp_path / "comments.json"
    submission = FakeSubmission(
        comments=[
            {"id": "7", "author_id": "99", "comment": "Mine."},
            {"id": "8", "author_id": "88", "comment": "Theirs."},
        ]
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_comments(
        SimpleNamespace(
            course_id=101,
            assignment_id=5,
            canvas_id=1,
            output=str(output),
            overwrite=False,
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [row["owned_by_current_user"] for row in payload["comments"]] == [True, False]
