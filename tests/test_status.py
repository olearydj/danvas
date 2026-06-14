from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from danvas.cli import app
from danvas.status import build_status, command_status

runner = CliRunner()

NOW = dt.datetime(2026, 6, 12, 1, 0, tzinfo=dt.UTC)


def build_snapshot() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-12T00:00:00Z",
        "course": {"id": 101, "name": "INSY 6600"},
        "assignment_groups": [],
        "assignments": [
            {
                "id": 1,
                "name": "Case Study 1",
                "points_possible": 100,
                "due_at": "2026-06-15T04:59:00Z",
                "published": True,
                "submission_types": ["online_upload"],
            },
            {
                "id": 2,
                "name": "Case Study 2",
                "points_possible": 50,
                "due_at": "",
                "published": True,
                "submission_types": ["online_upload"],
            },
            {
                "id": 3,
                "name": "Reflection Paper",
                "points_possible": 10,
                "due_at": "",
                "published": True,
                "submission_types": ["online_text_entry"],
            },
            {
                "id": 9,
                "name": "Case Discussion",
                "points_possible": 10,
                "due_at": "2026-06-20T04:59:00Z",
                "published": True,
                "submission_types": ["discussion_topic"],
            },
        ],
        "folders": [],
        "files": [
            {
                "id": 300,
                "display_name": "notes.pdf",
                "filename": "notes.pdf",
                "canvas_path": "course files/notes.pdf",
                "folder_full_name": "course files",
                "size": 5,
            },
            {
                "id": 301,
                "display_name": "rename.pdf",
                "filename": "rename.pdf",
                "canvas_path": "course files/rename.pdf",
                "folder_full_name": "course files",
                "size": 99,
            },
            {
                "id": 302,
                "display_name": "missing.pdf",
                "filename": "missing.pdf",
                "canvas_path": "course files/missing.pdf",
                "folder_full_name": "course files",
                "size": 7,
            },
        ],
        "discussions": [
            {
                "id": 400,
                "title": "Case Discussion",
                "assignment_id": 9,
                "published": True,
                "locked": False,
                "message_text": "Discuss the case",
            }
        ],
        "announcements": [
            {
                "id": 401,
                "title": "Welcome",
                "published": True,
                "posted_at": "2026-06-01T12:00:00Z",
                "delayed_post_at": "",
                "message_text": "Hello",
            }
        ],
        "quizzes": [
            {"id": 500, "assignment_id": 98, "title": "Chapter 7 Quiz", "published": True},
            {"id": 501, "assignment_id": 97, "title": "Chapter 8 Quiz", "published": False},
        ],
        "group_categories": [
            {
                "id": 700,
                "name": "Case 1 Groups",
                "self_signup": None,
                "group_count": 4,
                "member_count": 16,
                "groups": [],
            }
        ],
    }


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_workspace(root: Path) -> None:
    write(
        root / "content" / "announcements" / "01-welcome.md",
        "---\ntitle: Welcome\npublished: true\n---\n\nHello.\n",
    )
    write(
        root / "content" / "cases" / "case-1-assignment.md",
        "---\ntitle: Case Study 1\npoints_possible: 100\ndue_at: 2026-06-15T04:59:00Z\n"
        "published: true\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "cases" / "case-2-assignment.md",
        "---\ntitle: Case Study 2\npoints_possible: 100\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "cases" / "case-3-assignment.md",
        "---\ntitle: Case Study 3\npoints_possible: 25\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "discussions" / "case-discussion.md",
        "---\ntitle: Case Discussion\npoints_possible: 10\n---\n\nDiscuss.\n",
    )
    write(root / "content" / "quizzes" / "chap07.md", "Quiz title: Chapter 7 Quiz\n")
    write(root / "content" / "quizzes" / "chap07.zip", "fake zip")
    write(root / "notes.pdf", "12345")
    write(root / "rename.pdf", "x")


def classifications(items: list[dict[str, Any]]) -> dict[str, str]:
    return {item["title"]: item["classification"] for item in items}


def test_build_status_classifies_each_section(tmp_path: Path) -> None:
    build_workspace(tmp_path)

    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    sections = payload["sections"]
    assert classifications(sections["assignments"]) == {
        "Case Study 1": "exact",
        "Case Study 2": "metadata mismatch",
        "Case Study 3": "local-only",
        "Reflection Paper": "Canvas-only",
    }
    assert classifications(sections["announcements"]) == {"Welcome": "exact"}
    assert classifications(sections["discussions"]) == {"Case Discussion": "exact"}
    assert classifications(sections["quizzes"]) == {
        "Chapter 7 Quiz": "exact",
        "Chapter 8 Quiz": "Canvas-only",
    }
    assert classifications(sections["files"]) == {
        "course files/notes.pdf": "exact",
        "course files/rename.pdf": "filename-only match",
        "course files/missing.pdf": "Canvas-only",
    }
    assert payload["snapshot"]["stale"] is False
    assert payload["summary"]["exact"] == 5
    assert payload["group_categories"] == [
        {"name": "Case 1 Groups", "group_count": 4, "member_count": 16}
    ]

    mismatch = next(
        item for item in sections["assignments"] if item["title"] == "Case Study 2"
    )
    assert mismatch["details"] == ["points_possible: local 100 != Canvas 50"]


def test_build_status_excludes_discussion_backed_assignments(tmp_path: Path) -> None:
    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    titles = [item["title"] for item in payload["sections"]["assignments"]]
    assert "Case Discussion" not in titles


def test_build_status_flags_stale_snapshot(tmp_path: Path) -> None:
    snapshot = build_snapshot()
    snapshot["generated_at"] = "2026-06-01T00:00:00Z"

    payload = build_status(snapshot, tmp_path, max_age_hours=24, now=NOW)

    assert payload["snapshot"]["stale"] is True
    assert payload["summary"]["snapshot stale"] == 1


def test_build_status_notes_missing_qti_zip(tmp_path: Path) -> None:
    write(tmp_path / "content" / "quizzes" / "chap07.md", "Quiz title: Chapter 7 Quiz\n")

    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    quiz = next(
        item
        for item in payload["sections"]["quizzes"]
        if item["title"] == "Chapter 7 Quiz"
    )
    assert "no QTI zip found next to source" in quiz["details"]


def test_status_cli_writes_json_and_markdown(
    tmp_path: Path, monkeypatch: Any
) -> None:
    build_workspace(tmp_path)
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["status", "--output", "status.json", "--report-md", "status.md"]
    )

    assert result.exit_code == 0, result.output
    assert "Course status: INSY 6600 (101)" in result.output
    assert "metadata mismatch: Case Study 2" in result.output
    payload = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert payload["summary"]["exact"] == 5
    report = (tmp_path / "status.md").read_text(encoding="utf-8")
    assert "# Course Status Report" in report
    assert "Canvas-only: Chapter 8 Quiz" in report


def test_status_cli_uses_configured_assignment_sources(
    tmp_path: Path, monkeypatch: Any
) -> None:
    write(
        tmp_path / "content" / "assignments" / "01-setup-check.md",
        "---\ntitle: Case Study 1\npoints_possible: 100\n"
        "due_at: 2026-06-15T04:59:00Z\npublished: true\n---\n\nSubmit.\n",
    )
    write(
        tmp_path / "content" / "assignments" / "assignment-notes.md",
        "# Assignment Notes\n\nSupport notes, not Canvas source.\n",
    )
    write(
        tmp_path / ".danvas" / "config.toml",
        "\n".join(
            [
                "[canvas]",
                "course_id = 101",
                "",
                "[sources.assignments]",
                'include = ["content/assignments/*.md"]',
            ]
        ),
    )
    snapshot = build_snapshot()
    snapshot["assignments"] = [snapshot["assignments"][0]]
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "Assignments: exact: 1" in result.output
    assert "Canvas-only: Case Study 1" not in result.output


def test_command_status_requires_current_snapshot_schema(tmp_path: Path) -> None:
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    del snapshot["schema_version"]
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    args = SimpleNamespace(
        project_root=str(tmp_path), max_age_hours=None, output=None, report_md=None
    )

    with pytest.raises(SystemExit, match="predates the current format"):
        command_status(args)
