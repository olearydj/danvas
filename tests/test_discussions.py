from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from danvas.discussions import (
    discussion_posts,
    parse_discussion_url,
    score_discussion,
    upload_discussion_scores,
)


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
