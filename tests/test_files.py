from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.files import (
    build_file_inventory,
    command_files_download,
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
