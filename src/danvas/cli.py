"""Unified operational Canvas CLI."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
import tomllib
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import requests
import typer
from bs4 import BeautifulSoup
from canvasapi import Canvas
from canvasapi.exceptions import ResourceDoesNotExist
from dotenv import load_dotenv

from danvas import assignment_audit, gradebook, quiz

DEFAULT_API_URL = "https://auburn.instructure.com/"

ASSIGNMENT_METADATA_FIELDS = {
    "allowed_attempts",
    "allowed_extensions",
    "anonymous_grading",
    "anonymous_peer_reviews",
    "assignment_group_id",
    "automatic_peer_reviews",
    "due_at",
    "external_tool_tag_attributes",
    "final_grader_id",
    "grade_group_students_individually",
    "grader_comments_visible_to_graders",
    "grader_count",
    "graders_anonymous_to_graders",
    "graders_names_visible_to_final_grader",
    "grading_standard_id",
    "grading_type",
    "group_category_id",
    "hide_in_gradebook",
    "integration_data",
    "integration_id",
    "lock_at",
    "moderated_grading",
    "name",
    "notify_of_update",
    "omit_from_final_grade",
    "only_visible_to_overrides",
    "peer_reviews",
    "points_possible",
    "position",
    "published",
    "submission_types",
    "turnitin_enabled",
    "turnitin_settings",
    "unlock_at",
    "vericite_enabled",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def resolve_api_key(*, provider: str, op_reference: str, env_var: str) -> tuple[str, str]:
    attempts = []
    if provider in {"auto", "1password"}:
        if op_reference and shutil.which("op"):
            result = subprocess.run(
                ["op", "read", op_reference],
                capture_output=True,
                text=True,
                check=False,
            )
            token = result.stdout.strip()
            if result.returncode == 0 and token:
                return token, "1password"
            attempts.append(f"1password: {result.stderr.strip() or 'empty token'}")
        else:
            attempts.append("1password: unavailable")
    if provider in {"auto", "env"}:
        token = (os.environ.get(env_var) or "").strip()
        if token:
            return token, f"env:{env_var}"
        attempts.append(f"env:{env_var}: unavailable")
    raise SystemExit(f"Could not resolve Canvas API key. Tried: {'; '.join(attempts)}")


SecretProvider = Literal["auto", "1password", "env"]
AssignmentExportFormat = Literal["auto", "json", "csv", "markdown"]
DiscussionExportFormat = Literal["json", "csv"]


def canvas_from_args(args: Any) -> Canvas:
    api_key, provider_name = resolve_api_key(
        provider=args.secret_provider,
        op_reference=args.op_reference,
        env_var=args.api_key_env,
    )
    print(f"Using API key from: {provider_name}")
    return Canvas(args.api_url, api_key)


def args_for(**kwargs: Any) -> SimpleNamespace:
    """Build the small namespace expected by the command implementation functions."""
    kwargs["api_url"] = kwargs.get("api_url") or os.environ.get("CANVAS_API_URL", DEFAULT_API_URL)
    kwargs["secret_provider"] = kwargs.get("secret_provider") or os.environ.get(
        "CANVAS_SECRET_PROVIDER", "auto"
    )
    kwargs["op_reference"] = kwargs.get("op_reference") or os.environ.get(
        "CANVAS_API_KEY_OP_REFERENCE", ""
    )
    kwargs["api_key_env"] = kwargs.get("api_key_env") or os.environ.get(
        "CANVAS_API_KEY_ENV", "CANVAS_API_KEY"
    )
    return SimpleNamespace(**kwargs)


def clean_filename(name: object, limit: int = 100) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name))
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:limit] or "untitled"


def canvas_object_to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return {str(k): normalize_json(v) for k, v in obj.items()}
    out: dict[str, Any] = {}
    for key, value in getattr(obj, "__dict__", {}).items():
        if key.startswith("_") or callable(value):
            continue
        out[key] = normalize_json(value)
    return out


def normalize_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    return str(value)


def html_to_text(html: str | None) -> str:
    parser = TextExtractor()
    parser.feed(html or "")
    return parser.text()


def slugify(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or fallback


def command_courses(args: Any) -> None:
    canvas = canvas_from_args(args)
    user = canvas.get_current_user()
    rows = []
    for course in user.get_courses(enrollment_state="active"):
        rows.append(
            {
                "id": getattr(course, "id", ""),
                "name": getattr(course, "name", ""),
                "course_code": getattr(course, "course_code", ""),
                "start_at": getattr(course, "start_at", ""),
                "end_at": getattr(course, "end_at", ""),
            }
        )
    rows.sort(key=lambda row: (str(row["course_code"]), str(row["name"])))
    write_rows(Path(args.output), rows, ["id", "name", "course_code", "start_at", "end_at"])
    print(f"Wrote {len(rows)} courses to {args.output}")


def command_roster(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    enrollments = course.get_enrollments(type=[args.enrollment_type], state=["active"])
    rows = []
    for enrollment in enrollments:
        user = enrollment.user
        rows.append(
            {
                "CanvasID": user["id"],
                "Name": user.get("sortable_name", user.get("name", "")),
                "Email": user.get("login_id", ""),
                "SIS_ID": user.get("sis_user_id", ""),
            }
        )
    rows.sort(key=lambda row: row["Name"])
    write_rows(Path(args.output), rows, ["CanvasID", "Name", "Email", "SIS_ID"])
    print(f"Wrote {len(rows)} students to {args.output}")


def write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def command_assignments_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    course_payload = canvas_object_to_dict(course)
    groups = {
        int(group.id): canvas_object_to_dict(group) for group in course.get_assignment_groups()
    }
    rows = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        payload = canvas_object_to_dict(assignment)
        group = groups.get(int(getattr(assignment, "assignment_group_id", 0) or 0), {})
        row = {
            "id": getattr(assignment, "id", ""),
            "name": getattr(assignment, "name", ""),
            "assignment_group_id": getattr(assignment, "assignment_group_id", ""),
            "assignment_group_name": group.get("name", ""),
            "points_possible": getattr(assignment, "points_possible", ""),
            "due_at": getattr(assignment, "due_at", ""),
            "unlock_at": getattr(assignment, "unlock_at", ""),
            "lock_at": getattr(assignment, "lock_at", ""),
            "published": getattr(assignment, "published", ""),
            "html_url": getattr(assignment, "html_url", ""),
            "submission_types": ",".join(getattr(assignment, "submission_types", []) or []),
            "description_text": html_to_text(getattr(assignment, "description", "")),
            "description_html": getattr(assignment, "description", "") or "",
        }
        if args.full:
            row["assignment"] = payload
            row["assignment_group"] = group
        rows.append(row)
    rows.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    output = Path(args.output)
    fmt = resolve_format(output, args.format)
    if fmt == "csv":
        write_rows(
            output,
            rows,
            [
                "id",
                "name",
                "assignment_group_id",
                "assignment_group_name",
                "points_possible",
                "due_at",
                "unlock_at",
                "lock_at",
                "published",
                "html_url",
                "submission_types",
                "description_text",
                "description_html",
            ],
        )
    elif fmt == "markdown":
        write_assignments_markdown(output, course_payload, groups, rows)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} assignments to {output}")


def resolve_format(output: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if output.suffix.lower() == ".csv":
        return "csv"
    if output.suffix.lower() in {".md", ".markdown"} or not output.suffix:
        return "markdown" if not output.suffix else "json"
    return "json"


def write_assignments_markdown(
    output: Path,
    course_payload: dict[str, Any],
    groups: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "course": course_payload,
        "assignment_groups": list(groups.values()),
        "assignment_count": len(rows),
        "points_possible_total": sum(float(row["points_possible"] or 0) for row in rows),
    }
    (output / "course.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for index, row in enumerate(rows, start=1):
        slug = slugify(str(row["name"]), f"assignment-{row['id']}")
        path = output / f"{index:03d}-{slug}-{row['id']}.md"
        metadata = {
            key: row[key] for key in row if key not in {"description_html", "description_text"}
        }
        text = "---\n" + json.dumps(metadata, indent=2, ensure_ascii=False) + "\n---\n\n"
        text += row["description_text"] or row["description_html"] or ""
        path.write_text(text, encoding="utf-8")


def command_assignments_create(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    assignment = load_assignment_markdown(source)
    if args.dry_run:
        print("Dry run - no assignment created.")
        print(json.dumps(assignment, indent=2, ensure_ascii=False))
        return
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    created = course.create_assignment(assignment)
    print(f"Created assignment: {created.name} (ID {created.id})")
    if getattr(created, "html_url", None):
        print(f"URL: {created.html_url}")


def load_assignment_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "+++":
        raise SystemExit(f"Assignment source must start with TOML front matter: {source}")
    close = next(
        (idx for idx, line in enumerate(lines[1:], start=1) if line.strip() == "+++"), None
    )
    if close is None:
        raise SystemExit(f"Assignment source missing closing +++: {source}")
    metadata = tomllib.loads("".join(lines[1:close]))
    body = "".join(lines[close + 1 :])
    if "title" in metadata:
        if "name" in metadata:
            raise SystemExit("Use either 'name' or 'title', not both.")
        metadata["name"] = metadata.pop("title")
    if not str(metadata.get("name", "")).strip():
        raise SystemExit("Assignment metadata must include 'name' or 'title'.")
    unknown = sorted(set(metadata) - ASSIGNMENT_METADATA_FIELDS)
    if unknown:
        raise SystemExit(f"Unsupported assignment metadata field(s): {', '.join(unknown)}")
    import markdown as markdown_lib

    assignment = {key: normalize_canvas_value(value) for key, value in metadata.items()}
    assignment.setdefault("published", False)
    assignment["description"] = markdown_lib.markdown(body, extensions=["extra", "sane_lists"])
    return assignment


def normalize_canvas_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_canvas_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_canvas_value(item) for key, item in value.items()}
    return value


def command_submissions_feedback(args: Any) -> None:
    feedback_dir = Path(args.feedback_dir)
    roster_path = Path(args.roster)
    if not feedback_dir.is_dir():
        raise SystemExit(f"Feedback directory not found: {feedback_dir}")
    if not roster_path.is_file():
        raise SystemExit(f"Roster CSV not found: {roster_path}")
    canvas_ids = load_roster_ids(roster_path)
    files = sorted(feedback_dir.glob(args.pattern))
    matched, unmatched = match_files_to_students(files, canvas_ids)
    print(f"Matched: {len(matched)}")
    if unmatched:
        print(f"Unmatched files ({len(unmatched)}):")
        for path in unmatched:
            print(f"  - {path.name}")
    if args.dry_run:
        for canvas_id, path in matched:
            print(f"  {canvas_ids[canvas_id]} (CanvasID {canvas_id}) <- {path.name}")
        return
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    success = failed = 0
    for canvas_id, path in matched:
        label = f"{canvas_ids[canvas_id]} (CanvasID {canvas_id})"
        try:
            assignment.get_submission(canvas_id).upload_comment(
                file=str(path), comment=args.comment
            )
            success += 1
            print(f"  {label}: uploaded {path.name}")
            time.sleep(args.sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {label}: FAILED {type(exc).__name__}: {exc}")
    print(f"Done. Uploaded: {success}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


def load_roster_ids(path: Path) -> dict[int, str]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if "CanvasID" not in (reader.fieldnames or []):
            raise SystemExit(f"Roster CSV must include CanvasID: {path}")
        return {
            int(row["CanvasID"]): row.get("Name", row["CanvasID"])
            for row in reader
            if row.get("CanvasID")
        }


def match_files_to_students(
    files: list[Path], canvas_ids: dict[int, str]
) -> tuple[list[tuple[int, Path]], list[Path]]:
    matched = []
    unmatched = []
    for path in files:
        ids = [int(value) for value in re.findall(r"(?<!\d)(\d{5,})(?!\d)", path.name)]
        hits = [canvas_id for canvas_id in ids if canvas_id in canvas_ids]
        if len(hits) == 1:
            matched.append((hits[0], path))
        else:
            unmatched.append(path)
    return matched, unmatched


def command_submissions_media(args: Any) -> None:
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    output_root = Path(args.output_dir)
    assignment_dir = output_root / clean_filename(assignment.name)
    assignment_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for submission in assignment.get_submissions(include=["submission_comments", "user"]):
        student_name = clean_filename(student_label(submission))
        prefix = f"{student_name}_sub{submission.id}"
        for attachment in getattr(submission, "attachments", []) or []:
            filename = f"{prefix}_{clean_filename(attachment.filename)}"
            if download_file(
                attachment.url,
                assignment_dir / filename,
                attachment.url,
                getattr(attachment, "content_type", ""),
            ):
                count += 1
        media = getattr(submission, "media_comment", None)
        if media and download_media(media, assignment_dir, prefix):
            count += 1
        for index, comment in enumerate(
            getattr(submission, "submission_comments", []) or [], start=1
        ):
            media = getattr(comment, "media_comment", None)
            if media:
                author = clean_filename(getattr(comment, "author_name", f"comment{index}"))
                if download_media(media, assignment_dir, f"{prefix}_{author}_comment{index}"):
                    count += 1
    print(f"Downloaded {count} files to {assignment_dir}")


def student_label(submission: Any) -> str:
    user = getattr(submission, "user", None)
    if isinstance(user, dict):
        return user.get("sortable_name") or user.get("name") or f"UserID_{submission.user_id}"
    return f"UserID_{getattr(submission, 'user_id', 'unknown')}"


def download_media(media: dict[str, Any], directory: Path, prefix: str) -> bool:
    url = media.get("url")
    if not url:
        return False
    display = clean_filename(media.get("display_name") or media.get("media_id") or "media")
    if "." not in display:
        content_type = media.get("content-type") or "video/mp4"
        display = f"{display}.{content_type.split('/')[-1]}"
    return download_file(url, directory / f"{prefix}_{display}", url, media.get("content-type", ""))


def download_file(url: str, path: Path, original_url: str, content_type: str) -> bool:
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        metadata = {
            "original_download_url": original_url,
            "resolved_download_url": response.url,
            "content_type_from_header": response.headers.get("Content-Type"),
            "content_type_from_canvas": content_type,
            "downloaded_filename": path.name,
        }
        path.with_suffix(path.suffix + ".info.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        print(f"Downloaded: {path}")
        return True
    except requests.RequestException as exc:
        print(f"Failed download {path.name}: {exc}")
        return False


def command_grades_post(args: Any) -> None:
    rows = load_grade_rows(Path(args.grades_csv))
    if args.dry_run:
        print("Dry run - no grades posted:")
        for row in rows:
            print(
                f"  {row.get('Name') or row['CanvasID']} (CanvasID {row['CanvasID']}): {row['Grade']}"
            )
        return
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    success = skipped = failed = 0
    for row in rows:
        canvas_id = int(row["CanvasID"])
        grade = row["Grade"].strip()
        comment = row.get("Comment", "").strip()
        label = f"{row.get('Name') or canvas_id} (CanvasID {canvas_id})"
        try:
            submission = assignment.get_submission(canvas_id, include=["submission_comments"])
            has_grade = grade_matches(submission, grade)
            has_comment = not comment or comment_exists(submission, comment)
            if has_grade and has_comment:
                skipped += 1
                print(f"  {label}: already posted")
                continue
            kwargs: dict[str, Any] = {}
            if not has_grade:
                kwargs["submission"] = {"posted_grade": grade}
            if not has_comment:
                kwargs["comment"] = {"text_comment": comment}
            submission.edit(**kwargs)
            success += 1
            print(f"  {label}: posted")
            time.sleep(args.sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {label}: FAILED {type(exc).__name__}: {exc}")
    print(f"Done. Posted: {success}, Already present: {skipped}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


def command_grades_verify(args: Any) -> None:
    rows = load_grade_rows(Path(args.grades_csv))
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    failures = 0
    for row in rows:
        submission = assignment.get_submission(
            int(row["CanvasID"]), include=["submission_comments"]
        )
        grade_ok = grade_matches(submission, row["Grade"].strip())
        comment = row.get("Comment", "").strip()
        comment_ok = not comment or comment_exists(submission, comment)
        status = "OK" if grade_ok and comment_ok else "MISMATCH"
        print(f"  {row.get('Name') or row['CanvasID']}: {status}")
        failures += 0 if status == "OK" else 1
    if failures:
        raise SystemExit(1)


def load_grade_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Grades CSV not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for column in ("CanvasID", "Grade"):
            if column not in headers:
                raise SystemExit(f"Grades CSV must include {column}. Found: {', '.join(headers)}")
        return [row for row in reader if row.get("CanvasID") and row.get("Grade")]


def grade_matches(submission: Any, expected: str) -> bool:
    score = getattr(submission, "score", None)
    grade = getattr(submission, "grade", None)
    for value in (score, grade):
        if value is None:
            continue
        try:
            return abs(float(value) - float(expected)) < 0.0001
        except ValueError:
            return str(value).strip() == expected.strip()
    return False


def comment_exists(submission: Any, expected: str) -> bool:
    for comment in getattr(submission, "submission_comments", []) or []:
        text = (
            comment.get("comment", "")
            if isinstance(comment, dict)
            else getattr(comment, "comment", "")
        )
        if str(text).strip() == expected.strip():
            return True
    return False


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


app = typer.Typer(
    name="danvas",
    help=(
        "Unified Canvas operations CLI.\n\n"
        "Use this for day-to-day course work: discover courses, export rosters, "
        "create or audit assignments, move submission files, post grades, and score discussions. "
        "It intentionally does not manage archival ledger/history data."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
)
assignments_app = typer.Typer(
    help="Create assignments from Markdown/TOML or export assignment metadata for review.",
    no_args_is_help=True,
)
gradebook_app = typer.Typer(
    help="Check Canvas gradebook exports and audit final-score setup.",
    no_args_is_help=True,
)
quiz_app = typer.Typer(
    help="Analyze Canvas Classic Quiz/Survey student-analysis CSV exports.",
    no_args_is_help=True,
)
submissions_app = typer.Typer(
    help="Download submitted media/attachments or upload per-student feedback files.",
    no_args_is_help=True,
)
grades_app = typer.Typer(
    help="Post grades from CSV, optionally with comments, then verify Canvas matches the CSV.",
    no_args_is_help=True,
)
discussions_app = typer.Typer(
    help="Export discussion posts or score participation for a graded discussion.",
    no_args_is_help=True,
)

app.add_typer(assignments_app, name="assignments")
app.add_typer(gradebook_app, name="gradebook")
app.add_typer(quiz_app, name="quiz")
app.add_typer(submissions_app, name="submissions")
app.add_typer(grades_app, name="grades")
app.add_typer(discussions_app, name="discussions")


ApiUrl = Annotated[
    str | None,
    typer.Option(
        "--api-url", help="Canvas base URL. Defaults to CANVAS_API_URL, then Auburn Canvas."
    ),
]
SecretProviderOption = Annotated[
    SecretProvider,
    typer.Option("--secret-provider", help="Secret source for the Canvas API token."),
]
OpReference = Annotated[
    str | None,
    typer.Option(
        "--op-reference", help="1Password item reference, such as op://Dev/Canvas/credential."
    ),
]
ApiKeyEnv = Annotated[
    str | None,
    typer.Option("--api-key-env", help="Environment variable containing the Canvas API token."),
]
CourseId = Annotated[int, typer.Option("--course-id", help="Canvas course ID.")]
AssignmentId = Annotated[int, typer.Option("--assignment-id", help="Canvas assignment ID.")]


def run_command(func: Any, args: SimpleNamespace) -> None:
    try:
        func(args)
    except ResourceDoesNotExist as exc:
        typer.echo(f"Canvas resource not found: {exc}", err=True)
        raise typer.Exit(1) from exc
    except SystemExit as exc:
        message = str(exc)
        if message and message != "0":
            typer.echo(message, err=True)
        raise typer.Exit(code=exc.code if isinstance(exc.code, int) else 1) from exc


@app.command(help="Export active courses visible to the authenticated Canvas user.")
def courses(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="CSV output path: id, name, course_code, start_at, end_at."
        ),
    ] = Path("courses.csv"),
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_courses,
        args_for(
            output=str(output),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@app.command(
    help="Export active course enrollments to a roster CSV for later grade/feedback matching."
)
def roster(
    course_id: CourseId,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="CSV output path: CanvasID, Name, Email, SIS_ID.")
    ] = Path("roster.csv"),
    enrollment_type: Annotated[
        str,
        typer.Option("--enrollment-type", help="Canvas enrollment type to include."),
    ] = "StudentEnrollment",
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_roster,
        args_for(
            course_id=course_id,
            output=str(output),
            enrollment_type=enrollment_type,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "export", help="Export assignment details as JSON, CSV, or a Markdown directory."
)
def assignments_export(
    course_id: CourseId,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output path. Use .json, .csv, or a directory with --format markdown.",
        ),
    ] = Path("assignments.json"),
    output_format: Annotated[
        AssignmentExportFormat,
        typer.Option("--format", help="Output format. 'auto' infers JSON/CSV from extension."),
    ] = "auto",
    full: Annotated[
        bool,
        typer.Option("--full", help="Include raw Canvas assignment/group payloads in JSON output."),
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_export,
        args_for(
            course_id=course_id,
            output=str(output),
            format=output_format,
            full=full,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "create",
    help="Create one Canvas assignment from Markdown. Use --dry-run first to inspect the payload.",
)
def assignments_create(
    course_id: CourseId,
    source: Annotated[
        Path, typer.Argument(help="Markdown source beginning with +++ TOML assignment metadata.")
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the Canvas payload without creating anything.")
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_create,
        args_for(
            course_id=course_id,
            source=str(source),
            dry_run=dry_run,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "audit",
    help="Compare a saved assignments export to course policy weights and basic setup expectations.",
)
def assignments_audit(
    assignments_path: Annotated[
        Path, typer.Argument(help="Assignments JSON file or Markdown export directory.")
    ],
    course_yaml: Annotated[
        Path | None,
        typer.Option("--course-yaml", help="Optional course policy YAML with expected weights."),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON audit output path.")
    ] = None,
) -> None:
    payload = assignment_audit.audit_assignment_file(assignments_path, course_yaml)
    typer.echo(f"Assignment setup audit: {assignments_path}")
    if payload["canvas_weights"]:
        typer.echo(f"  Canvas weight sum: {payload['weight_sum']}")
    if payload["missing_groups"]:
        typer.echo(f"  Missing groups: {', '.join(payload['missing_groups'])}")
    if payload["extra_groups"]:
        typer.echo(f"  Extra groups: {', '.join(payload['extra_groups'])}")
    typer.echo(f"  Assignments: {payload['assignments']['count']}")
    typer.echo(f"  Unpublished: {len(payload['assignments']['unpublished'])}")
    typer.echo(f"  Missing due dates: {len(payload['assignments']['missing_due_dates'])}")
    if output:
        gradebook.write_json(output, payload)
        typer.echo(f"Wrote {output}")


@gradebook_app.command(
    "check",
    help="Inspect a Canvas gradebook CSV export for structure, score variants, and missing cells.",
)
def gradebook_check(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    course_yaml: Annotated[
        Path | None,
        typer.Option(
            "--course-yaml", help="Optional YAML with exclude_students/final_score_column."
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON check output path.")
    ] = None,
) -> None:
    policy = gradebook.load_policy(course_yaml)
    gb = gradebook.CanvasGradebook.read(gradebook_csv, policy.get("exclude_students") or [])
    payload = gradebook.check_gradebook(gb, final_score_column=policy.get("final_score_column"))
    typer.echo(f"Canvas gradebook check: {gradebook_csv}")
    typer.echo(f"  Included rows: {payload['structure']['included_rows']}")
    typer.echo(f"  Columns: {payload['structure']['columns']}")
    typer.echo(f"  Final score column: {payload['structure']['final_score_column']}")
    typer.echo(f"  Assignment columns: {payload['assignments']['detected_columns']}")
    typer.echo(f"  Assignment groups: {payload['assignments']['detected_groups']}")
    typer.echo(f"  Score variant diff rows: {payload['score_variants']['rows_with_differences']}")
    if payload["missing"]["totals"]:
        typer.echo(f"  Missing/nonnumeric totals: {payload['missing']['totals']}")
    if output:
        gradebook.write_json(output, payload)
        typer.echo(f"Wrote {output}")


@gradebook_app.command(
    "audit",
    help="Audit final-score setup using a gradebook export and optional course policy/assignment snapshot.",
)
def gradebook_audit(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    course_yaml: Annotated[
        Path | None,
        typer.Option(
            "--course-yaml", help="Course policy YAML with weights and reconstruction rules."
        ),
    ] = None,
    assignments_path: Annotated[
        Path | None,
        typer.Option(
            "--assignments",
            help="Optional assignments JSON/directory export for Canvas group weights.",
        ),
    ] = None,
    tolerance: Annotated[
        float, typer.Option("--tolerance", help="Maximum allowed absolute final-score difference.")
    ] = 0.05,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON audit output path.")
    ] = None,
) -> None:
    policy = gradebook.load_policy(course_yaml)
    assignment_weights = None
    if assignments_path:
        assignment_weights = assignment_audit.assignment_group_weights(
            assignment_audit.load_assignment_snapshot(assignments_path)
        )
    gb = gradebook.CanvasGradebook.read(gradebook_csv, policy.get("exclude_students") or [])
    payload = gradebook.audit_gradebook(
        gb,
        policy=policy,
        assignment_weights=assignment_weights,
        tolerance=tolerance,
    )
    typer.echo(f"Canvas gradebook audit: {gradebook_csv}")
    typer.echo(f"  Final score column: {payload['final_score_column']}")
    typer.echo(f"  Weight sum: {payload['weight_sum']}")
    typer.echo(f"  Matched groups: {len(payload['matched_group_columns'])}")
    if payload["missing_weight_groups"]:
        typer.echo(f"  Missing weighted groups: {', '.join(payload['missing_weight_groups'])}")
    recon = payload["reconstruction"]
    typer.echo(f"  Rows compared: {recon['rows_compared']}")
    typer.echo(f"  Max abs diff: {recon['max_abs_diff']}")
    typer.echo(f"  Rows over tolerance: {recon['rows_over_tolerance']}")
    typer.echo(f"  Status: {recon['status']}")
    if output:
        gradebook.write_json(output, payload)
        typer.echo(f"Wrote {output}")


@quiz_app.command(
    "analysis", help="Summarize a Canvas Classic Quiz/Survey student-analysis CSV export."
)
def quiz_analysis(
    student_analysis_csv: Annotated[
        Path, typer.Argument(help="Canvas student-analysis CSV export.")
    ],
    answer_term: Annotated[
        list[str] | None,
        typer.Option(
            "--answer-term",
            help="Question text term to count answers for. Repeat for multiple terms.",
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON analysis output path.")
    ] = None,
) -> None:
    payload = quiz.analyze_student_analysis(student_analysis_csv, answer_terms=answer_term)
    typer.echo(f"Canvas quiz analysis: {student_analysis_csv}")
    typer.echo(f"  Students: {payload['rows']['students']}")
    typer.echo(f"  Submitted: {payload['rows']['submitted']}")
    typer.echo(f"  Question pairs: {len(payload['questions'])}")
    typer.echo(f"  Mean earned: {payload['score_summary']['earned']['mean']}")
    if "answer_counts" in payload:
        typer.echo(f"  Answer counts: {payload['answer_counts']}")
    if output:
        quiz.write_json(output, payload)
        typer.echo(f"Wrote {output}")


@submissions_app.command(
    "media", help="Download all submission attachments and media comments for one assignment."
)
def submissions_media(
    course_id: CourseId,
    assignment_id: AssignmentId,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir", help="Base directory for downloaded files and .info.json metadata."
        ),
    ] = Path("canvas_assignment_files"),
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_media,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output_dir=str(output_dir),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@submissions_app.command(
    "feedback",
    help="Upload feedback files as submission comments, matching Canvas IDs embedded in filenames.",
)
def submissions_feedback(
    course_id: CourseId,
    assignment_id: AssignmentId,
    roster_path: Annotated[
        Path, typer.Option("--roster", "-r", help="Roster CSV with a CanvasID column.")
    ],
    feedback_dir: Annotated[
        Path, typer.Option("--feedback-dir", "-d", help="Directory containing feedback files.")
    ],
    pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            "-p",
            help="Glob pattern inside --feedback-dir, for example '*-feedback.pdf'.",
        ),
    ] = "*",
    comment: Annotated[
        str, typer.Option("--comment", "-c", help="Submission comment text.")
    ] = "Here is your graded feedback.",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show matched/unmatched files without uploading. Recommended first."
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.5,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_feedback,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            roster=str(roster_path),
            feedback_dir=str(feedback_dir),
            pattern=pattern,
            comment=comment,
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "post",
    help="Post assignment grades from CSV. If Comment is present, add it once as a submission comment.",
)
def grades_post(
    course_id: CourseId,
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path,
        typer.Option(
            "--grades-csv", "-g", help="CSV with CanvasID, Grade, optional Name, optional Comment."
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print rows without posting. Recommended before live grade writes."
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.25,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_post,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "verify", help="Check Canvas grades/comments against a CSV and exit nonzero on mismatch."
)
def grades_verify(
    course_id: CourseId,
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path, typer.Option("--grades-csv", "-g", help="CSV with CanvasID, Grade, optional Comment.")
    ],
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_verify,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "export", help="Export all visible posts from one Canvas discussion topic to JSON or CSV."
)
def discussions_export(
    discussion_url: Annotated[
        str, typer.Argument(help="Canvas discussion URL containing course and topic IDs.")
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output file. Use --format csv for spreadsheet review."
        ),
    ] = Path("discussion.json"),
    output_format: Annotated[
        DiscussionExportFormat, typer.Option("--format", help="Output format.")
    ] = "json",
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_export,
        args_for(
            discussion_url=discussion_url,
            output=str(output),
            format=output_format,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "score",
    help="Score student discussion activity from post/reply counts and optionally upload to the graded discussion.",
)
def discussions_score(
    discussion_url: Annotated[
        str, typer.Argument(help="Canvas discussion URL containing course and topic IDs.")
    ],
    points_per_original: Annotated[float, typer.Argument(help="Points awarded per original post.")],
    points_per_response: Annotated[float, typer.Argument(help="Points awarded per response.")],
    max_original_comments: Annotated[int, typer.Argument(help="Maximum original posts counted.")],
    max_responses: Annotated[int, typer.Argument(help="Maximum responses counted.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional CSV output for scored rows.")
    ] = None,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload", help="Post scores and comments to the discussion's Canvas assignment."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show upload actions without writing to Canvas. Implies upload preview.",
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.3,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_score,
        args_for(
            discussion_url=discussion_url,
            points_per_original=points_per_original,
            points_per_response=points_per_response,
            max_original_comments=max_original_comments,
            max_responses=max_responses,
            output=str(output) if output else None,
            upload=upload,
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


def main() -> None:
    load_dotenv()
    app()


if __name__ == "__main__":
    main()
