from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from danvas.assignments import command_assignments_overrides
from danvas.overrides import private_assignment_overrides, redacted_assignment_overrides


def assignment() -> Any:
    return SimpleNamespace(
        id=123,
        due_at="2026-06-15T04:59:00Z",
        unlock_at=None,
        lock_at="2026-06-15T04:59:59Z",
        all_dates=[
            {
                "title": "Everyone else",
                "base": True,
                "due_at": "2026-06-15T04:59:00Z",
                "lock_at": "2026-06-15T04:59:59Z",
            },
            {
                "id": 900,
                "title": "Extension",
                "due_at": "2026-06-17T04:59:59Z",
                "student_ids": [10, 11],
            },
        ],
        overrides=[
            {
                "id": 900,
                "title": "Extension",
                "due_at": "2026-06-17T04:59:59Z",
                "student_ids": [10, 11],
            }
        ],
    )


def test_redacted_assignment_overrides_omits_members() -> None:
    payload = redacted_assignment_overrides(assignment())

    assert payload["has_overrides"] is True
    assert payload["all_dates"][1]["assignee_count"] == 2
    assert "student_ids" not in json.dumps(payload)
    assert "10" not in json.dumps(payload)


def test_private_assignment_overrides_includes_member_ids() -> None:
    payload = private_assignment_overrides(assignment(), source="content/case.md")

    assert payload["private_student_data"] is True
    assert payload["overrides"][0]["assignees"]["canvas_user_ids"] == [10, 11]


def test_command_assignments_overrides_writes_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Course:
        def get_assignment(self, assignment_id: int, include: list[str]) -> Any:
            assert include == ["all_dates", "overrides"]
            return assignment()

    class Canvas:
        def get_course(self, course_id: int) -> Course:
            return Course()

    monkeypatch.setattr("danvas.assignments.canvas_from_args", lambda args: Canvas())
    output = tmp_path / "overrides.yaml"

    command_assignments_overrides(
        SimpleNamespace(
            course_id=101,
            assignment_id=123,
            output=str(output),
            source="content/case.md",
            overwrite=False,
        )
    )

    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert payload["assignment_id"] == 123
    assert payload["overrides"][0]["assignees"]["canvas_user_ids"] == [10, 11]


def test_command_assignments_overrides_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "overrides.json"
    output.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: (_ for _ in ()).throw(AssertionError("Canvas should not be contacted")),
    )

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        command_assignments_overrides(
            SimpleNamespace(
                course_id=101,
                assignment_id=123,
                output=str(output),
                source="",
                overwrite=False,
            )
        )
