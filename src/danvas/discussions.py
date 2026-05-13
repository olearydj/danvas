"""Canvas discussion export and scoring operations."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from danvas.auth import canvas_from_args
from danvas.utils import write_rows


def parse_discussion_url(url: str) -> tuple[int, int]:
    match = re.search(r"courses/(\d+)/discussion_topics/(\d+)", url)
    if not match:
        raise SystemExit(
            "Discussion URL must contain /courses/{course_id}/discussion_topics/{discussion_id}"
        )
    return int(match.group(1)), int(match.group(2))


def command_discussions_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    course_id, discussion_id = parse_discussion_url(args.discussion_url)
    course = canvas.get_course(course_id)
    topic = course.get_discussion_topic(discussion_id)
    posts = discussion_posts(course, topic)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "csv" or output.suffix.lower() == ".csv":
        fieldnames = [
            "topic_id",
            "topic_title",
            "post_id",
            "parent_id",
            "author",
            "author_id",
            "message",
            "created_at",
            "is_reply",
            "depth",
        ]
        write_rows(output, posts, fieldnames)
    else:
        output.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(posts)} posts to {output}")


def command_discussions_score(args: Any) -> None:
    canvas = canvas_from_args(args)
    course_id, discussion_id = parse_discussion_url(args.discussion_url)
    course = canvas.get_course(course_id)
    topic = course.get_discussion_topic(discussion_id)
    posts = discussion_posts(course, topic)
    students = student_enrollments(course)
    scored = score_discussion(
        posts,
        students,
        args.points_per_original,
        args.points_per_response,
        args.max_original_comments,
        args.max_responses,
    )
    for row in scored:
        print(f"  {row['name']}: {row['score']}")
    if args.output:
        write_rows(
            Path(args.output),
            scored,
            [
                "author_id",
                "name",
                "score",
                "original_comments",
                "responses",
                "total_posts",
                "comment",
            ],
        )
    if args.upload or args.dry_run:
        upload_discussion_scores(
            course, topic, scored, dry_run=args.dry_run, sleep_seconds=args.sleep_seconds
        )


def discussion_posts(course: Any, topic: Any) -> list[dict[str, Any]]:
    data = course.get_full_discussion_topic(topic.id)
    participants = {
        item["id"]: item.get("display_name", f"User {item['id']}")
        for item in data.get("participants", [])
    }
    posts: list[dict[str, Any]] = []

    def walk(entries: list[dict[str, Any]], parent_id: int | None = None, depth: int = 0) -> None:
        for entry in entries:
            if entry.get("deleted"):
                continue
            user_id = entry.get("user_id")
            message = BeautifulSoup(entry.get("message") or "", "html.parser").get_text(" ")
            posts.append(
                {
                    "topic_id": topic.id,
                    "topic_title": topic.title,
                    "post_id": entry.get("id"),
                    "parent_id": parent_id,
                    "author": participants.get(user_id, f"User {user_id}"),
                    "author_id": user_id,
                    "message": " ".join(message.split()),
                    "created_at": entry.get("created_at"),
                    "is_reply": depth > 0,
                    "depth": depth,
                }
            )
            walk(entry.get("replies") or [], entry.get("id"), depth + 1)

    walk(data.get("view", []))
    return posts


def student_enrollments(course: Any) -> dict[int, str]:
    out = {}
    for enrollment in course.get_enrollments(
        type=["StudentEnrollment"], state=["active", "invited"]
    ):
        user = getattr(enrollment, "user", {}) or {}
        out[int(enrollment.user_id)] = (
            user.get("sortable_name") or user.get("name") or f"User {enrollment.user_id}"
        )
    return out


def score_discussion(
    posts: list[dict[str, Any]],
    students: dict[int, str],
    points_per_original: float,
    points_per_response: float,
    max_original_comments: int,
    max_responses: int,
) -> list[dict[str, Any]]:
    post_authors = {post["post_id"]: post.get("author_id") for post in posts}
    counts = {uid: {"original_comments": 0, "responses": 0, "total_posts": 0} for uid in students}
    for post in posts:
        uid = post.get("author_id")
        if uid not in students:
            continue
        counts[uid]["total_posts"] += 1
        parent_author = post_authors.get(post.get("parent_id"))
        if post.get("parent_id") is None or parent_author not in students:
            counts[uid]["original_comments"] += 1
        else:
            counts[uid]["responses"] += 1
    rows = []
    for uid, name in students.items():
        original = counts[uid]["original_comments"]
        responses = counts[uid]["responses"]
        score = (
            min(original, max_original_comments) * points_per_original
            + min(responses, max_responses) * points_per_response
        )
        max_score = (
            max_original_comments * points_per_original + max_responses * points_per_response
        )
        comment = (
            f"Discussion score: {score}/{max_score}\n"
            f"Original posts: {min(original, max_original_comments)} x {points_per_original} pts\n"
            f"Responses: {min(responses, max_responses)} x {points_per_response} pts"
        )
        rows.append(
            {"author_id": uid, "name": name, "score": score, **counts[uid], "comment": comment}
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def upload_discussion_scores(
    course: Any, topic: Any, rows: list[dict[str, Any]], *, dry_run: bool, sleep_seconds: float
) -> None:
    assignment_id = getattr(topic, "assignment_id", None)
    if not assignment_id:
        raise SystemExit("Discussion is not graded and has no assignment_id.")
    assignment = course.get_assignment(assignment_id)
    success = failed = 0
    for row in rows:
        if dry_run:
            print(f"  {row['name']} (user {row['author_id']}): {row['score']}")
            success += 1
            continue
        try:
            assignment.get_submission(row["author_id"]).edit(
                submission={"posted_grade": row["score"]},
                comment={"text_comment": row["comment"]},
            )
            success += 1
            time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {row['name']}: FAILED {type(exc).__name__}: {exc}")
    label = "Dry run" if dry_run else "Upload"
    print(f"{label} complete: {success} succeeded, {failed} failed")
    if failed:
        raise SystemExit(1)
