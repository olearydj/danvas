from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.files import (
    build_file_inventory,
    command_files_compare,
    command_files_download,
    command_files_download_one,
    command_files_inventory,
    command_files_upload,
    content_type_for,
    download_relative_path,
    local_files,
    plan_upload_rows,
    scrub_sensitive_upload_payload,
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


def test_upload_payload_scrubber_drops_embedded_sensitive_key_names() -> None:
    payload = {
        "oauth_token_hint": "secret-token",
        "callback_url_metadata": "https://canvas.example/upload",
        "challenge_verifier_copy": "secret-verifier",
        "message": "safe",
    }

    assert scrub_sensitive_upload_payload(payload) == {"message": "safe"}


class FakeUploadFolder(SimpleNamespace):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(uploads=[], files=[], **kwargs)

    def get_files(self) -> list[object]:
        return list(self.files)

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


def test_internal_upload_plan_error_policy_never_overwrites() -> None:
    folder = FakeUploadFolder(id=20, full_name="course files/assets")
    folder.files = [SimpleNamespace(id=44, display_name="case.pdf", filename="case.pdf")]

    rows = plan_upload_rows(
        [
            {
                "source": "/private/source/case.pdf",
                "relative_path": "assets/case.pdf",
                "name": "case.pdf",
                "size": 10,
                "content_type": "application/pdf",
            }
        ],
        folder,
        on_duplicate="error",
    )

    assert rows[0]["status"] == "conflict"
    assert rows[0]["existing_canvas_ids"] == [44]


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
    assert inventory["comparison"][0]["local_match_details"][0]["size"] == 7
    assert inventory["comparison"][0]["local_match_details"][0]["mtime"]
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
    archived_file = tmp_path / "_archive" / "old" / "case.pdf"
    archived_file.parent.mkdir(parents=True)
    archived_file.write_text("archived", encoding="utf-8")
    report_file = tmp_path / ".danvas" / "reports" / "run" / "case.pdf"
    report_file.parent.mkdir(parents=True)
    report_file.write_text("generated", encoding="utf-8")
    content_file = tmp_path / "content" / "note.md"
    content_file.parent.mkdir()
    content_file.write_text("public", encoding="utf-8")

    rows = local_files(tmp_path)

    assert [row["relative_path"] for row in rows] == ["content/note.md"]


def test_command_files_inventory_uses_configured_local_ignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\n\n[files.inventory]\nignore = ["scratch/**"]\n',
        encoding="utf-8",
    )
    local_case = tmp_path / "content" / "cases" / "case.pdf"
    local_case.parent.mkdir(parents=True)
    local_case.write_text("content", encoding="utf-8")
    scratch_missing = tmp_path / "scratch" / "missing.pdf"
    scratch_missing.parent.mkdir()
    scratch_missing.write_text("x" * 10, encoding="utf-8")
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    output_dir = tmp_path / "inventory"
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        output_dir=str(output_dir),
        local_root=str(tmp_path),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_inventory(args)

    inventory = json.loads((output_dir / "files-inventory.json").read_text(encoding="utf-8"))
    statuses = {row["display_name"]: row["status"] for row in inventory["comparison"]}
    assert statuses["case.pdf"] == "present_by_name_and_size"
    assert statuses["missing.pdf"] == "missing"
    assert "scratch/**" in inventory["local_ignore_patterns"]
    assert inventory["local_files_compared"] == 1


def test_command_files_inventory_rejects_unsafe_ignore_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\n\n[files.inventory]\nignore = ["../outside/**"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        output_dir=str(tmp_path / "inventory"),
        local_root=str(tmp_path),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    with pytest.raises(SystemExit, match="files.inventory.ignore patterns"):
        command_files_inventory(args)


def test_write_missing_report_summarizes_missing_files(tmp_path: Path) -> None:
    inventory = build_file_inventory(FakeCourse(), local_root=tmp_path)
    output = tmp_path / "files-missing-report.md"

    write_missing_report(output, inventory)

    text = output.read_text(encoding="utf-8")
    assert "Canvas files inventoried: `2`" in text
    assert "missing.pdf" in text
    assert "Canvas size" in text
    assert "Local size(s)" in text
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


def test_download_relative_path_neutralizes_dot_components() -> None:
    record = {
        "folder_full_name": "course files/../../outside",
        "display_name": "..",
    }

    assert download_relative_path(record) == Path("untitled/untitled/outside/untitled")


def test_command_files_download_cannot_escape_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    output_dir = tmp_path / "downloads"

    class TraversalCourse(FakeCourse):
        def get_folders(self) -> list[object]:
            return [SimpleNamespace(id=9, full_name="course files/../..")]

        def get_files(self) -> list[object]:
            return [
                FakeFile(
                    id=99,
                    display_name="sentinel.txt",
                    filename="sentinel.txt",
                    folder_id=9,
                    size=7,
                )
            ]

    class TraversalCanvas:
        def get_course(self, course_id: int) -> TraversalCourse:
            return TraversalCourse()

    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: TraversalCanvas())

    command_files_download(
        SimpleNamespace(course_id=101, output_dir=str(output_dir), overwrite=True)
    )

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert (output_dir / "untitled" / "untitled" / "sentinel.txt").is_file()


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


def test_command_files_download_one_writes_exact_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "downloads" / "case.pdf"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        output=str(output),
        file_id=10,
        canvas_path=None,
        overwrite=False,
    )

    command_files_download_one(args)

    assert output.read_bytes() == b"x" * 7
    captured = capsys.readouterr().out
    report = json.loads(captured)
    assert report["status"] == "downloaded"
    assert report["output"] == str(output)
    assert report["canvas"]["id"] == 10
    assert report["canvas"]["canvas_path"] == "course files/cases/case.pdf"
    assert report["local"]["size"] == 7
    assert "verifier" not in captured


def test_command_files_download_one_by_canvas_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "case.pdf"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        output=str(output),
        file_id=None,
        canvas_path="course files/cases/case.pdf",
        overwrite=False,
    )

    command_files_download_one(args)

    assert output.read_bytes() == b"x" * 7


def test_command_files_download_one_refuses_overwrite_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "case.pdf"
    output.write_text("existing", encoding="utf-8")

    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.files.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        output=str(output),
        file_id=10,
        canvas_path=None,
        overwrite=False,
    )

    with pytest.raises(SystemExit, match="Pass --overwrite"):
        command_files_download_one(args)


def test_command_files_download_one_requires_output_and_target_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.files.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        output=None,
        file_id=10,
        canvas_path=None,
        overwrite=False,
    )

    with pytest.raises(SystemExit, match="Output file required"):
        command_files_download_one(args)

    args.output = str(tmp_path / "case.pdf")
    args.file_id = None
    with pytest.raises(SystemExit, match="Canvas file target required"):
        command_files_download_one(args)


def test_command_files_compare_writes_report_dir_by_file_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"x" * 7)
    downloaded = tmp_path / "canvas-case.pdf"
    downloaded.write_bytes(b"x" * 7)
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        local=str(source),
        downloaded_canvas=str(downloaded),
        file_id=10,
        canvas_path=None,
        output=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    command_files_compare(args)

    report = json.loads((tmp_path / "report" / "files-compare.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text(encoding="utf-8"))
    md = (tmp_path / "report" / "files-compare.md").read_text(encoding="utf-8")
    assert report["status"] == "matches"
    assert report["canvas"]["id"] == 10
    assert report["canvas"]["canvas_path"] == "course files/cases/case.pdf"
    assert report["comparisons"]["size"]["matches"] is True
    assert report["comparisons"]["checksum"]["algorithm"] == "sha256"
    assert report["comparisons"]["checksum"]["matches"] is True
    assert report["downloaded_canvas"]["path"] == str(downloaded)
    assert manifest["command"] == "files compare"
    assert manifest["report_slug"] == "files-compare"
    assert manifest["files"] == ["files-compare.json", "files-compare.md"]
    assert manifest["inputs"] == [{"scope": "external"}, {"scope": "external"}]
    assert "input_paths" not in manifest
    assert "Checksum comparison uses the supplied downloaded Canvas file" in md
    assert "File compare: matches" in capsys.readouterr().out


def test_command_files_compare_by_canvas_path_writes_legacy_output_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "renamed.pdf"
    source.write_bytes(b"short")
    output = tmp_path / "compare.json"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        local=str(source),
        downloaded_canvas=None,
        file_id=None,
        canvas_path="course files/cases/case.pdf",
        output=str(output),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_compare(args)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "mismatch"
    assert report["comparisons"]["name"]["matches"] is False
    assert report["comparisons"]["size"]["matches"] is False
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_command_files_compare_defaults_to_project_report_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"x" * 7)
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=str(tmp_path),
        local=str(source),
        downloaded_canvas=None,
        file_id=10,
        canvas_path=None,
        output=None,
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_compare(args)

    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    assert report_dirs[0].name.endswith("-files-compare")
    assert (report_dirs[0] / "files-compare.json").is_file()
    assert (report_dirs[0] / "files-compare.md").is_file()


def test_command_files_compare_rejects_invalid_targets_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"x" * 7)

    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.files.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        local=str(source),
        downloaded_canvas=None,
        file_id=10,
        canvas_path="course files/cases/case.pdf",
        output=None,
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    with pytest.raises(SystemExit, match="Use either --file-id or --canvas-path"):
        command_files_compare(args)

    args.file_id = None
    args.canvas_path = None
    with pytest.raises(SystemExit, match="Canvas file target required"):
        command_files_compare(args)

    args.file_id = 10
    args.local = str(tmp_path / "missing.pdf")
    with pytest.raises(SystemExit, match="Local file not found"):
        command_files_compare(args)


def test_command_files_compare_checksum_mismatch_changes_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"local")
    downloaded = tmp_path / "canvas-case.pdf"
    downloaded.write_bytes(b"canvas")
    output = tmp_path / "compare.json"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        local=str(source),
        downloaded_canvas=str(downloaded),
        file_id=10,
        canvas_path=None,
        output=str(output),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_compare(args)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "mismatch"
    assert report["comparisons"]["checksum"]["matches"] is False
    assert report["comparisons"]["checksum"]["canvas"] != report["comparisons"]["checksum"]["local"]


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
    assert report["files"][0]["status"] == "would_create"
    assert "verifier" not in output.read_text(encoding="utf-8")
    assert "Dry run - no files uploaded." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("policy", "expected_status"),
    [("overwrite", "would_overwrite"), ("rename", "would_rename")],
)
def test_command_files_upload_dry_run_classifies_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    expected_status: str,
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"case")
    course = FakeUploadCourse()
    course.slides.files = [SimpleNamespace(id=77, display_name="case.pdf")]
    output = tmp_path / f"{policy}.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(course)
    )

    command_files_upload(
        SimpleNamespace(
            course_id=101,
            files=[str(source)],
            folder="course files/slides",
            folder_id=None,
            on_duplicate=policy,
            dry_run=True,
            output=str(output),
        )
    )

    row = json.loads(output.read_text(encoding="utf-8"))["files"][0]
    assert row["status"] == expected_status
    assert row["existing_canvas_ids"] == [77]


def test_command_files_upload_dry_run_listing_failure_is_sanitized_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "case.pdf"
    source.write_bytes(b"case")

    class FailingListingFolder(FakeUploadFolder):
        def get_files(self) -> list[object]:
            raise RuntimeError(
                "GET https://canvas.example/files?verifier=secret-value failed"
            )

    class FailingListingCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = FailingListingFolder(id=20, full_name="course files/slides")

    output = tmp_path / "plan.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args",
        lambda args: FakeUploadCanvas(FailingListingCourse()),
    )

    with pytest.raises(SystemExit):
        command_files_upload(
            SimpleNamespace(
                course_id=101,
                files=[str(source)],
                folder="course files/slides",
                folder_id=None,
                on_duplicate="overwrite",
                dry_run=True,
                output=str(output),
                project_root=None,
                no_report=False,
                report_root=None,
                report_dir=str(tmp_path / "report"),
                report_slug=None,
            )
        )

    text = output.read_text(encoding="utf-8")
    assert json.loads(text)["files"][0]["status"] == "conflict"
    assert "secret-value" not in text
    assert "canvas.example" not in text
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text("utf-8"))
    assert manifest["status"] == "failed"


def test_command_files_upload_dry_run_writes_report_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "Lecture 14.pptx"
    source.write_bytes(b"deck")
    canvas = FakeUploadCanvas()
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
        project_root=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    command_files_upload(args)

    report = json.loads((tmp_path / "report" / "files-upload.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert report["files"][0]["status"] == "would_create"
    assert manifest["command"] == "files upload"
    assert manifest["status"] == "success"
    assert manifest["may_contain_private_student_data"] is False


def test_command_files_upload_defaults_to_project_report_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "Lecture 14.pptx"
    source.write_bytes(b"deck")
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )
    canvas = FakeUploadCanvas()
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=True,
        output=None,
        project_root=str(tmp_path),
        no_report=False,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_files_upload(args)

    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    assert report_dirs[0].name.endswith("-files-upload")
    assert (report_dirs[0] / "files-upload.json").is_file()
    assert (report_dirs[0] / "manifest.json").is_file()


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
        api_url="https://canvas.example/",
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
    assert report["files"][0]["canvas_url"] == (
        "https://canvas.example/courses/101/files/1001?wrap=1"
    )
    assert report["files"][0]["canvas_path"] == (
        "course files/slides/Lecture 14 - Sheets.xlsx"
    )
    assert "verifier" not in report_text
    captured = capsys.readouterr().out
    assert "== Canvas write: upload 1 file(s) ==" in captured
    assert '"status": "uploaded"' in captured


def test_command_files_upload_error_policy_rechecks_and_uses_rename_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_bytes(b"slides")
    canvas = FakeUploadCanvas()
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr("danvas.files.canvas_from_args", lambda args: canvas)

    command_files_upload(
        SimpleNamespace(
            course_id=101,
            files=[str(source)],
            folder="course files/slides",
            folder_id=None,
            on_duplicate="error",
            dry_run=False,
            mutation_mode="apply",
            api_url="https://canvas.example/",
            output=str(output),
        )
    )

    assert canvas.course.slides.uploads[0]["on_duplicate"] == "rename"
    row = json.loads(output.read_text(encoding="utf-8"))["files"][0]
    assert row["requested_duplicate_policy"] == "error"
    assert row["transport_duplicate_policy"] == "rename"
    assert row["planned_outcome"] == "would_create"
    assert row["observed_outcome"] == "created"


def test_command_files_upload_error_policy_blocks_known_conflict_without_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_bytes(b"slides")
    course = FakeUploadCourse()
    course.slides.files = [SimpleNamespace(id=77, display_name="slides.pdf")]
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(course)
    )

    with pytest.raises(SystemExit):
        command_files_upload(
            SimpleNamespace(
                course_id=101,
                files=[str(source)],
                folder="course files/slides",
                folder_id=None,
                on_duplicate="error",
                dry_run=False,
                mutation_mode="apply",
                api_url="https://canvas.example/",
                output=str(output),
            )
        )

    assert course.slides.uploads == []
    assert "== Canvas write:" not in capsys.readouterr().out
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["plan"]["status"] == "blocked"
    assert report["files"][0]["status"] == "conflict"


def test_command_files_upload_error_policy_blocks_prewrite_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PrewriteRaceFolder(FakeUploadFolder):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.listings = 0

        def get_files(self) -> list[object]:
            self.listings += 1
            if self.listings == 1:
                return []
            return [SimpleNamespace(id=77, display_name="slides.pdf")]

    class PrewriteRaceCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = PrewriteRaceFolder(id=20, full_name="course files/slides")

    source = tmp_path / "slides.pdf"
    source.write_bytes(b"slides")
    course = PrewriteRaceCourse()
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(course)
    )

    with pytest.raises(SystemExit):
        command_files_upload(
            SimpleNamespace(
                course_id=101,
                files=[str(source)],
                folder="course files/slides",
                folder_id=None,
                on_duplicate="error",
                dry_run=False,
                mutation_mode="apply",
                api_url="https://canvas.example/",
                output=str(output),
            )
        )

    assert course.slides.uploads == []
    row = json.loads(output.read_text(encoding="utf-8"))["files"][0]
    assert row["mutation_status"] == "not_attempted"
    assert row["observed_outcome"] == "prewrite_conflict"


def test_command_files_upload_error_policy_classifies_renamed_race_as_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RenamedRaceFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            assert on_duplicate == "rename"
            self.uploads.append(
                {"source": source, "on_duplicate": on_duplicate, "content_type": content_type}
            )
            return True, {
                "id": 1001,
                "display_name": "slides-1.pdf",
                "filename": "slides-1.pdf",
                "folder_id": self.id,
                "size": Path(source).stat().st_size,
                "content_type": content_type,
            }

    class RenamedRaceCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = RenamedRaceFolder(id=20, full_name="course files/slides")

    source = tmp_path / "slides.pdf"
    source.write_bytes(b"slides")
    course = RenamedRaceCourse()
    output = tmp_path / "upload-report.json"
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(course)
    )

    with pytest.raises(SystemExit):
        command_files_upload(
            SimpleNamespace(
                course_id=101,
                files=[str(source)],
                folder="course files/slides",
                folder_id=None,
                on_duplicate="error",
                dry_run=False,
                mutation_mode="apply",
                api_url="https://canvas.example/",
                output=str(output),
            )
        )

    row = json.loads(output.read_text(encoding="utf-8"))["files"][0]
    assert row["status"] == "conflict"
    assert row["mutation_status"] == "conflict"
    assert row["observed_outcome"] == "renamed_race_conflict"
    assert "not overwritten" in row["error"]
    assert "do not retry" in row["safe_next_action"].lower()


def test_command_files_upload_live_writes_legacy_and_report_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        api_url="https://canvas.example/",
        output=str(output),
        project_root=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    command_files_upload(args)

    legacy_report = json.loads(output.read_text(encoding="utf-8"))
    run_report = json.loads((tmp_path / "report" / "files-upload.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text(encoding="utf-8"))
    assert legacy_report["files"][0]["status"] == "uploaded"
    assert run_report["files"][0]["status"] == "uploaded"
    assert manifest["status"] == "success"


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
        api_url="https://canvas.example/",
        output=None,
    )

    with pytest.raises(SystemExit) as exc:
        command_files_upload(args)

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert '"status": "uploaded"' in output
    assert '"status": "failed"' in output
    assert "Upload incomplete: 1 uploaded, 1 failed." in output


def test_command_files_upload_partial_failure_writes_failed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
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
        api_url="https://canvas.example/",
        output=None,
        project_root=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    with pytest.raises(SystemExit):
        command_files_upload(args)

    report = json.loads((tmp_path / "report" / "files-upload.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in report["files"]] == ["uploaded", "failed"]
    assert manifest["status"] == "failed"


def test_command_files_upload_records_success_when_stable_url_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(FakeUploadCourse())
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="rename",
        dry_run=False,
        api_url="",
        output=None,
        project_root=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    command_files_upload(args)

    output = capsys.readouterr().out
    report = json.loads((tmp_path / "report" / "files-upload.json").read_text("utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text("utf-8"))
    row = report["files"][0]
    assert row["status"] == "uploaded"
    assert row["mutation_status"] == "succeeded"
    assert row["evidence_status"] == "partial"
    assert row["canvas_id"] == 1001
    assert row["canvas_url"] == ""
    assert "Do not retry the upload" in row["evidence_warning"]
    assert "Upload succeeded, but evidence is incomplete" in output
    assert manifest["status"] == "success"


def test_command_files_upload_success_without_id_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NoIdentityFolder(FakeUploadFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            return True, {"display_name": Path(source).name, "folder_id": self.id}

    class NoIdentityCourse(FakeUploadCourse):
        def __init__(self) -> None:
            super().__init__()
            self.slides = NoIdentityFolder(id=20, full_name="course files/slides")

    source = tmp_path / "slides.pdf"
    source.write_text("pdf", encoding="utf-8")
    monkeypatch.setattr(
        "danvas.files.canvas_from_args", lambda args: FakeUploadCanvas(NoIdentityCourse())
    )
    args = SimpleNamespace(
        course_id=101,
        files=[str(source)],
        folder="course files/slides",
        folder_id=None,
        on_duplicate="overwrite",
        dry_run=False,
        api_url="https://canvas.example/",
        output=None,
        project_root=None,
        no_report=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    with pytest.raises(SystemExit) as excinfo:
        command_files_upload(args)

    assert excinfo.value.code == 1
    report = json.loads((tmp_path / "report" / "files-upload.json").read_text("utf-8"))
    assert report["files"][0]["status"] == "indeterminate"
    assert report["files"][0]["mutation_status"] == "indeterminate"
    assert "verify Canvas before retrying" in report["files"][0]["error"]


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
        api_url="https://canvas.example/",
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
        api_url="https://canvas.example/",
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
        api_url="https://canvas.example/",
        output=str(output),
    )

    with pytest.raises(SystemExit):
        command_files_upload(args)

    report_text = output.read_text(encoding="utf-8")
    assert "RuntimeError: POST [redacted-url] failed" in report_text
    assert "canvas.example" not in report_text
    assert "secret-token" not in report_text
