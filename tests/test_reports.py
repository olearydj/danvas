from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from danvas.reports import (
    create_report_run,
    create_sequenced_run_dir,
    discover_report_runs,
    latest_report_run,
    now_for_config,
)


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


def test_discover_report_runs_labels_valid_missing_and_invalid_manifests(
    tmp_path: Path,
) -> None:
    reports_root = tmp_path / ".danvas" / "reports"
    reports_root.mkdir(parents=True)
    valid = reports_root / "2026-06-23-001-status"
    valid.mkdir()
    (valid / "manifest.json").write_text(
        json.dumps(
            {
                "command": "status",
                "generated_at": "2026-06-23T12:00:00-05:00",
                "report_slug": "status",
                "status": "success",
                "course_id": 101,
                "danvas_version": "0.3.0",
                "may_contain_private_student_data": False,
                "files": ["status.json", "status.md"],
            }
        ),
        encoding="utf-8",
    )
    (reports_root / "2026-06-23-002-files-inventory").mkdir()
    invalid = reports_root / "2026-06-23-003-assignment-audit"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("{not-json", encoding="utf-8")

    rows = discover_report_runs(report_root=reports_root)

    assert [row["name"] for row in rows] == [
        "2026-06-23-003-assignment-audit",
        "2026-06-23-002-files-inventory",
        "2026-06-23-001-status",
    ]
    assert rows[0]["manifest_status"] == "invalid"
    assert rows[1]["manifest_status"] == "missing"
    assert rows[1]["report_slug"] == "files-inventory"
    assert rows[2]["manifest_status"] == "valid"
    assert rows[2]["command"] == "status"
    assert rows[2]["files"] == ["status.json", "status.md"]


def test_latest_report_run_returns_newest_valid_matching_slug(tmp_path: Path) -> None:
    reports_root = tmp_path / ".danvas" / "reports"
    reports_root.mkdir(parents=True)
    older = reports_root / "2026-06-23-001-status"
    older.mkdir()
    (older / "manifest.json").write_text(
        json.dumps({"command": "status", "report_slug": "status", "status": "success"}),
        encoding="utf-8",
    )
    newer_other = reports_root / "2026-06-23-002-files-inventory"
    newer_other.mkdir()
    (newer_other / "manifest.json").write_text(
        json.dumps(
            {
                "command": "files inventory",
                "report_slug": "files-inventory",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    newer_status = reports_root / "2026-06-24-001-status"
    newer_status.mkdir()
    (newer_status / "manifest.json").write_text(
        json.dumps({"command": "status", "report_slug": "status", "status": "success"}),
        encoding="utf-8",
    )

    latest = latest_report_run(report_root=reports_root)
    assert latest is not None
    assert latest["name"] == "2026-06-24-001-status"
    latest_files = latest_report_run(slug="files inventory", report_root=reports_root)
    assert latest_files is not None
    assert latest_files["name"] == "2026-06-23-002-files-inventory"
    assert latest_report_run(slug="missing", report_root=reports_root) is None
