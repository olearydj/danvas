from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.submissions import (
    command_submissions_feedback,
    load_roster_ids,
    match_files_to_students,
)


def write_roster(path: Path) -> None:
    path.write_text(
        "CanvasID,Name,Email,SIS_ID\n"
        '4024825,"Lawson, Jack",jack@example.edu,JL1\n'
        '5113936,"Reyes, Ana",ana@example.edu,AR1\n',
        encoding="utf-8",
    )


def feedback_args(roster: Path, feedback_dir: Path, **overrides: Any) -> Any:
    defaults = {
        "course_id": 101,
        "assignment_id": 5,
        "roster": str(roster),
        "feedback_dir": str(feedback_dir),
        "pattern": "*-feedback.pdf",
        "comment": "Here is your graded feedback.",
        "dry_run": False,
        "sleep_seconds": 0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_load_roster_ids_requires_canvas_id_column(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    path.write_text("Name\nDoe\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must include CanvasID"):
        load_roster_ids(path)


def test_match_files_to_students_matches_unique_embedded_ids(tmp_path: Path) -> None:
    canvas_ids = {4024825: "Lawson, Jack", 5113936: "Reyes, Ana"}
    matched_file = tmp_path / "4024825-feedback.pdf"
    repeated_id = tmp_path / "4024825-4024825-feedback.pdf"
    two_students = tmp_path / "4024825-5113936-feedback.pdf"
    unknown_id = tmp_path / "9999999-feedback.pdf"
    no_id = tmp_path / "feedback.pdf"
    files = [matched_file, repeated_id, two_students, unknown_id, no_id]

    matched, unmatched = match_files_to_students(files, canvas_ids)

    assert matched == [(4024825, matched_file), (4024825, repeated_id)]
    assert unmatched == [two_students, unknown_id, no_id]


def test_submissions_feedback_dry_run_previews_without_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    roster = tmp_path / "roster.csv"
    write_roster(roster)
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "4024825-feedback.pdf").write_bytes(b"x")
    (feedback_dir / "0000001-feedback.pdf").write_bytes(b"x")
    (feedback_dir / "notes.txt").write_bytes(b"x")

    def fail(args: Any) -> Any:
        raise AssertionError("canvas_from_args should not be called in dry run")

    monkeypatch.setattr("danvas.submissions.canvas_from_args", fail)

    command_submissions_feedback(feedback_args(roster, feedback_dir, dry_run=True))

    out = capsys.readouterr().out
    assert "Matched: 1" in out
    assert "Unmatched files (1):" in out
    assert "0000001-feedback.pdf" in out
    assert "notes.txt" not in out


def test_submissions_feedback_uploads_matched_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = tmp_path / "roster.csv"
    write_roster(roster)
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "4024825-feedback.pdf").write_bytes(b"x")

    uploads: list[tuple[int, str, str]] = []

    class FakeAssignment:
        def get_submission(self, canvas_id: int) -> Any:
            class FakeSubmission:
                def upload_comment(self, file: str, comment: str) -> None:
                    uploads.append((canvas_id, Path(file).name, comment))

            return FakeSubmission()

    class FakeCanvas:
        def get_course(self, course_id: int) -> FakeCanvas:
            return self

        def get_assignment(self, assignment_id: int) -> FakeAssignment:
            return FakeAssignment()

    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: FakeCanvas())

    command_submissions_feedback(feedback_args(roster, feedback_dir, comment="Graded."))

    assert uploads == [(4024825, "4024825-feedback.pdf", "Graded.")]
