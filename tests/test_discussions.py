from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.discussions import (
    command_discussions_export,
    command_discussions_score,
    command_discussions_sync_prompts,
    discussion_posts,
    discussion_prompt_records,
    parse_discussion_url,
    score_discussion,
)
from danvas.grades import build_grade_post_plan, load_grade_rows


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


def write_config(root: Path) -> None:
    config_dir = root / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\napi_url = "https://canvas.example.edu/"\n',
        encoding="utf-8",
    )


def score_args(root: Path, **overrides: Any) -> SimpleNamespace:
    defaults = {
        "discussion_url": "https://canvas.example/courses/101/discussion_topics/9",
        "points_per_original": 2.0,
        "points_per_response": 1.0,
        "max_original_comments": 1,
        "max_responses": 1,
        "output": None,
        "overwrite": False,
        "upload": False,
        "dry_run": False,
        "project_root": str(root),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


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


def test_discussions_export_uses_private_project_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_config(tmp_path)
    topic = SimpleNamespace(id=9, title="Student Topic")
    course = SimpleNamespace(
        get_discussion_topic=lambda topic_id: topic,
        get_full_discussion_topic=lambda topic_id: {
            "participants": [{"id": 11, "display_name": "Student One"}],
            "view": [
                {
                    "id": 1,
                    "user_id": 11,
                    "message": "<p>Private response</p>",
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ],
        },
    )
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: canvas)

    command_discussions_export(
        SimpleNamespace(
            discussion_url="https://canvas.example/courses/101/discussion_topics/9",
            output=None,
            format="json",
            overwrite=False,
            project_root=str(tmp_path),
        )
    )

    output = tmp_path / ".danvas/private/discussions/topic-9/posts.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["artifact_class"] == "private"
    assert payload["posts"][0]["author"] == "Student One"
    terminal = capsys.readouterr().out
    assert "Student One" not in terminal
    assert "Private response" not in terminal


def test_discussions_score_writes_private_plan_without_student_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_config(tmp_path)
    topic = SimpleNamespace(id=9, title="Student Topic", assignment_id=77)
    submission = SimpleNamespace(grade="1", score=1.0)
    assignment = SimpleNamespace(
        id=77,
        name="Discussion Participation",
        get_submission=lambda user_id, include=None: submission,
    )
    course = SimpleNamespace(
        get_discussion_topic=lambda topic_id: topic,
        get_assignment=lambda assignment_id: assignment,
        get_full_discussion_topic=lambda topic_id: {
            "participants": [{"id": 11, "display_name": "Student One"}],
            "view": [
                {
                    "id": 1,
                    "user_id": 11,
                    "message": "<p>Private response</p>",
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ],
        },
        get_enrollments=lambda **kwargs: [
            SimpleNamespace(user_id=11, user={"name": "Student One"})
        ],
    )
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: canvas)

    command_discussions_score(score_args(tmp_path))

    output = tmp_path / ".danvas/private/discussions/topic-9/grade-plan.csv"
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "CanvasID": "11",
            "Name": "Student One",
            "Grade": "2.0",
            "ExpectedCurrentGrade": "1",
            "Comment": (
                "Discussion score: 2.0/3.0\n"
                "Original posts: 1 x 2.0 pts\n"
                "Responses: 0 x 1.0 pts"
            ),
            "CommentAction": "append",
            "OriginalComments": "1",
            "Responses": "0",
            "TotalPosts": "1",
        }
    ]
    loaded_rows = load_grade_rows(output)
    assert loaded_rows[0]["ExpectedCurrentGrade"] == "1"
    grade_plan = build_grade_post_plan(
        assignment,
        loaded_rows,
        expected_assignment_title="Discussion Participation",
        current_user_id=None,
    )
    assert grade_plan["blockers"] == []
    assert grade_plan["actions"][0]["blockers"] == []
    assert grade_plan["actions"][0]["proposed_grade"] == "2.0"
    assert grade_plan["actions"][0]["comment_action"] == "append"
    sidecar = json.loads(
        output.with_name("grade-plan.csv.artifact.json").read_text(encoding="utf-8")
    )
    assert sidecar["assignment_id"] == 77
    assert sidecar["assignment_title"] == "Discussion Participation"
    assert sidecar["scoring"] == {
        "points_per_original": 2.0,
        "points_per_response": 1.0,
        "max_original_comments": 1,
        "max_responses": 1,
    }
    assert sidecar["next_steps"]["preflight"][-2:] == [
        "--expected-assignment-title",
        "Discussion Participation",
    ]
    assert sidecar["next_steps"]["apply"][-1] == "--apply"
    assert sidecar["sha256"]
    terminal = capsys.readouterr().out
    assert "Student One" not in terminal
    assert "Private response" not in terminal


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
    assert (
        (output_dir / "existing-week-1.md")
        .read_text(encoding="utf-8")
        .endswith("Edited locally.\n")
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


def test_discussions_score_requires_graded_discussion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    topic = SimpleNamespace(id=9, title="Ungraded", assignment_id=None)
    course = SimpleNamespace(get_discussion_topic=lambda topic_id: topic)
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: canvas)

    with pytest.raises(SystemExit, match="not graded"):
        command_discussions_score(score_args(tmp_path))


def test_discussions_score_upload_writes_plan_and_exits_nonzero_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_config(tmp_path)

    class ReadOnlySubmission:
        grade = "3"
        score = 3.0

        def edit(self, **kwargs: Any) -> None:
            raise AssertionError("discussions score must never mutate grades")

    topic = SimpleNamespace(id=9, title="Student Topic", assignment_id=77)
    assignment = SimpleNamespace(
        id=77,
        name="Discussion Participation",
        get_submission=lambda user_id: ReadOnlySubmission(),
    )
    course = SimpleNamespace(
        get_discussion_topic=lambda topic_id: topic,
        get_assignment=lambda assignment_id: assignment,
        get_full_discussion_topic=lambda topic_id: {"participants": [], "view": []},
        get_enrollments=lambda **kwargs: [
            SimpleNamespace(user_id=11, user={"name": "Student One"})
        ],
    )
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: canvas)

    with pytest.raises(SystemExit) as exc_info:
        command_discussions_score(score_args(tmp_path, upload=True))

    assert exc_info.value.code == 2
    output = tmp_path / ".danvas/private/discussions/topic-9/grade-plan.csv"
    assert output.is_file()
    terminal = capsys.readouterr().out
    assert "Direct discussion upload was removed" in terminal
    assert "danvas grades post" in terminal
    assert "--apply" in terminal
    assert "Student One" not in terminal


def test_discussions_score_dry_run_is_same_plan_only_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    topic = SimpleNamespace(id=9, title="Student Topic", assignment_id=77)
    submission = SimpleNamespace(grade=None, score=None)
    assignment = SimpleNamespace(
        id=77,
        name="Discussion Participation",
        get_submission=lambda user_id: submission,
    )
    course = SimpleNamespace(
        get_discussion_topic=lambda topic_id: topic,
        get_assignment=lambda assignment_id: assignment,
        get_full_discussion_topic=lambda topic_id: {"participants": [], "view": []},
        get_enrollments=lambda **kwargs: [
            SimpleNamespace(user_id=11, user={"name": "Student One"})
        ],
    )
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr("danvas.discussions.canvas_from_args", lambda args: canvas)

    command_discussions_score(score_args(tmp_path, dry_run=True))

    output = tmp_path / ".danvas/private/discussions/topic-9/grade-plan.csv"
    with output.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["ExpectedCurrentGrade"] == ""
