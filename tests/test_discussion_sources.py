from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.discussion_sources import (
    command_discussions_create,
    command_discussions_update,
    command_discussions_verify,
    load_discussion_source,
)

SOURCE = """---
title: Unit 4 Discussion
discussion_type: threaded
published: false
points_possible: 10
assignment_group_id: 7
due_at: 2026-09-01T04:59:00Z
---

Discuss the unit.

--- reply ---

## Prompt One

Start with evidence.

--- reply ---

## Prompt Two

Respond to a peer.
"""


class FakeEntry:
    def __init__(self, entry_id: int, message: str) -> None:
        self.id = entry_id
        self.message = message


class FakeAssignment:
    def __init__(self, values: dict[str, Any]) -> None:
        self.id = 900
        self.assignment_group_id = values.get("assignment_group_id")
        self.points_possible = values.get("points_possible")
        self.due_at = values.get("due_at")
        self.unlock_at = values.get("unlock_at", "")
        self.lock_at = values.get("lock_at", "")
        self.published = values.get("published", False)
        self.grading_type = values.get("grading_type", "points")


class FakeTopic:
    def __init__(self, course: FakeCourse, topic_id: int, values: dict[str, Any]) -> None:
        self.course = course
        self.id = topic_id
        self.title = values["title"]
        self.message = values["message"]
        self.discussion_type = values.get("discussion_type", "threaded")
        self.published = values.get("published", False)
        self.require_initial_post = values.get("require_initial_post", "")
        self.group_category_id = values.get("group_category_id", "")
        self.html_url = f"https://canvas.example/courses/101/discussion_topics/{topic_id}"
        self.updated_at = "2026-08-11T12:00:00Z"
        self.assignment_id = 900 if values.get("assignment") else ""
        self.entries: dict[int, FakeEntry] = {}
        self.posted_messages: list[str] = []
        self.update_calls: list[dict[str, Any]] = []

    def post_entry(self, **kwargs: Any) -> FakeEntry:
        message = str(kwargs["message"])
        self.posted_messages.append(message)
        entry = FakeEntry(500 + len(self.entries) + 1, message)
        self.entries[entry.id] = entry
        return entry

    def get_entries(self, ids: list[int]) -> list[FakeEntry]:
        return [self.entries[entry_id] for entry_id in ids if entry_id in self.entries]

    def update(self, **kwargs: Any) -> FakeTopic:
        self.update_calls.append(kwargs)
        for key, value in kwargs.items():
            if key == "assignment":
                for assignment_key, assignment_value in value.items():
                    setattr(self.course.assignment, assignment_key, assignment_value)
            else:
                setattr(self, key, value)
        return self


class FakeCourse:
    id = 101
    name = "Example Course"
    course_code = "EX-101"

    def __init__(self) -> None:
        self.topic: FakeTopic | None = None
        self.assignment = FakeAssignment(
            {
                "assignment_group_id": 7,
                "points_possible": 10,
                "due_at": "2026-09-01T04:59:00Z",
                "published": False,
                "grading_type": "points",
            }
        )
        self.create_calls: list[dict[str, Any]] = []

    def create_discussion_topic(self, **kwargs: Any) -> FakeTopic:
        self.create_calls.append(kwargs)
        if kwargs.get("assignment"):
            self.assignment = FakeAssignment(kwargs["assignment"])
        self.topic = FakeTopic(self, 44, kwargs)
        return self.topic

    def get_discussion_topic(self, topic_id: int) -> FakeTopic:
        if self.topic is None or topic_id != self.topic.id:
            raise KeyError(topic_id)
        return self.topic

    def get_assignment(self, assignment_id: int) -> FakeAssignment:
        if assignment_id != self.assignment.id:
            raise KeyError(assignment_id)
        return self.assignment


class FakeCanvas:
    def __init__(self, course: FakeCourse) -> None:
        self.course = course

    def get_course(self, course_id: int) -> FakeCourse:
        assert course_id == 101
        return self.course


def args(source: Path, **overrides: Any) -> SimpleNamespace:
    values = {
        "source": str(source),
        "course_id": 101,
        "discussion_id": None,
        "seed_replies": True,
        "body_only": False,
        "dry_run": False,
        "project_root": str(source.parent),
        "no_report": True,
        "report_root": None,
        "report_dir": None,
        "report_slug": None,
        "api_url": "https://canvas.example",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def write_source(tmp_path: Path, text: str = SOURCE) -> Path:
    source = tmp_path / "discussion.md"
    source.write_text(text, encoding="utf-8")
    return source


def test_load_discussion_source_splits_root_and_seed_replies(tmp_path: Path) -> None:
    local = load_discussion_source(write_source(tmp_path))

    assert local["topic"]["title"] == "Unit 4 Discussion"
    assert local["body_text"] == "Discuss the unit."
    assert [reply["heading"] for reply in local["seed_replies"]] == [
        "Prompt One",
        "Prompt Two",
    ]
    assert local["assignment"]["points_possible"] == 10


def test_create_requires_seed_confirmation_before_canvas_call(tmp_path: Path) -> None:
    source = write_source(tmp_path)

    with pytest.raises(SystemExit, match="--seed-replies"):
        command_discussions_create(args(source, seed_replies=False, dry_run=True))


def test_create_dry_run_writes_report_without_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path)
    report_dir = tmp_path / "report"
    monkeypatch.setattr(
        "danvas.discussion_sources.canvas_from_args",
        lambda _args: pytest.fail("dry-run must not initialize Canvas"),
    )

    command_discussions_create(
        args(source, dry_run=True, no_report=False, report_dir=str(report_dir))
    )

    report = json.loads((report_dir / "discussions-create.json").read_text("utf-8"))
    assert report["status"] == "would_create"
    assert report["seed_reply_count"] == 2
    assert "message" not in report["topic_payload"]
    assert not (tmp_path / ".danvas" / "source-map.json").exists()


def test_create_posts_seeds_in_reverse_and_records_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path)
    course = FakeCourse()
    monkeypatch.setattr(
        "danvas.discussion_sources.canvas_from_args", lambda _args: FakeCanvas(course)
    )

    command_discussions_create(args(source))

    assert course.create_calls[0]["assignment"]["points_possible"] == 10
    topic = course.topic
    assert topic is not None
    assert "Prompt Two" in topic.posted_messages[0]
    assert "Prompt One" in topic.posted_messages[1]
    source_map = json.loads((tmp_path / ".danvas/source-map.json").read_text("utf-8"))
    entry = source_map["sources"][0]
    assert entry["kind"] == "discussion"
    assert entry["canvas"]["id"] == 44
    assert entry["canvas"]["assignment_id"] == 900
    assert entry["canvas"]["entry_ids"] == [502, 501]
    assert entry["last_posted"]["fields"]["seed_prompt_headings"] == [
        "Prompt One",
        "Prompt Two",
    ]
    assert "body_text" not in entry["last_posted"]["fields"]


def test_verify_uses_source_map_seed_ids_and_checks_headings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path)
    course = FakeCourse()
    monkeypatch.setattr(
        "danvas.discussion_sources.canvas_from_args", lambda _args: FakeCanvas(course)
    )
    command_discussions_create(args(source))

    command_discussions_verify(args(source))


def test_body_only_update_does_not_touch_entries_or_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path)
    course = FakeCourse()
    monkeypatch.setattr(
        "danvas.discussion_sources.canvas_from_args", lambda _args: FakeCanvas(course)
    )
    command_discussions_create(args(source))
    topic = course.topic
    assert topic is not None
    original_entries = dict(topic.entries)
    changed = SOURCE.replace("Discuss the unit.", "Discuss the revised unit.").replace(
        "published: false\n", ""
    )
    source.write_text(changed, encoding="utf-8")

    command_discussions_update(args(source, body_only=True))

    assert topic.update_calls[-1].keys() == {"message"}
    assert topic.published is False
    assert topic.entries == original_entries


def test_full_update_sends_only_declared_metadata_and_never_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path)
    course = FakeCourse()
    monkeypatch.setattr(
        "danvas.discussion_sources.canvas_from_args", lambda _args: FakeCanvas(course)
    )
    command_discussions_create(args(source))
    topic = course.topic
    assert topic is not None
    original_entries = dict(topic.entries)
    source.write_text(
        """---
title: Renamed Discussion
canvas_id: 44
---

Revised root body.

--- reply ---

## Prompt One

Do not repost me.
""",
        encoding="utf-8",
    )

    command_discussions_update(args(source))

    payload = topic.update_calls[-1]
    assert payload.keys() == {"title", "message"}
    assert "assignment" not in payload
    assert topic.entries == original_entries
