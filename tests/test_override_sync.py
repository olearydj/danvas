from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from danvas.override_sync import (
    command_assignments_overrides_sync,
    plan_override_sync,
    validate_override_payload,
)


class FakeOverride:
    def __init__(self, **values: Any) -> None:
        self.id = int(values.get("id", 0))
        self.__dict__.update(values)
        self.edits: list[dict[str, Any]] = []

    def edit(self, **kwargs: Any) -> FakeOverride:
        payload = kwargs["assignment_override"]
        self.edits.append(payload)
        for key in ("student_ids", "course_section_id", "group_id"):
            if key in payload:
                setattr(self, key, payload[key])
            elif hasattr(self, key):
                delattr(self, key)
        for key, value in payload.items():
            setattr(self, key, value)
        return self


class FakeAssignment:
    def __init__(self, rows: list[FakeOverride]) -> None:
        self.rows = rows
        self.created: list[dict[str, Any]] = []

    def get_overrides(self) -> list[FakeOverride]:
        return self.rows

    def create_override(self, **kwargs: Any) -> FakeOverride:
        payload = kwargs["assignment_override"]
        self.created.append(payload)
        created = FakeOverride(id=max([row.id for row in self.rows], default=899) + 1, **payload)
        self.rows.append(created)
        return created


def write_project(tmp_path: Path, overrides: list[dict[str, Any]]) -> tuple[Path, Path]:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n', encoding="utf-8"
    )
    source = tmp_path / "content" / "test.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 123
title: Test 2
availability_overrides_ref: grading/25-26.Su/test2-overrides.yaml
---

Test instructions.
""",
        encoding="utf-8",
    )
    private_path = tmp_path / "grading" / "25-26.Su" / "test2-overrides.yaml"
    private_path.parent.mkdir(parents=True)
    private_path.write_text(
        yaml.safe_dump(
            {
                "private_student_data": True,
                "assignment_id": 123,
                "source": "content/test.md",
                "base": {"due_at": "2026-07-20T04:59:00Z"},
                "overrides": overrides,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return source, private_path


def args(source: Path, root: Path, report: Path, **updates: Any) -> SimpleNamespace:
    values = {
        "source": str(source),
        "course_id": 101,
        "assignment_id": None,
        "dry_run": True,
        "confirm": "",
        "project_root": str(root),
        "no_report": False,
        "report_root": None,
        "report_dir": str(report),
        "report_slug": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def student_override(
    title: str, ids: list[int], *, override_id: int | None = None
) -> dict[str, Any]:
    return {
        "id": override_id,
        "title": title,
        "due_at": "2026-07-21T04:59:00Z",
        "unlock_at": "2026-07-19T13:00:00Z",
        "lock_at": "2026-07-21T05:15:00Z",
        "assignees": {
            "canvas_user_ids": ids,
            "course_section_id": None,
            "group_id": None,
        },
    }


def test_validate_override_payload_accepts_download_schema() -> None:
    desired = validate_override_payload(
        {"assignment_id": 123, "overrides": [student_override("ProctorU", [12, 11])]},
        123,
    )

    assert desired[0]["target"] == {"kind": "canvas_user_ids", "value": [11, 12]}


def test_plan_updates_membership_and_preserves_canvas_only_rows() -> None:
    desired = validate_override_payload(
        {"assignment_id": 123, "overrides": [student_override("ProctorU", [10, 11])]},
        123,
    )
    proctoru = FakeOverride(
        id=900,
        title="ProctorU",
        due_at="2026-07-21T04:59:00Z",
        unlock_at="2026-07-19T13:00:00Z",
        lock_at="2026-07-21T05:15:00Z",
        student_ids=[10],
    )
    old = FakeOverride(
        id=901,
        title="Existing extension",
        due_at=None,
        unlock_at=None,
        lock_at=None,
        student_ids=[99],
    )

    plan = plan_override_sync(desired, [proctoru, old])

    assert len(plan["updates"]) == 1
    assert plan["updates"][0]["changed_fields"] == ["assignees"]
    assert len(plan["unmanaged"]) == 1
    assert plan["unmanaged"][0]["canvas_override_id"] == 901


def test_plan_reserves_explicit_ids_before_title_fallback() -> None:
    desired = validate_override_payload(
        {
            "assignment_id": 123,
            "overrides": [
                student_override("Extended window", [20]),
                student_override("Extended window", [10], override_id=900),
            ],
        },
        123,
    )
    explicit = FakeOverride(
        id=900,
        title="Extended window",
        due_at="2026-07-21T04:59:00Z",
        unlock_at="2026-07-19T13:00:00Z",
        lock_at="2026-07-21T05:15:00Z",
        student_ids=[10],
    )

    plan = plan_override_sync(desired, [explicit])

    assert len(plan["creates"]) == 1
    assert plan["creates"][0]["assignee_count"] == 1
    assert len(plan["unchanged"]) == 1
    assert plan["unchanged"][0]["canvas_override_id"] == 900


def test_command_dry_run_writes_private_redacted_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = write_project(tmp_path, [student_override("ProctorU", [501234])])
    assignment = FakeAssignment([])
    canvas = SimpleNamespace(
        get_course=lambda course_id: SimpleNamespace(
            get_assignment=lambda assignment_id: assignment
        )
    )
    monkeypatch.setattr("danvas.override_sync.canvas_from_args", lambda options: canvas)
    report_dir = tmp_path / "private-report"

    command_assignments_overrides_sync(args(source, tmp_path, report_dir))

    report_text = (report_dir / "assignments-overrides-sync.json").read_text("utf-8")
    manifest = json.loads((report_dir / "manifest.json").read_text("utf-8"))
    report = json.loads(report_text)
    assert report["status"] == "would_apply"
    assert report["summary"]["creates"] == 1
    assert "501234" not in report_text
    assert assignment.created == []
    assert manifest["may_contain_private_student_data"] is True


def test_command_live_updates_and_creates_then_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = [
        student_override("ProctorU", [10, 11]),
        student_override("Zoom", [20]),
    ]
    source, _ = write_project(tmp_path, local)
    proctoru = FakeOverride(
        id=900,
        title="ProctorU",
        due_at="2026-07-21T04:59:00Z",
        unlock_at="2026-07-19T13:00:00Z",
        lock_at="2026-07-21T05:15:00Z",
        student_ids=[10],
    )
    assignment = FakeAssignment([proctoru])
    canvas = SimpleNamespace(
        get_course=lambda course_id: SimpleNamespace(
            get_assignment=lambda assignment_id: assignment
        )
    )
    monkeypatch.setattr("danvas.override_sync.canvas_from_args", lambda options: canvas)

    command_assignments_overrides_sync(
        args(
            source,
            tmp_path,
            tmp_path / "live-report",
            dry_run=False,
            confirm="apply",
        )
    )

    report = json.loads(
        (tmp_path / "live-report" / "assignments-overrides-sync.json").read_text("utf-8")
    )
    assert proctoru.edits[0]["student_ids"] == [10, 11]
    assert assignment.created[0]["title"] == "Zoom"
    assert report["status"] == "applied"
    assert report["verification"]["updates"] == 0
    assert report["verification"]["creates"] == 0


def test_command_live_requires_explicit_confirmation(tmp_path: Path) -> None:
    source, _ = write_project(tmp_path, [])

    with pytest.raises(SystemExit, match="--live --confirm apply"):
        command_assignments_overrides_sync(
            args(source, tmp_path, tmp_path / "report", dry_run=False)
        )
