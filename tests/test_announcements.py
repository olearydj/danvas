from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.announcements import (
    announcement_records,
    command_announcements_create,
    command_announcements_latest,
    command_announcements_sync,
    command_announcements_verify,
    load_announcement_markdown,
    write_announcements_csv,
)


class FakeCourse:
    id = 101
    name = "Example Course"
    course_code = "EX-101"

    def __init__(self) -> None:
        self.id = 101
        self.name = "Example Course"
        self.course_code = "EX-101"
        self.topics = [
            SimpleNamespace(
                id=2,
                title="Second Update",
                posted_at="2025-06-02T14:00:00Z",
                html_url="https://canvas.example/courses/1/discussion_topics/2",
                message="<p>Second body</p>",
                user_id=42,
                published=True,
            ),
            SimpleNamespace(
                id=1,
                title="First Update",
                posted_at="2025-06-01T14:00:00Z",
                html_url="https://canvas.example/courses/1/discussion_topics/1",
                message="<p>First body</p>",
                user_id=42,
                published=True,
            ),
        ]
        self.full_topics = {
            1: {
                "participants": [
                    {"id": 42, "display_name": "Instructor"},
                    {"id": 99, "display_name": "Student"},
                ],
                "view": [
                    {
                        "id": 10,
                        "user_id": 99,
                        "message": "<p>Student response</p>",
                        "created_at": "2025-06-01T15:00:00Z",
                        "replies": [
                            {
                                "id": 11,
                                "user_id": 42,
                                "message": "<p>Instructor reply</p>",
                                "created_at": "2025-06-01T16:00:00Z",
                            }
                        ],
                    },
                    {
                        "id": 12,
                        "user_id": 42,
                        "message": "<p>Deleted reply</p>",
                        "created_at": "2025-06-01T17:00:00Z",
                        "deleted": True,
                    },
                ],
            },
            2: {
                "participants": [{"id": 42, "display_name": "Instructor"}],
                "view": [],
            },
        }

    def get_discussion_topics(self, **kwargs: object) -> list[Any]:
        assert kwargs == {"only_announcements": True}
        return self.topics

    def get_full_discussion_topic(self, topic_id: int) -> dict[str, Any]:
        return self.full_topics[topic_id]

    def create_discussion_topic(self, **kwargs: object) -> object:
        self.created_payload = kwargs
        return SimpleNamespace(
            id=3,
            title=kwargs["title"],
            html_url="https://canvas.example/courses/1/discussion_topics/3",
        )


class FakeCanvas:
    def __init__(self) -> None:
        self.course = FakeCourse()

    def get_course(self, course_id: int) -> FakeCourse:
        assert course_id == 101
        return self.course


def test_announcement_records_include_announcements_and_only_selected_replies() -> None:
    records = announcement_records(FakeCourse(), reply_user_id=42)

    assert [record["title"] for record in records] == ["First Update", "Second Update"]
    assert records[0]["message"] == "First body"
    assert records[0]["instructor_replies"] == [
        {
            "id": 11,
            "parent_id": 10,
            "author": "Instructor",
            "author_id": 42,
            "message": "Instructor reply",
            "message_html": "<p>Instructor reply</p>",
            "created_at": "2025-06-01T16:00:00Z",
            "updated_at": None,
            "depth": 1,
        }
    ]
    assert records[1]["instructor_replies"] == []


def test_write_announcements_csv_flattens_without_student_replies(tmp_path: Path) -> None:
    path = tmp_path / "announcements.csv"
    write_announcements_csv(path, announcement_records(FakeCourse(), reply_user_id=42))

    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert [row["record_type"] for row in rows] == [
        "announcement",
        "instructor_reply",
        "announcement",
    ]
    assert "Student response" not in path.read_text(encoding="utf-8")


def test_load_announcement_markdown_accepts_yaml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Welcome Update
published: true
lock_comment: false
---

# Welcome

Hello, **class**.
""",
        encoding="utf-8",
    )

    payload = load_announcement_markdown(source)

    assert payload["title"] == "Welcome Update"
    assert payload["published"] is True
    assert payload["lock_comment"] is False
    assert payload["is_announcement"] is True
    assert "<h1>Welcome</h1>" in payload["message"]
    assert "<strong>class</strong>" in payload["message"]


def test_load_announcement_markdown_still_accepts_toml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """+++
title = "TOML Update"
published = false
+++

Body.
""",
        encoding="utf-8",
    )

    payload = load_announcement_markdown(source)

    assert payload["title"] == "TOML Update"
    assert payload["published"] is False
    assert payload["is_announcement"] is True


def test_load_announcement_markdown_defaults_unpublished(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Draft Update
---

Body.
""",
        encoding="utf-8",
    )

    payload = load_announcement_markdown(source)

    assert payload["published"] is False


def test_load_announcement_markdown_ignores_sync_provenance(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Synced Update
canvas_id: 10
canvas_url: https://canvas.example/announcements/10
posted_at: 2025-06-01T14:00:00Z
published: true
---

Body.
""",
        encoding="utf-8",
    )

    payload = load_announcement_markdown(source)

    assert payload["title"] == "Synced Update"
    assert payload["published"] is True
    assert "canvas_id" not in payload
    assert "canvas_url" not in payload
    assert "posted_at" not in payload


def test_load_announcement_markdown_rejects_missing_title(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
published: false
---

Body.
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="must include 'title'"):
        load_announcement_markdown(source)


def test_load_announcement_markdown_rejects_unknown_metadata(tmp_path: Path) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Bad Update
assignment_group_id: 1
---

Body.
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Unsupported announcement metadata"):
        load_announcement_markdown(source)


def test_command_announcements_create_posts_discussion_announcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Live Update
published: true
---

Body.
""",
        encoding="utf-8",
    )
    fake_canvas = FakeCanvas()
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: fake_canvas)
    args = SimpleNamespace(course_id=101, source=str(source), dry_run=False)

    command_announcements_create(args)

    assert fake_canvas.course.created_payload["title"] == "Live Update"
    assert fake_canvas.course.created_payload["published"] is True
    assert fake_canvas.course.created_payload["is_announcement"] is True
    assert fake_canvas.course.created_payload["message"] == "<p>Body.</p>"


def test_command_announcements_latest_prints_markdown_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(course_id=101, output=None, format="auto")

    command_announcements_latest(args)

    output = capsys.readouterr().out
    assert "# Latest Canvas Announcement" in output
    assert "## Second Update" in output
    assert "First Update" not in output
    assert "- Announcement ID: 2" in output
    assert "Second body" in output


def test_command_announcements_latest_writes_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "latest.json"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(course_id=101, output=str(output), format="auto")

    command_announcements_latest(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["course"]["name"] == "Example Course"
    assert payload["announcement"]["id"] == 2
    assert payload["announcement"]["title"] == "Second Update"


def test_command_announcements_latest_rejects_empty_course(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyCourse(FakeCourse):
        topics: list[Any] = []

        def __init__(self) -> None:
            self.topics = []
            self.full_topics = {}

    monkeypatch.setattr(
        "danvas.announcements.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: EmptyCourse()),
    )
    args = SimpleNamespace(course_id=101, output=None, format="auto")

    with pytest.raises(SystemExit, match="No Canvas announcements found"):
        command_announcements_latest(args)


def test_command_announcements_sync_dry_run_writes_report_without_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "content" / "announcements"
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        output_dir=str(output_dir),
        dry_run=True,
        no_report=False,
        report_root=None,
        report_dir=str(report_dir),
        report_slug=None,
    )

    command_announcements_sync(args)

    assert not output_dir.exists()
    report = json.loads((report_dir / "announcements-sync.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert [action["status"] for action in report["actions"]] == ["would_create", "would_create"]
    assert "markdown" not in report["actions"][0]
    assert report["actions"][0]["target_relative_path"] == "001-first-update.md"
    assert manifest["command"] == "announcements sync"
    assert manifest["report_slug"] == "announcements-sync"
    assert "would_create" in capsys.readouterr().out


def test_command_announcements_sync_live_creates_missing_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "content" / "announcements"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        output_dir=str(output_dir),
        dry_run=False,
        no_report=True,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_announcements_sync(args)

    first = output_dir / "001-first-update.md"
    second = output_dir / "002-second-update.md"
    assert first.is_file()
    assert second.is_file()
    text = first.read_text(encoding="utf-8")
    assert "canvas_id: 1" in text
    assert "canvas_url: https://canvas.example/courses/1/discussion_topics/1" in text
    assert "First body" in text
    assert "Student response" not in text


def test_command_announcements_sync_skips_known_local_and_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "content" / "announcements"
    output_dir.mkdir(parents=True)
    (output_dir / "existing-first.md").write_text(
        """---
title: First Update
canvas_id: 1
---

Edited locally.
""",
        encoding="utf-8",
    )
    (output_dir / "002-second-update.md").write_text(
        """---
title: Different Update
canvas_id: 999
---

Different content.
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        output_dir=str(output_dir),
        dry_run=False,
        no_report=False,
        report_root=None,
        report_dir=str(report_dir),
        report_slug=None,
    )

    command_announcements_sync(args)

    report = json.loads((report_dir / "announcements-sync.json").read_text(encoding="utf-8"))
    assert [action["status"] for action in report["actions"]] == [
        "skipped_known_local",
        "conflict",
    ]
    assert (output_dir / "existing-first.md").read_text(encoding="utf-8").endswith(
        "Edited locally.\n"
    )
    assert "different canvas_id 999" in report["actions"][1]["reason"]


def test_command_announcements_verify_matches_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: First Update
canvas_id: 1
canvas_url: https://canvas.example/courses/1/discussion_topics/1
published: true
---

First body
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        source=str(source),
        announcement_id=None,
        no_report=False,
        report_root=None,
        report_dir=str(report_dir),
        report_slug=None,
    )

    command_announcements_verify(args)

    report = json.loads((report_dir / "announcements-verify.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report["status"] == "matches"
    assert report["canvas_id"] == 1
    assert all(check["matches"] for check in report["checks"])
    assert manifest["command"] == "announcements verify"
    assert manifest["status"] == "success"
    assert "Announcement verify: matches" in capsys.readouterr().out


def test_command_announcements_verify_mismatch_writes_failed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: Wrong Title
canvas_id: 1
published: false
---

Different body
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.announcements.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        source=str(source),
        announcement_id=None,
        no_report=False,
        report_root=None,
        report_dir=str(report_dir),
        report_slug=None,
    )

    with pytest.raises(SystemExit) as exc:
        command_announcements_verify(args)

    assert exc.value.code == 1
    report = json.loads((report_dir / "announcements-verify.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report["status"] == "mismatch"
    assert manifest["status"] == "failed"
    mismatches = [check["field"] for check in report["checks"] if not check["matches"]]
    assert {"title", "published", "body_text"} <= set(mismatches)


def test_command_announcements_verify_requires_canvas_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "announcement.md"
    source.write_text(
        """---
title: First Update
---

First body
""",
        encoding="utf-8",
    )

    def fail_canvas(args: object) -> object:
        raise AssertionError("Canvas should not be contacted")

    monkeypatch.setattr("danvas.announcements.canvas_from_args", fail_canvas)
    args = SimpleNamespace(
        course_id=101,
        project_root=None,
        source=str(source),
        announcement_id=None,
        no_report=True,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    with pytest.raises(SystemExit, match="requires --announcement-id or canvas_id"):
        command_announcements_verify(args)
