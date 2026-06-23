from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from danvas.reports import create_report_run, create_sequenced_run_dir, now_for_config


def write_config(root: Path, timezone: str = "America/Chicago") -> None:
    config_dir = root / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        f'[canvas]\ncourse_id = 101\ntimezone = "{timezone}"\n',
        encoding="utf-8",
    )


def test_create_sequenced_run_dir_uses_global_daily_sequence(tmp_path: Path) -> None:
    (tmp_path / "2026-06-23-001-status").mkdir()
    (tmp_path / "2026-06-23-002-files-inventory").mkdir()

    path = create_sequenced_run_dir(tmp_path, "2026-06-23", "assignment-audit")

    assert path.name == "2026-06-23-003-assignment-audit"


def test_create_report_run_uses_project_timezone(tmp_path: Path) -> None:
    write_config(tmp_path)

    created_at = now_for_config(tmp_path / ".danvas")

    assert created_at.tzinfo == ZoneInfo("America/Chicago")


def test_create_report_run_writes_manifest(tmp_path: Path) -> None:
    write_config(tmp_path)

    run = create_report_run(
        command="assignments audit",
        slug="assignment-audit",
        project_root=tmp_path,
        course_id=101,
        input_paths=[tmp_path / "assignments.json"],
    )
    run.write_text("assignment-audit.md", "# Report\n")
    manifest_path = run.finish()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["command"] == "assignments audit"
    assert manifest["course_id"] == 101
    assert manifest["report_slug"] == "assignment-audit"
    assert manifest["status"] == "success"
    assert manifest["files"] == ["assignment-audit.md"]


def test_create_report_run_uses_config_course_id_when_omitted(tmp_path: Path) -> None:
    write_config(tmp_path)

    run = create_report_run(
        command="assignments audit",
        slug="assignment-audit",
        project_root=tmp_path,
    )
    manifest_path = run.finish()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["course_id"] == 101


def test_report_run_can_record_failed_status(tmp_path: Path) -> None:
    run = create_report_run(command="files inventory", slug="files-inventory", report_dir=tmp_path / "run")

    manifest_path = run.finish(
        "failed",
        error="POST https://canvas.example/upload?verifier=secret-token token=abc failed",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "secret-token" not in manifest["error"]
    assert "token=abc" not in manifest["error"]
    assert "[url]" in manifest["error"]


def test_create_report_run_refuses_existing_exact_report_dir(tmp_path: Path) -> None:
    target = tmp_path / "report"
    target.mkdir()

    with pytest.raises(FileExistsError):
        create_report_run(command="status", slug="status", report_dir=target)
