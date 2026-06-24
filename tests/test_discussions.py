from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.discussions import (
    command_discussions_sync_prompts,
    discussion_posts,
    discussion_prompt_records,
    parse_discussion_url,
    score_discussion,
    upload_discussion_scores,
)


class FakeDiscussionCourse:
    id = 101
    name = "Example Course"
    course_code = "EX-101"

    def __init__(self) -> None:
        self.topics = [
            SimpleNamespace(
                id=2,
                title="Week 2 Discussion",
                posted_at="2026-06-02T14:00:00Z",
                html_url="https://canvas.example/courses/101/discussion_topics/2",
                message="<p>Discuss week 2.</p>",
                published=True,
                due_at="2026-06-07T04:59:00Z",
                assignment_id=2002,
                points_possible=10,
            ),
            SimpleNamespace(
                id=1,
                title="Week 1 Discussion",
                posted_at="2026-06-01T14:00:00Z",
                html_url="https://canvas.example/courses/101/discussion_topics/1",
                message="<p>Discuss <strong>week 1</strong>.</p>",
                published=True,
                due_at="2026-06-06T04:59:00Z",
                assignment_id=2001,
                points_possible=10,
            ),
            SimpleNamespace(
                id=9,
                title="Announcement Topic",
                posted_at="2026-06-03T14:00:00Z",
                html_url="https://canvas.example/courses/101/discussion_topics/9",
                message="<p>Announcement</p>",
                is_announcement=True,
            ),
        ]

    def get_discussion_topics(self, **kwargs: object) -> list[Any]:
        assert kwargs == {}
        return self.topics


class FakeDiscussionCanvas:
    def __init__(self) -> None:
        self.course = FakeDiscussionCourse()

    def get_course(self, course_id: int) -> FakeDiscussionCourse:
        assert course_id == 101
        return self.course


def test_parse_discussion_url_extracts_course_and_topic() -> None:
    url = "https://canvas.example/courses/123/discussion_topics/456?entry=1"

    assert parse_discussion_url(url) == (123, 456)


def test_parse_discussion_url_rejects_other_urls() -> None:
    with pytest.raises(SystemExit, match="Discussion URL"):
        parse_discussion_url("https://canvas.example/courses/123/assignments/456")


def test_discussion_posts_flattens_view_and_strips_html() -> None:
    course = SimpleNamespace(
        get_full_discussion_topic=lambda topic_id: {
            "participants": [{"id": 11, "display_name": "Student One"}],
            "view": [
                {
                    "id": 1,
                    "user_id": 11,
                    "message": "<p>Hello <b>world</b></p>",
                    "created_at": "2026-06-01T00:00:00Z",
                    "replies": [
                        {
                            "id": 2,
                            "user_id": 22,
                            "message": "<p>Reply</p>",
                            "created_at": "2026-06-01T01:00:00Z",
                        }
                    ],
                },
                {"id": 3, "user_id": 11, "message": "<p>Gone</p>", "deleted": True},
            ],
        }
    )
    topic = SimpleNamespace(id=9, title="Week 1")

    posts = discussion_posts(course, topic)

    assert [post["post_id"] for post in posts] == [1, 2]
    assert posts[0]["message"] == "Hello world"
    assert posts[0]["is_reply"] is False
    assert posts[1] == {
        "topic_id": 9,
        "topic_title": "Week 1",
        "post_id": 2,
        "parent_id": 1,
        "author": "User 22",
        "author_id": 22,
        "message": "Reply",
        "created_at": "2026-06-01T01:00:00Z",
        "is_reply": True,
        "depth": 1,
    }


def test_discussion_prompt_records_skip_announcements() -> None:
    records = discussion_prompt_records(FakeDiscussionCourse())

    assert [record["title"] for record in records] == [
        "Week 1 Discussion",
        "Week 2 Discussion",
    ]
    assert records[0]["message"] == "Discuss week 1 ."
    assert records[0]["assignment_id"] == 2001
    assert records[0]["points_possible"] == 10


def test_command_discussions_sync_prompts_dry_run_writes_report_without_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "content" / "discussions"
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: FakeDiscussionCanvas())
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

    command_discussions_sync_prompts(args)

    assert not output_dir.exists()
    report = json.loads((report_dir / "discussions-sync-prompts.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert [action["status"] for action in report["actions"]] == ["would_create", "would_create"]
    assert report["actions"][0]["target_relative_path"] == "001-week-1-discussion.md"
    assert "markdown" not in report["actions"][0]
    assert manifest["command"] == "discussions sync-prompts"
    assert manifest["report_slug"] == "discussions-sync-prompts"
    assert "would_create" in capsys.readouterr().out


def test_command_discussions_sync_prompts_live_creates_missing_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "content" / "discussions"
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: FakeDiscussionCanvas())
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

    command_discussions_sync_prompts(args)

    first = output_dir / "001-week-1-discussion.md"
    second = output_dir / "002-week-2-discussion.md"
    assert first.is_file()
    assert second.is_file()
    text = first.read_text(encoding="utf-8")
    assert "canvas_id: 1" in text
    assert "canvas_url: https://canvas.example/courses/101/discussion_topics/1" in text
    assert "assignment_id: 2001" in text
    assert "points_possible: 10" in text
    assert "Discuss week 1 ." in text
    assert "Announcement" not in text


def test_command_discussions_sync_prompts_skips_known_local_and_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "content" / "discussions"
    output_dir.mkdir(parents=True)
    (output_dir / "existing-week-1.md").write_text(
        """---
title: Week 1 Discussion
canvas_id: 1
---

Edited locally.
""",
        encoding="utf-8",
    )
    (output_dir / "002-week-2-discussion.md").write_text(
        """---
title: Different Discussion
canvas_id: 999
---

Different content.
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: FakeDiscussionCanvas())
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

    command_discussions_sync_prompts(args)

    report = json.loads((report_dir / "discussions-sync-prompts.json").read_text(encoding="utf-8"))
    assert [action["status"] for action in report["actions"]] == [
        "skipped_known_local",
        "conflict",
    ]
    assert (output_dir / "existing-week-1.md").read_text(encoding="utf-8").endswith(
        "Edited locally.\n"
    )
    assert "different canvas_id 999" in report["actions"][1]["reason"]


def make_posts() -> list[dict[str, Any]]:
    return [
        {"post_id": 1, "parent_id": None, "author_id": 11},
        {"post_id": 2, "parent_id": 1, "author_id": 22},
        {"post_id": 3, "parent_id": None, "author_id": 99},
        {"post_id": 4, "parent_id": 3, "author_id": 11},
        {"post_id": 5, "parent_id": 1, "author_id": 22},
        {"post_id": 6, "parent_id": 1, "author_id": 22},
    ]


def test_score_discussion_counts_originals_responses_and_caps() -> None:
    students = {11: "Student One", 22: "Student Two"}

    rows = score_discussion(
        make_posts(),
        students,
        points_per_original=2.0,
        points_per_response=1.0,
        max_original_comments=2,
        max_responses=2,
    )

    by_id = {row["author_id"]: row for row in rows}
    one = by_id[11]
    assert one["original_comments"] == 2
    assert one["score"] == 4.0
    two = by_id[22]
    assert two["responses"] == 3
    assert two["score"] == 2.0
    assert "2 x 1.0 pts" in two["comment"]
    assert [row["name"] for row in rows] == sorted(row["name"] for row in rows)


def test_score_discussion_scores_inactive_students_zero() -> None:
    students = {33: "Silent Student"}

    rows = score_discussion(make_posts(), students, 2.0, 1.0, 2, 2)

    assert rows[0]["score"] == 0.0
    assert rows[0]["total_posts"] == 0


def test_upload_discussion_scores_requires_graded_discussion() -> None:
    topic = SimpleNamespace(assignment_id=None)

    with pytest.raises(SystemExit, match="not graded"):
        upload_discussion_scores(
            SimpleNamespace(), topic, [], dry_run=False, sleep_seconds=0
        )


def test_upload_discussion_scores_posts_grades_and_comments() -> None:
    edits: list[tuple[int, dict[str, Any]]] = []

    class FakeAssignment:
        def get_submission(self, user_id: int) -> Any:
            class FakeSubmission:
                def edit(self, **kwargs: Any) -> None:
                    edits.append((user_id, kwargs))

            return FakeSubmission()

    course = SimpleNamespace(get_assignment=lambda assignment_id: FakeAssignment())
    topic = SimpleNamespace(assignment_id=77)
    rows = [{"author_id": 11, "name": "Student One", "score": 4.0, "comment": "Discussion score"}]

    upload_discussion_scores(course, topic, rows, dry_run=False, sleep_seconds=0)

    assert edits == [
        (
            11,
            {
                "submission": {"posted_grade": 4.0},
                "comment": {"text_comment": "Discussion score"},
            },
        )
    ]


def test_upload_discussion_scores_dry_run_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ExplodingAssignment:
        def get_submission(self, user_id: int) -> Any:
            raise AssertionError("dry run must not fetch submissions")

    course = SimpleNamespace(get_assignment=lambda assignment_id: ExplodingAssignment())
    topic = SimpleNamespace(assignment_id=77)
    rows = [{"author_id": 11, "name": "Student One", "score": 4.0, "comment": "c"}]

    upload_discussion_scores(course, topic, rows, dry_run=True, sleep_seconds=0)

    assert "Dry run complete: 1 succeeded, 0 failed" in capsys.readouterr().out
