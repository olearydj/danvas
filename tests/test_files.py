from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.files import (
    build_file_inventory,
    command_files_download,
    command_files_inventory,
    command_files_upload,
    content_type_for,
    download_relative_path,
    local_files,
    write_missing_report,
)


class FakeCourse:
    id = 101
    name = "Example Course"
    course_code = "EX-101"

    def get_folders(self) -> list[object]:
        return [
            SimpleNamespace(id=1, full_name="course files"),
            SimpleNamespace(id=2, full_name="course files/cases"),
        ]

    def get_files(self) -> list[object]:
        return [
            FakeFile(
                id=10,
                display_name="case.pdf",
                filename="case.pdf",
                folder_id=2,
                size=7,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
                content_type="application/pdf",
                url="https://canvas.example/files/10/download?verifier=secret",
            ),
            FakeFile(
                id=11,
                display_name="missing.pdf",
                filename="missing.pdf",
                folder_id=2,
                size=10,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
                content_type="application/pdf",
                url="https://canvas.example/files/11/download?verifier=secret",
            ),
        ]


class FakeFile(SimpleNamespace):
    def download(self, target: str) -> None:
        Path(target).write_bytes(b"x" * int(self.size))


class FakeCanvas:
    def get_course(self, course_id: int) -> FakeCourse:
        assert course_id == 101
        return FakeCourse()


class FakeUploadFolder(SimpleNamespace):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(uploads=[], **kwargs)

    def upload(self, source: str, *, on_duplicate: str, content_type: str):
        self.uploads.append(
            {
                "source": source,
                "on_duplicate": on_duplicate,
                "content_type": content_type,
            }
        )
        path = Path(source)
        return True, {
            "id": len(self.uploads) + 1000,
            "display_name": path.name,
            "filename": path.name.replace(" ", "+"),
            "folder_id": self.id,
            "size": path.stat().st_size,
            "content_type": content_type,
            "url": "https://canvas.example/files/download?verifier=secret",
        }


class FakeUploadCourse:
    id = 101
    name = "Example Course"

    def __init__(self) -> None:
        self.slides = FakeUploadFolder(id=20, full_name="course files/slides")
        self.cases = FakeUploadFolder(id=21, full_name="course files/cases")

    def get_folders(self) -> list[FakeUploadFolder]:
        return [self.slides, self.cases]


class FakeUploadCanvas:
    def __init__(self, course: FakeUploadCourse | None = None) -> None:
        self.course = course or FakeUploadCourse()
        self.folder_requested: int | None = None

    def get_course(self, course_id: int) -> FakeUploadCourse:
        assert course_id == 101
        return self.course

    def get_folder(self, folder_id: int) -> FakeUploadFolder:
        self.folder_requested = folder_id
        return self.course.slides


def test_build_file_inventory_compares_local_files_without_urls(tmp_path: Path) -> None:
    local_case = tmp_path / "content" / "cases" / "case.pdf"
    local_case.parent.mkdir(parents=True)
    local_case.write_text("content", encoding="utf-8")

    inventory = build_file_inventory(FakeCourse(), local_root=tmp_path)

    assert inventory["local_files_compared"] == 1
    assert [row["status"] for row in inventory["comparison"]] == [
        "present_by_name_and_size",
        "missing",
    ]
    assert inventory["comparison"][0]["local_matches"] == ["content/cases/case.pdf"]
    assert "url" not in inventory["canvas_files"][0]


def test_build_file_inventory_without_local_root_skips_comparison(tmp_path: Path) -> None:
    inventory = build_file_inventory(FakeCourse(), local_root=None)

    assert inventory["local_files_compared"] == 0
    assert [row["status"] for row in inventory["comparison"]] == ["not_compared", "not_compared"]

    output = tmp_path / "files-missing-report.md"
    write_missing_report(output, inventory)
    text = output.read_text(encoding="utf-8")
    assert "Local comparison skipped" in text
    assert "Missing locally by filename: `0`" in text


def test_local_files_excludes_generated_and_grading_files(tmp_path: Path) -> None:
    (tmp_path / "files-inventory.json").write_text("{}", encoding="utf-8")
    grading_file = tmp_path / "_archive" / "24-25.Su" / "grading" / "grades.csv"
    grading_file.parent.mkdir(parents=True)
    grading_file.write_text("private", encoding="utf-8")
    content_file = tmp_path / "content" / "note.md"
    content_file.parent.mkdir()
    content_file.write_text("public", encoding="utf-8")

    rows = local_files(tmp_path)

    assert [row["relative_path"] for row in rows] == ["content/note.md"]


def test_write_missing_report_summarizes_missing_files(tmp_path: Path) -> None:
    inventory = build_file_inventory(FakeCourse(), local_root=tmp_path)
    output = tmp_path / "files-missing-report.md"

    write_missing_report(output, inventory)

    text = output.read_text(encoding="utf-8")
    assert "Canvas files inventoried: `2`" in text
    assert "missing.pdf" in text
    assert "verifier" not in text


def test_command_files_inventory_writes_default_report_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        output_dir=None,
        local_root=None,
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_inventory(args)

    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    report_dir = report_dirs[0]
    assert report_dir.name.endswith("-files-inventory")
    assert (report_dir / "manifest.json").is_file()
    assert (report_dir / "files-inventory.json").is_file()
    assert (report_dir / "files-inventory.csv").is_file()
    assert (report_dir / "files-missing-report.md").is_file()


def test_command_files_inventory_preserves_explicit_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    output_dir = tmp_path / "legacy"
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        output_dir=str(output_dir),
        local_root=None,
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_inventory(args)

    assert (output_dir / "files-inventory.json").is_file()
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_download_relative_path_strips_course_files_prefix() -> None:
    record = {
        "folder_full_name": "course files/Case Studies",
        "display_name": "case: one?.pdf",
    }

    assert download_relative_path(record) == Path("Case Studies/case one.pdf")


def test_command_files_download_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(course_id=101, output_dir=str(tmp_path), overwrite=False)

    command_files_download(args)

    assert (tmp_path / "cases" / "case.pdf").is_file()
    assert (tmp_path / "cases" / "missing.pdf").is_file()
    manifest = (tmp_path / "files-download-manifest.json").read_text(encoding="utf-8")
    assert "case.pdf" in manifest
    assert "verifier" not in manifest


def test_command_files_download_deduplicates_colliding_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CollidingCourse(FakeCourse):
        def get_files(self) -> list[object]:
            return [
                FakeFile(id=10, display_name="case.pdf", filename="case.pdf", folder_id=2, size=7),
                FakeFile(id=11, display_name="case.pdf", filename="case.pdf", folder_id=2, size=9),
            ]

    class CollidingCanvas:
        def get_course(self, course_id: int) -> CollidingCourse:
            return CollidingCourse()

    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: CollidingCanvas())
    args = SimpleNamespace(course_id=101, output_dir=str(tmp_path), overwrite=False)

    command_files_download(args)

    assert (tmp_path / "cases" / "case-10.pdf").read_bytes() == b"x" * 7
    assert (tmp_path / "cases" / "case-11.pdf").read_bytes() == b"x" * 9
    manifest = json.loads(
        (tmp_path / "files-download-manifest.json").read_text(encoding="utf-8")
    )
    assert [row["deduplicated"] for row in manifest["files"]] == [True, True]
    assert [row["status"] for row in manifest["files"]] == ["downloaded", "downloaded"]


def test_content_type_for_uses_office_mappings() -> None:
    assert (
        content_type_for(Path("slides.pptx"))
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert content_type_for(Path("unknown.notreal")) == "application/octet-stream"


def test_command_files_upload_dry_run_resolves_folder_without_uploading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "Lecture 14.pptx"
    source.write_bytes(b"deck")
    canvas = FakeUploadCanvas()
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=True,
        output=str(output),
    )

    command_files_upload(args)

    assert canvas.course.slides.uploads == []
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert report["folder_full_name"] == "course files/slides"
    assert report["files"][0]["status"] == "dry-run"
    assert "verifier" not in output.read_text(encoding="utf-8")
    assert "Dry run - no files uploaded." in capsys.readouterr().out


def test_command_files_upload_missing_file_exits_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.files.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(tmp_path / "missing.pdf")],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=None,
    )

    with pytest.raises(SystemExit, match="Upload source not found"):
        command_files_upload(args)


def test_command_files_upload_rejects_folder_conflict_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")

    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.files.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=20,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    with pytest.raises(SystemExit, match="Use either --folder or --folder-id"):
        command_files_upload(args)


def test_command_files_upload_rejects_duplicate_basenames_without_rename(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "slides.pdf"
    second = tmp_path / "two" / "slides.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    args = SimpleNamespace(
        course_id=101,
        files=[str(first), str(second)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=None,
    )

    with pytest.raises(SystemExit, match="Duplicate local filenames"):
        command_files_upload(args)


def test_command_files_upload_folder_id_uses_canvas_get_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    canvas = FakeUploadCanvas()
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder=None,
        folder_id=20,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    command_files_upload(args)

    assert canvas.folder_requested == 20


def test_command_files_upload_folder_id_allows_matching_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    canvas = FakeUploadCanvas()
    canvas.course.slides.context_type = "Course"
    canvas.course.slides.context_id = 101
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder=None,
        folder_id=20,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    command_files_upload(args)

    assert canvas.folder_requested == 20


def test_command_files_upload_folder_id_rejects_mismatched_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    canvas = FakeUploadCanvas()
    canvas.course.slides.context_type = "Course"
    canvas.course.slides.context_id = 999
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder=None,
        folder_id=20,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    with pytest.raises(SystemExit, match="does not belong to course 101"):
        command_files_upload(args)


def test_command_files_upload_folder_id_rejects_absent_context_not_in_course(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    external_folder = FakeUploadFolder(id=99, full_name="course files/other")

    class ExternalFolderCanvas(FakeUploadCanvas):
        def get_folder(self, folder_id: int) -> FakeUploadFolder:
            assert folder_id == 99
            return external_folder

    canvas = ExternalFolderCanvas()
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder=None,
        folder_id=99,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    with pytest.raises(SystemExit, match="was not found in course 101"):
        command_files_upload(args)


def test_command_files_upload_rejects_missing_and_ambiguous_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    canvas = FakeUploadCanvas()
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/unknown",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
    )

    with pytest.raises(SystemExit, match="Canvas folder not found"):
        command_files_upload(args)

    class AmbiguousCourse(FakeUploadCourse):
        def get_folders(self) -> list[FakeUploadFolder]:
            return [
                FakeUploadFolder(id=20, full_name="course files/slides"),
                FakeUploadFolder(id=21, full_name="course files/slides"),
            ]

    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(AmbiguousCourse())
    )
    args.folder = "course files/slides"

    with pytest.raises(SystemExit, match="ambiguous"):
        command_files_upload(args)


def test_command_files_upload_live_uploads_and_writes_safe_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "Lecture 14 - Sheets.xlsx"
    source.write_bytes(b"sheet")
    canvas = FakeUploadCanvas()
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="rename",
        dry_run=False,
        output=str(output),
    )

    command_files_upload(args)

    assert canvas.course.slides.uploads == [
        {
            "source": str(source),
            "on_duplicate": "rename",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    ]
    report_text = output.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["files"][0]["status"] == "uploaded"
    assert report["files"][0]["url_present"] is True
    assert "verifier" not in report_text
    captured = capsys.readouterr().out
    assert "== Canvas write: upload 1 file(s) ==" in captured
    assert '"status": "uploaded"' in captured


def test_command_files_upload_partial_failure_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            self.uploads.append(
                {
                    "source": source,
                    "on_duplicate": on_duplicate,
                    "content_type": content_type,
                }
            )
            if Path(source).name == "bad.pdf":
                return False, {"message": "upload rejected"}
            return super().upload(
                source, on_duplicate=on_duplicate, content_type=content_type
            )

    class FailingCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = FailingFolder(id=20, full_name="course files/slides")

    good = tmp_path / "good.pdf"
    bad = tmp_path / "bad.pdf"
    good.write_text("good", encoding="utf-8")
    bad.write_text("bad", encoding="utf-8")
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(FailingCourse())
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(good), str(bad)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=None,
    )

    with pytest.raises(SystemExit) as exc:
        command_files_upload(args)

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert '"status": "uploaded"' in output
    assert '"status": "failed"' in output
    assert "Upload incomplete: 1 uploaded, 1 failed." in output


def test_command_files_upload_failure_payload_does_not_leak_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UrlOnlyFailureFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            return False, {
                "download_url": "https://canvas.example/files/download?verifier=secret",
                "verifier": "secret",
            }

    class UrlOnlyFailureCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = UrlOnlyFailureFolder(id=20, full_name="course files/slides")

    source = tmp_path / "bad.pdf"
    source.write_text("bad", encoding="utf-8")
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args",
        lambda args: FakeUploadCanvas(UrlOnlyFailureCourse()),
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=str(output),
    )

    with pytest.raises(SystemExit):
        command_files_upload(args)

    report_text = output.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["files"][0]["error"] == "Upload failed without a Canvas error message."
    assert "download_url" not in report_text
    assert "verifier" not in report_text
    assert "secret" not in report_text


def test_command_files_upload_empty_failure_payload_gets_generic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyFailureFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            return False, {}

    class EmptyFailureCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = EmptyFailureFolder(id=20, full_name="course files/slides")

    source = tmp_path / "bad.pdf"
    source.write_text("bad", encoding="utf-8")
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args",
        lambda args: FakeUploadCanvas(EmptyFailureCourse()),
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=str(output),
    )

    with pytest.raises(SystemExit):
        command_files_upload(args)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["files"][0]["status"] == "failed"
    assert report["files"][0]["error"] == "Upload failed without a Canvas error message."


def test_command_files_upload_exception_text_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ExceptionFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            raise RuntimeError(
                "POST https://canvas.example/upload?verifier=secret-token failed"
            )

    class ExceptionCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = ExceptionFolder(id=20, full_name="course files/slides")

    source = tmp_path / "bad.pdf"
    source.write_text("bad", encoding="utf-8")
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(ExceptionCourse())
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        output=str(output),
    )

    with pytest.raises(SystemExit):
        command_files_upload(args)

    report_text = output.read_text(encoding="utf-8")
    assert "RuntimeError: POST [redacted-url] failed" in report_text
    assert "canvas.example" not in report_text
    assert "secret-token" not in report_text
