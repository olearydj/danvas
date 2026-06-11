"""Canvas submission media and feedback operations."""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from danvas.auth import canvas_from_args
from danvas.utils import clean_filename


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
        ids = {int(value) for value in re.findall(r"(?<!\d)(\d{5,})(?!\d)", path.name)}
        hits = sorted(canvas_id for canvas_id in ids if canvas_id in canvas_ids)
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
