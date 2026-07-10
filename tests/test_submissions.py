from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from danvas.submissions import (
    command_submissions_export,
    command_submissions_feedback,
    command_submissions_grades,
    command_submissions_media,
    file_integrity,
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


def test_submissions_feedback_live_run_prints_mutation_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    roster = tmp_path / "roster.csv"
    write_roster(roster)
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "4024825-feedback.pdf").write_bytes(b"x")

    class FakeCanvas:
        def get_course(self, course_id: int) -> FakeCanvas:
            return self

        def get_assignment(self, assignment_id: int) -> Any:
            class FakeAssignment:
                def get_submission(self, canvas_id: int) -> Any:
                    class FakeSubmission:
                        def upload_comment(self, file: str, comment: str) -> None:
                            pass

                    return FakeSubmission()

            return FakeAssignment()

    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: FakeCanvas())

    command_submissions_feedback(feedback_args(roster, feedback_dir))

    out = capsys.readouterr().out
    assert "== Canvas write: upload feedback comments ==" in out
    assert "files: 1" in out


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


class FakeAttachment:
    id = 700
    filename = "workbook.xlsx"
    display_name = "workbook.xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    size = 42
    url = "https://canvas.test/download?verifier=secret"


class FakeSubmission:
    def __init__(self, *, grade: str | None = "90") -> None:
        self.id = 800
        self.user_id = 4024825
        self.user = {"sortable_name": "Lawson, Jack"}
        self.attempt = 1
        self.workflow_state = "graded"
        self.submitted_at = "2026-07-01T12:00:00Z"
        self.graded_at = "2026-07-02T12:00:00Z"
        self.score = 90.0 if grade else None
        self.grade = grade
        self.grader_id = 99
        self.late = False
        self.missing = False
        self.excused = False
        self.attachments = [FakeAttachment()]
        self.submission_comments = [
            {
                "id": 44,
                "author_id": 99,
                "author_name": "Instructor",
                "comment": "Good work.",
                "created_at": "2026-07-02T12:00:00Z",
            }
        ]
        self.submission_history = [{"attempt": 1}]
        self.media_comment = None


class FakeSubmissionAssignment:
    id = 5
    name = "Case Study 1"

    def __init__(self, submissions: list[FakeSubmission]) -> None:
        self.submissions = submissions

    def get_submissions(self, include: list[str]) -> list[FakeSubmission]:
        return self.submissions


class FakeSubmissionCanvas:
    def __init__(self, assignment: FakeSubmissionAssignment) -> None:
        self.assignment = assignment

    def get_course(self, course_id: int) -> FakeSubmissionCanvas:
        return self

    def get_assignment(self, assignment_id: int) -> FakeSubmissionAssignment:
        return self.assignment


def submission_args(tmp_path: Path, **overrides: Any) -> Any:
    defaults = {
        "course_id": 101,
        "assignment_id": 5,
        "output": str(tmp_path / "submissions.json"),
        "include_comments": False,
        "include_history": False,
        "save_raw": None,
        "only_graded": False,
        "overwrite": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_submissions_export_writes_sanitized_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = FakeSubmissionCanvas(FakeSubmissionAssignment([FakeSubmission()]))
    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: canvas)

    command_submissions_export(
        submission_args(tmp_path, include_comments=True, include_history=True)
    )

    payload = json.loads((tmp_path / "submissions.json").read_text(encoding="utf-8"))
    row = payload["submissions"][0]
    assert row["canvas_user_id"] == 4024825
    assert row["attachment_ids"] == [700]
    assert row["attachment_content_types"] == [FakeAttachment.content_type]
    assert row["attachment_sizes"] == [42]
    assert row["comments"][0]["comment"] == "Good work."
    assert "verifier" not in json.dumps(payload)
    assert "download" not in json.dumps(payload)


def test_submissions_grades_only_graded_flattens_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas = FakeSubmissionCanvas(
        FakeSubmissionAssignment([FakeSubmission(), FakeSubmission(grade=None)])
    )
    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: canvas)
    output = tmp_path / "grades.csv"

    command_submissions_grades(
        submission_args(tmp_path, output=str(output), only_graded=True)
    )

    text = output.read_text(encoding="utf-8")
    assert "Good work." in text
    assert "comment_author_id" in text
    assert text.count("Lawson, Jack") == 1


def test_submissions_media_flat_writes_hash_integrity_and_safe_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    body = buffer.getvalue()

    class Response:
        headers = {"Content-Type": FakeAttachment.content_type}

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return [body]

    monkeypatch.setattr("danvas.submissions.requests.get", lambda *args, **kwargs: Response())
    canvas = FakeSubmissionCanvas(FakeSubmissionAssignment([FakeSubmission()]))
    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: canvas)
    output = tmp_path / "downloads"

    command_submissions_media(
        SimpleNamespace(
            course_id=101,
            assignment_id=5,
            output_dir=str(output),
            layout="flat",
            overwrite=False,
        )
    )

    downloaded = output / "Lawson,_Jack_sub800_workbook.xlsx"
    assert downloaded.is_file()
    sidecar = json.loads(
        downloaded.with_suffix(".xlsx.info.json").read_text(encoding="utf-8")
    )
    assert sidecar["integrity_status"] == "valid"
    assert sidecar["downloaded_at"].endswith("+00:00")
    assert len(sidecar["sha256"]) == 64
    assert "url" not in json.dumps(sidecar).lower()
    manifest = json.loads(
        (output / "submissions-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["files"][0]["stable_canvas_id"] == 700
    assert "verifier" not in json.dumps(manifest)


def test_office_integrity_rejects_plain_zip_missing_ooxml_parts(tmp_path: Path) -> None:
    path = tmp_path / "fake.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("notes.txt", "not a workbook")
    status, error = file_integrity(path)
    assert status == "invalid"
    assert "OOXML" in error


def test_media_http_failure_is_sanitized_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise requests.ConnectionError(
            "failed https://canvas.test/download?verifier=secret-token"
        )

    monkeypatch.setattr("danvas.submissions.requests.get", fail)
    canvas = FakeSubmissionCanvas(FakeSubmissionAssignment([FakeSubmission()]))
    monkeypatch.setattr("danvas.submissions.canvas_from_args", lambda args: canvas)
    output = tmp_path / "downloads"
    command_submissions_media(
        SimpleNamespace(
            course_id=101,
            assignment_id=5,
            output_dir=str(output),
            layout="flat",
            overwrite=False,
        )
    )
    manifest = json.loads(
        (output / "submissions-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["files"][0]["download_status"] == "failed"
    assert "secret-token" not in json.dumps(manifest)
    assert not list(output.glob("*.part"))
