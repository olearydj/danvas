from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.courses import command_courses, command_roster


class FakeUser:
    def get_courses(self, enrollment_state: str) -> list[object]:
        assert enrollment_state == "active"
        return [
            SimpleNamespace(id=2, name="Stats", course_code="INSY 6600", start_at="", end_at=""),
            SimpleNamespace(id=1, name="Python", course_code="INSY 3010", start_at="", end_at=""),
        ]


class FakeCanvas:
    def get_current_user(self) -> FakeUser:
        return FakeUser()

    def get_course(self, course_id: int) -> FakeCanvas:
        return self

    def get_enrollments(self, type: list[str], state: list[str]) -> list[object]:
        assert type == ["StudentEnrollment"]
        assert state == ["active"]
        return [
            SimpleNamespace(
                user={
                    "id": 2,
                    "sortable_name": "Reyes, Ana",
                    "login_id": "ana@example.edu",
                    "sis_user_id": "AR1",
                }
            ),
            SimpleNamespace(
                user={
                    "id": 1,
                    "sortable_name": "Lawson, Jack",
                    "login_id": "jack@example.edu",
                    "sis_user_id": "JL1",
                }
            ),
        ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_command_courses_writes_sorted_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("danvas.courses.canvas_from_args", lambda args: FakeCanvas())
    output = tmp_path / "courses.csv"

    command_courses(SimpleNamespace(output=str(output)))

    rows = read_csv(output)
    assert [row["course_code"] for row in rows] == ["INSY 3010", "INSY 6600"]
    assert rows[0]["id"] == "1"


def test_command_roster_writes_sorted_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("danvas.courses.canvas_from_args", lambda args: FakeCanvas())
    output = tmp_path / "roster.csv"

    command_roster(
        SimpleNamespace(course_id=101, output=str(output), enrollment_type="StudentEnrollment")
    )

    rows = read_csv(output)
    assert [row["Name"] for row in rows] == ["Lawson, Jack", "Reyes, Ana"]
    assert rows[0] == {
        "CanvasID": "1",
        "Name": "Lawson, Jack",
        "Email": "jack@example.edu",
        "SIS_ID": "JL1",
    }
