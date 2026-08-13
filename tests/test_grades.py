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
    edit_submission_comment,
    grade_matches,
    load_grade_rows,
)
from danvas.mutation import MutationMode


class FakeSubmission:
    def __init__(
        self,
        score: float | None = None,
        grade: str | None = None,
        comments: list[dict[str, Any]] | None = None,
        posted_at: str | None = None,
        assignment_visible: bool = True,
    ) -> None:
        self.score = score
        self.grade = grade
        self.submission_comments = comments or []
        self.edits: list[dict[str, Any]] = []
        self.posted_at = posted_at
        self.assignment_visible = assignment_visible

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
    def __init__(self, submissions: dict[int, Any]) -> None:
        self.id = 5
        self.name = "Case Study 1"
        self.published = True
        self.unlock_at = None
        self.due_at = None
        self.lock_at = None
        self.post_manually = True
        self.submissions = submissions

    def get_submission(self, user_id: int, include: list[str] | None = None) -> Any:
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

    config_dir = grades_csv.parent / ".danvas"
    config_dir.mkdir(exist_ok=True)
    config = config_dir / "config.toml"
    if not config.exists():
        config.write_text(
            '[canvas]\ncourse_id = 101\napi_url = "https://canvas.example.edu/"\n',
            encoding="utf-8",
        )
    defaults = {
        "course_id": 101,
        "assignment_id": 5,
        "grades_csv": str(grades_csv),
        "dry_run": False,
        "offline_preview": False,
        "expected_assignment_title": None,
        "rollback_dir": None,
        "sleep_seconds": 0,
        "project_root": str(grades_csv.parent),
        "no_report": True,
        "report_root": None,
        "report_dir": None,
        "report_slug": None,
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


def test_load_grade_rows_ignores_only_fully_blank_rows(tmp_path: Path) -> None:
    path = tmp_path / "grades.csv"
    path.write_text(
        "CanvasID,Name,Grade,Comment\n,,,\n1,Doe,0,\n\n",
        encoding="utf-8",
    )

    rows = load_grade_rows(path)

    assert rows == [{"CanvasID": "1", "Name": "Doe", "Grade": "0", "Comment": ""}]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (",Doe,90,", "row 2 must include CanvasID"),
        ("abc,Doe,90,", "row 2 has invalid CanvasID"),
        ("1,Doe,,", "row 2 must include Grade"),
    ],
)
def test_load_grade_rows_rejects_nonblank_malformed_rows(
    tmp_path: Path, row: str, message: str
) -> None:
    path = tmp_path / "grades.csv"
    path.write_text(f"CanvasID,Name,Grade,Comment\n{row}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match=message):
        load_grade_rows(path)


def test_load_grade_rows_rejects_duplicate_canvas_ids(tmp_path: Path) -> None:
    path = tmp_path / "grades.csv"
    path.write_text(
        "CanvasID,Name,Grade,Comment\n1,Doe,90,\n001,Doe again,80,\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="duplicate CanvasID 1 on rows 2 and 3"):
        load_grade_rows(path)


def test_load_grade_rows_rejects_empty_data(tmp_path: Path) -> None:
    path = tmp_path / "grades.csv"
    path.write_text("CanvasID,Name,Grade,Comment\n,,,\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="contains no data rows"):
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
    assert "already_applied: 1, verified_applied: 1" in out
    assert "Doe, Jane" not in out


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


def test_grades_post_verifies_numeric_score_when_canvas_returns_scheme_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",85,'])

    class SchemeSubmission(FakeSubmission):
        def edit(self, **kwargs: Any) -> None:
            self.edits.append(kwargs)
            posted_grade = kwargs.get("submission", {}).get("posted_grade")
            if posted_grade is not None:
                self.score = float(posted_grade)
                self.grade = "B"

    submission = SchemeSubmission(score=75.0, grade="C")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_post(post_args(grades_csv))

    assert submission.score == 85.0
    assert submission.grade == "B"


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
    assert "Target rows: 1; changes: 1; blocked: 0" in out
    assert "Doe, Jane" not in out
    assert "90" not in out
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

    out = capsys.readouterr().out
    assert "mismatches: 1" in out
    assert "Doe, Jane" not in out


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
    assert "Preflight blocked for 1 private row condition" in out
    assert "14 point additional deduction" not in out
    assert "Doe, Jane" not in out
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

    assert "Preflight blocked for 1 private row condition" in capsys.readouterr().out


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

    rollback_dir = tmp_path / ".danvas/private/grades/assignment-5/rollback"
    rollback_json = [
        path
        for path in rollback_dir.glob("rollback-*.json")
        if not path.name.endswith(".artifact.json")
    ]
    rollback_csv = list(rollback_dir.glob("rollback-*.csv"))
    assert len(rollback_json) == 1
    assert len(rollback_csv) == 1
    assert '"OriginalGrade": "80"' in rollback_json[0].read_text(encoding="utf-8")
    assert rollback_csv[0].with_name(f"{rollback_csv[0].name}.artifact.json").is_file()
    assert submission.score == 90.0


def test_grades_post_requires_private_rollback_destination_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    grades_csv = input_dir / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    args = post_args(grades_csv, project_root=str(tmp_path / "not-a-project"))

    def fail(args: Any) -> Any:
        raise AssertionError("canvas_from_args must not run before private path resolution")

    monkeypatch.setattr("danvas.grades.canvas_from_args", fail)

    with pytest.raises(SystemExit, match="Pass --rollback-dir"):
        command_grades_post(args)


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
        'CanvasID,Name,ExpectedCurrentGrade,CommentID\n1,"Doe, Jane",80,7\n',
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

    assert "Preflight blocked for 1 private row condition" in capsys.readouterr().out


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
            project_root=None,
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["artifact_class"] == "private"
    assert [row["owned_by_current_user"] for row in payload["comments"]] == [True, False]


def test_grades_comments_default_is_private_and_stdout_is_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    post_args(grades_csv)
    submission = FakeSubmission(
        comments=[{"id": "7", "author_id": "99", "comment": "Private feedback."}]
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    from types import SimpleNamespace

    command_grades_comments(
        SimpleNamespace(
            course_id=101,
            assignment_id=5,
            canvas_id=1,
            output=None,
            overwrite=False,
            project_root=str(tmp_path),
        )
    )

    output = tmp_path / ".danvas/private/grades/assignment-5/user-1/comments.json"
    assert output.is_file()
    assert output.stat().st_mode & 0o077 == 0
    terminal = capsys.readouterr().out
    assert "Private feedback" not in terminal
    assert "user-1" not in terminal


def test_edit_submission_comment_uses_canvasapi_requester_parameter_shape() -> None:
    from types import SimpleNamespace

    calls: list[tuple[str, str, dict[str, Any]]] = []

    class Requester:
        def request(self, method: str, endpoint: str, **kwargs: Any) -> None:
            calls.append((method, endpoint, kwargs))

    submission = SimpleNamespace(
        course_id=101,
        assignment_id=5,
        user_id=1,
        _requester=Requester(),
    )

    edit_submission_comment(submission, 7, "Revised.", mutation_mode=MutationMode.APPLY)

    assert calls == [
        (
            "PUT",
            "courses/101/assignments/5/submissions/1/comments/7",
            {"_kwargs": [("comment", "Revised.")]},
        )
    ]


def test_grades_post_replace_exact_uses_production_requester_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "patch.csv"
    grades_csv.write_text(
        "CanvasID,Name,Grade,Comment,CommentAction,CommentID\n"
        '1,"Doe, Jane",80,"Revised.",replace_exact,7\n',
        encoding="utf-8",
    )

    class ProductionLikeSubmission:
        def __init__(self) -> None:
            self.score = 80.0
            self.grade = "80"
            self.posted_at = None
            self.assignment_visible = True
            self.submission_comments = [{"id": "7", "author_id": "99", "comment": "Original."}]
            self.course_id = 101
            self.assignment_id = 5
            self.user_id = 1
            self._requester = self

        def edit(self, **kwargs: Any) -> None:
            raise AssertionError("No submission edit is needed for this patch")

        def request(self, method: str, endpoint: str, **kwargs: Any) -> None:
            assert method == "PUT"
            assert endpoint.endswith("/comments/7")
            assert kwargs["_kwargs"] == [("comment", "Revised.")]
            self.submission_comments[0]["comment"] = "Revised."

    submission = ProductionLikeSubmission()
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    command_grades_post(post_args(grades_csv))

    assert submission.submission_comments[0]["comment"] == "Revised."


def test_grades_post_reports_partial_grade_only_and_halts_remaining_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    grades_csv = tmp_path / "patch.csv"
    grades_csv.write_text(
        "CanvasID,Name,Grade,Comment,CommentAction,CommentID\n"
        '1,"Doe, Jane",90,"Revised.",replace_exact,7\n'
        '2,"Smith, Pat",85,"Updated.",replace_exact,8\n',
        encoding="utf-8",
    )

    class CommentFailure(FakeSubmission):
        def edit_comment(self, comment_id: int, text: str) -> None:
            raise RuntimeError("comment endpoint failed token=secret")

    first = CommentFailure(
        score=80.0,
        grade="80",
        comments=[{"id": "7", "author_id": "99", "comment": "Original."}],
    )
    second = FakeSubmission(
        score=70.0,
        grade="70",
        comments=[{"id": "8", "author_id": "99", "comment": "Earlier."}],
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: first, 2: second})),
    )

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv))

    out = capsys.readouterr().out
    assert "not_attempted: 1, partially_applied: 1" in out
    assert "Doe, Jane" not in out
    assert "Smith, Pat" not in out
    assert "secret" not in out
    assert first.grade == "90"
    assert first.submission_comments[0]["comment"] == "Original."
    assert second.edits == []
    recovery_dir = tmp_path / ".danvas/private/grades/assignment-5/rollback"
    recovery_json = [
        path
        for path in recovery_dir.glob("recovery-*.json")
        if not path.name.endswith(".artifact.json")
    ]
    recovery_csv = list(recovery_dir.glob("recovery-*.forward.csv"))
    assert len(recovery_json) == 1
    assert len(recovery_csv) == 1
    recovery = json.loads(recovery_json[0].read_text(encoding="utf-8"))
    assert recovery["rows"][0]["outcome"] == "partially_applied"
    assert recovery["rows"][0]["forward_recovery_row"]["ExpectedCurrentGrade"] == "90"
    assert recovery_json[0].stat().st_mode & 0o077 == 0


def test_grades_post_unchanged_failure_continues_to_later_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,', '2,"Smith, Pat",85,'])

    class UnchangedFailure(FakeSubmission):
        def edit(self, **kwargs: Any) -> None:
            raise RuntimeError("request rejected")

    first = UnchangedFailure(score=80.0, grade="80")
    second = FakeSubmission(score=70.0, grade="70")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: first, 2: second})),
    )

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv))

    out = capsys.readouterr().out
    assert "unchanged_failure" in out
    assert second.grade == "85"
    assert "not_attempted" not in out


def test_grades_post_success_response_with_mismatch_halts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,', '2,"Smith, Pat",85,'])

    class IgnoredWrite(FakeSubmission):
        def edit(self, **kwargs: Any) -> None:
            self.edits.append(kwargs)

    first = IgnoredWrite(score=80.0, grade="80")
    second = FakeSubmission(score=70.0, grade="70")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: first, 2: second})),
    )

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv))

    out = capsys.readouterr().out
    assert "applied_unverified" in out
    assert "not_attempted" in out
    assert second.edits == []


def test_grades_clear_reports_partial_grade_only_with_guarded_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_csv = tmp_path / "clear.csv"
    clear_csv.write_text(
        'CanvasID,Name,ExpectedCurrentGrade,CommentID\n1,"Doe, Jane",80,7\n',
        encoding="utf-8",
    )

    class DeleteFailure(FakeSubmission):
        def delete_comment(self, comment_id: int) -> None:
            raise RuntimeError("delete rejected")

    submission = DeleteFailure(
        score=80.0,
        grade="80",
        comments=[{"id": "7", "author_id": "99", "comment": "Remove me."}],
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )

    with pytest.raises(SystemExit):
        command_grades_clear(post_args(clear_csv))

    assert "partially_applied" in capsys.readouterr().out
    recovery_dir = tmp_path / ".danvas/private/grades/assignment-5/rollback"
    recovery_csv = list(recovery_dir.glob("recovery-*.forward.csv"))
    assert len(recovery_csv) == 1
    assert "false" in recovery_csv[0].read_text(encoding="utf-8")


def test_grades_post_indeterminate_readback_halts_without_executable_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,', '2,"Smith, Pat",85,'])
    first = FakeSubmission(score=80.0, grade="80")
    second = FakeSubmission(score=70.0, grade="70")

    class ReadbackFailureAssignment(FakeAssignment):
        def __init__(self) -> None:
            super().__init__({1: first, 2: second})
            self.calls: dict[int, int] = {1: 0, 2: 0}

        def get_submission(self, user_id: int, include: list[str] | None = None) -> FakeSubmission:
            self.calls[user_id] += 1
            if user_id == 1 and self.calls[user_id] > 1:
                raise RuntimeError("readback unavailable")
            return self.submissions[user_id]

    assignment = ReadbackFailureAssignment()
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: FakeCanvas(assignment))

    with pytest.raises(SystemExit):
        command_grades_post(post_args(grades_csv))

    out = capsys.readouterr().out
    assert "indeterminate" in out
    assert "not_attempted" in out
    recovery_dir = tmp_path / ".danvas/private/grades/assignment-5/rollback"
    assert not list(recovery_dir.glob("recovery-*.forward.csv"))
    recovery_json = [
        path
        for path in recovery_dir.glob("recovery-*.json")
        if not path.name.endswith(".artifact.json")
    ]
    recovery = json.loads(recovery_json[0].read_text(encoding="utf-8"))
    assert recovery["rows"][0]["readback_error"] == "readback unavailable"


def test_grades_dry_run_writes_private_plan_receipt_without_comment_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,"Private feedback text"'])
    assignment = FakeAssignment({1: FakeSubmission(score=80.0, grade="80")})
    monkeypatch.setattr("danvas.grades.canvas_from_args", lambda args: FakeCanvas(assignment))
    report_dir = tmp_path / "grade-plan-report"

    command_grades_post(
        post_args(
            grades_csv,
            dry_run=True,
            no_report=False,
            report_dir=str(report_dir),
        )
    )

    report_text = (report_dir / "grades-plan.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "Private feedback text" not in report_text
    assert report["rows"][0]["comment_sha256"]
    assert manifest["may_contain_private_student_data"] is True
    assert report_dir.stat().st_mode & 0o077 == 0
    assert (report_dir / "grades-plan.json").stat().st_mode & 0o077 == 0


def test_grades_post_rollback_failure_finishes_failed_private_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "patch.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    submission = FakeSubmission(score=80.0, grade="80")
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )
    monkeypatch.setattr(
        "danvas.grades.write_grade_rollback",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("rollback disk failed")),
    )
    report_dir = tmp_path / "failed-report"

    with pytest.raises(SystemExit, match="Grade rollback capture failed"):
        command_grades_post(post_args(grades_csv, no_report=False, report_dir=str(report_dir)))

    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((report_dir / "grades-result.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["may_contain_private_student_data"] is True
    assert report["status"] == "failed"
    assert submission.edits == []


def test_grades_verify_receipt_records_verified_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])
    submission = FakeSubmission(
        score=90.0,
        grade="90",
        posted_at="2026-08-11T12:00:00Z",
        assignment_visible=True,
    )
    monkeypatch.setattr(
        "danvas.grades.canvas_from_args",
        lambda args: FakeCanvas(FakeAssignment({1: submission})),
    )
    report_dir = tmp_path / "grade-verify-report"

    command_grades_verify(post_args(grades_csv, no_report=False, report_dir=str(report_dir)))

    report = json.loads((report_dir / "grades-verify.json").read_text("utf-8"))
    assert report["release_state"]["conclusion"] == "verified_visible"
    assert report["summary"] == {"verified": 1}
    assert report["rows"][0]["intended_grade"] == "90"


def test_grade_report_options_refuse_no_report_with_report_dir(tmp_path: Path) -> None:
    grades_csv = tmp_path / "grades.csv"
    write_grades_csv(grades_csv, ['1,"Doe, Jane",90,'])

    with pytest.raises(SystemExit, match="either --no-report or report output options"):
        command_grades_post(
            post_args(
                grades_csv,
                dry_run=True,
                no_report=True,
                report_dir=str(tmp_path / "report"),
            )
        )
