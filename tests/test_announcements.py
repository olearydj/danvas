from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.announcements import (
    announcement_records,
    command_announcements_create,
    load_announcement_markdown,
    write_announcements_csv,
)


class FakeCourse:
    def __init__(self) -> None:
        self.topics = [
            SimpleNamespace(
                id=2,
                title="Second Update",
                posted_at="2025-06-02T14:00:00Z",
                html_url="https://canvas.example/courses/1/discussion_topics/2",
                message="<p>Second body</p>",
                user_id=42,
            ),
            SimpleNamespace(
                id=1,
                title="First Update",
                posted_at="2025-06-01T14:00:00Z",
                html_url="https://canvas.example/courses/1/discussion_topics/1",
                message="<p>First body</p>",
                user_id=42,
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
