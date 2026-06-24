"""Canvas discussion export and scoring operations."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from danvas.auth import canvas_from_args
from danvas.frontmatter import parse_frontmatter
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.utils import (
    canvas_object_to_dict,
    html_to_text,
    print_mutation_banner,
    slugify,
    write_rows,
)


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


def command_discussions_sync_prompts(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    output_dir = Path(args.output_dir)
    records = discussion_prompt_records(course)
    plan = build_discussions_sync_prompts_plan(
        course=course,
        records=records,
        output_dir=output_dir,
        dry_run=bool(args.dry_run),
    )
    if not args.dry_run:
        write_discussions_sync_prompt_files(plan)
    write_discussions_sync_report_run(make_discussions_sync_report_run(args, plan), plan)
    print_discussions_sync_summary(plan)


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


def discussion_prompt_records(course: Any) -> list[dict[str, Any]]:
    records = [
        discussion_prompt_record(topic)
        for topic in course.get_discussion_topics()
        if not bool(first_attr(topic, "is_announcement", "announcement"))
    ]
    records.sort(key=lambda row: (str(row["posted_at"] or ""), str(row["title"] or "")))
    return records


def discussion_prompt_record(topic: Any) -> dict[str, Any]:
    payload = canvas_object_to_dict(topic)
    message_html = first_attr(topic, "message") or payload.get("message") or ""
    return {
        "id": first_attr(topic, "id") or payload.get("id"),
        "title": first_attr(topic, "title") or payload.get("title") or "",
        "html_url": first_attr(topic, "html_url") or payload.get("html_url") or "",
        "posted_at": first_attr(topic, "posted_at", "created_at") or payload.get("posted_at") or "",
        "delayed_post_at": first_attr(topic, "delayed_post_at") or payload.get("delayed_post_at") or "",
        "due_at": first_attr(topic, "due_at") or payload.get("due_at") or "",
        "unlock_at": first_attr(topic, "unlock_at") or payload.get("unlock_at") or "",
        "lock_at": first_attr(topic, "lock_at") or payload.get("lock_at") or "",
        "published": first_attr(topic, "published") if first_attr(topic, "published") != "" else payload.get("published", ""),
        "points_possible": first_attr(topic, "points_possible") or payload.get("points_possible") or "",
        "assignment_id": first_attr(topic, "assignment_id") or payload.get("assignment_id") or "",
        "message": html_to_text(str(message_html)),
        "message_html": message_html,
    }


def first_attr(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None and value != "":
            return value
    return ""


def build_discussions_sync_prompts_plan(
    *,
    course: Any,
    records: list[dict[str, Any]],
    output_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    existing_by_id = existing_discussion_sources(output_dir)
    used_names: set[str] = set()
    actions = []
    for index, record in enumerate(records, start=1):
        path = unique_discussion_path(output_dir, index, record, used_names)
        markdown = render_discussion_source_markdown(record)
        canvas_id = str(record.get("id") or "")
        existing_path = existing_by_id.get(canvas_id) if canvas_id else None
        status = "would_create" if dry_run else "created"
        reason = ""
        if existing_path:
            status = "skipped_known_local"
            reason = "Existing local source has matching canvas_id."
            path = existing_path
        elif path.exists():
            existing_canvas_id = discussion_source_canvas_id(path)
            if existing_canvas_id:
                status = "conflict"
                reason = f"Target exists with different canvas_id {existing_canvas_id}."
            else:
                status = "skipped_exists"
                reason = "Target exists without matching canvas_id."
        actions.append(
            {
                "status": status,
                "reason": reason,
                "canvas_id": record.get("id"),
                "title": record.get("title") or "",
                "canvas_url": record.get("html_url") or "",
                "target_path": str(path),
                "target_relative_path": (
                    path.relative_to(output_dir).as_posix()
                    if path.is_relative_to(output_dir)
                    else str(path)
                ),
                "markdown": markdown if status in {"would_create", "created"} else "",
            }
        )
    return {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "output_dir": str(output_dir),
        "actions": actions,
    }


def existing_discussion_sources(output_dir: Path) -> dict[str, Path]:
    if not output_dir.exists():
        return {}
    by_id = {}
    for path in sorted(output_dir.glob("*.md")):
        canvas_id = discussion_source_canvas_id(path)
        if canvas_id:
            by_id.setdefault(canvas_id, path)
    return by_id


def discussion_source_canvas_id(path: Path) -> str:
    try:
        metadata, _body = parse_frontmatter(
            path.read_text(encoding="utf-8-sig"),
            path,
            "Discussion",
        )
    except (OSError, SystemExit):
        return ""
    return str(metadata.get("canvas_id") or "")


def unique_discussion_path(
    output_dir: Path,
    index: int,
    record: dict[str, Any],
    used_names: set[str],
) -> Path:
    base = f"{index:03d}-{slugify(str(record.get('title') or ''), f'discussion-{index}')}"
    name = f"{base}.md"
    counter = 2
    while name in used_names:
        name = f"{base}-{counter}.md"
        counter += 1
    used_names.add(name)
    return output_dir / name


def render_discussion_source_markdown(record: dict[str, Any]) -> str:
    metadata = {
        "title": record.get("title") or "",
        "canvas_id": record.get("id"),
        "canvas_url": record.get("html_url") or "",
        "posted_at": record.get("posted_at") or "",
        "delayed_post_at": record.get("delayed_post_at") or "",
        "due_at": record.get("due_at") or "",
        "unlock_at": record.get("unlock_at") or "",
        "lock_at": record.get("lock_at") or "",
        "published": record.get("published") if record.get("published") != "" else None,
        "points_possible": record.get("points_possible") or "",
        "assignment_id": record.get("assignment_id") or "",
    }
    metadata = {key: value for key, value in metadata.items() if value not in {"", None}}
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    body = str(record.get("message") or "").strip()
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def write_discussions_sync_prompt_files(plan: dict[str, Any]) -> None:
    for action in plan["actions"]:
        if action["status"] != "created":
            continue
        target = Path(action["target_path"])
        if target.exists():
            action["status"] = "skipped_exists"
            action["reason"] = "Target appeared before write."
            action["markdown"] = ""
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action["markdown"], encoding="utf-8")


def make_discussions_sync_report_run(args: Any, plan: dict[str, Any]) -> ReportRun | None:
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=False,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="discussions sync-prompts",
        slug=report_slug or "discussions-sync-prompts",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(plan["output_dir"])],
        private_data=False,
    )


def write_discussions_sync_report_run(
    report_run: ReportRun | None, plan: dict[str, Any]
) -> None:
    if report_run is None:
        return
    try:
        report_plan = sync_report_payload(plan)
        json_path = report_run.write_json("discussions-sync-prompts.json", report_plan)
        md_path = report_run.write_text(
            "discussions-sync-prompts.md", render_discussions_sync_markdown(report_plan)
        )
        manifest_path = report_run.finish()
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def sync_report_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **plan,
        "actions": [
            {key: value for key, value in action.items() if key != "markdown"}
            for action in plan["actions"]
        ],
    }


def render_discussions_sync_markdown(plan: dict[str, Any]) -> str:
    counts = sync_status_counts(plan["actions"])
    lines = [
        "# Discussions Sync Prompts",
        "",
        f"- Dry run: `{plan['dry_run']}`",
        f"- Output directory: `{plan['output_dir']}`",
        f"- Actions: `{len(plan['actions'])}`",
        "",
        "## Summary",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        [
            "",
            "## Actions",
            "",
            "| Status | Canvas ID | Title | Target | Reason |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for action in plan["actions"]:
        lines.append(
            "| {status} | {canvas_id} | {title} | `{target}` | {reason} |".format(
                status=action["status"],
                canvas_id=action.get("canvas_id") or "",
                title=escape_table(str(action.get("title") or "")),
                target=action.get("target_relative_path") or action.get("target_path") or "",
                reason=escape_table(str(action.get("reason") or "")),
            )
        )
    return "\n".join(lines) + "\n"


def print_discussions_sync_summary(plan: dict[str, Any]) -> None:
    print(json.dumps(sync_status_counts(plan["actions"]), indent=2, sort_keys=True))


def sync_status_counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action["status"]] = counts.get(action["status"], 0) + 1
    return counts


def escape_table(value: str) -> str:
    return value.replace("|", "\\|")


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
    if not dry_run:
        print_mutation_banner(
            "post discussion scores",
            {
                "course": getattr(course, "id", ""),
                "assignment": assignment_id,
                "students": len(rows),
            },
        )
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
