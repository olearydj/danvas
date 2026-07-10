"""Canvas submission media and feedback operations."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from danvas.auth import canvas_from_args
from danvas.reports import safe_error
from danvas.utils import (
    canvas_object_to_dict,
    clean_filename,
    mark_private,
    normalize_json,
    print_mutation_banner,
    write_json,
    write_rows,
)

SUBMISSION_EXPORT_FIELDS = [
    "canvas_user_id",
    "name",
    "submission_id",
    "attempt",
    "workflow_state",
    "submitted_at",
    "graded_at",
    "score",
    "grade",
    "grader_id",
    "late",
    "missing",
    "excused",
    "attachment_count",
    "attachment_ids",
    "attachment_names",
    "attachment_content_types",
    "attachment_sizes",
    "comment_count",
]


def command_submissions_export(args: Any) -> None:
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    include = ["user", "submission_comments"]
    if getattr(args, "include_history", False):
        include.append("submission_history")
    submissions = list(assignment.get_submissions(include=include))
    rows = [
        submission_record(
            submission,
            include_comments=bool(getattr(args, "include_comments", False)),
            include_history=bool(getattr(args, "include_history", False)),
        )
        for submission in submissions
    ]
    write_submission_export(Path(args.output), rows, overwrite=bool(args.overwrite))
    raw_output = getattr(args, "save_raw", None)
    if raw_output:
        raw_path = Path(raw_output)
        refuse_overwrite(raw_path, bool(args.overwrite))
        write_json(
            raw_path,
            {
                "private_student_data": True,
                "raw_canvas_payloads": [canvas_object_to_dict(row) for row in submissions],
            },
        )
        mark_private(raw_path)
        print(f"Wrote private raw submission export: {raw_path}")


def command_submissions_grades(args: Any) -> None:
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    submissions = list(assignment.get_submissions(include=["user", "submission_comments"]))
    rows = []
    for submission in submissions:
        if getattr(args, "only_graded", False) and getattr(submission, "grade", None) in {None, ""}:
            continue
        base = submission_record(submission, include_comments=True, include_history=False)
        comments = base.pop("comments", [])
        if not comments:
            rows.append({**base, "comment_id": None, "comment_author_id": None, "comment": ""})
        else:
            for comment in comments:
                rows.append(
                    {
                        **base,
                        "comment_id": comment["id"],
                        "comment_author_id": comment["author_id"],
                        "comment_author_name": comment["author_name"],
                        "comment": comment["comment"],
                        "comment_created_at": comment["created_at"],
                    }
                )
    write_submission_export(Path(args.output), rows, overwrite=bool(args.overwrite))


def submission_record(
    submission: Any, *, include_comments: bool, include_history: bool
) -> dict[str, Any]:
    attachments = list(getattr(submission, "attachments", []) or [])
    comments = list(getattr(submission, "submission_comments", []) or [])
    record: dict[str, Any] = {
        "private_student_data": True,
        "canvas_user_id": getattr(submission, "user_id", None),
        "name": student_label(submission),
        "submission_id": getattr(submission, "id", None),
        "attempt": getattr(submission, "attempt", None),
        "workflow_state": getattr(submission, "workflow_state", None),
        "submitted_at": getattr(submission, "submitted_at", None),
        "graded_at": getattr(submission, "graded_at", None),
        "score": getattr(submission, "score", None),
        "grade": getattr(submission, "grade", None),
        "grader_id": getattr(submission, "grader_id", None),
        "late": bool(getattr(submission, "late", False)),
        "missing": bool(getattr(submission, "missing", False)),
        "excused": bool(getattr(submission, "excused", False)),
        "attachment_count": len(attachments),
        "attachment_ids": [getattr(item, "id", None) for item in attachments],
        "attachment_names": [
            getattr(item, "display_name", None) or getattr(item, "filename", "")
            for item in attachments
        ],
        "attachment_content_types": [getattr(item, "content_type", None) for item in attachments],
        "attachment_sizes": [getattr(item, "size", None) for item in attachments],
        "comment_count": len(comments),
    }
    if include_comments:
        record["comments"] = [submission_comment_record(comment) for comment in comments]
    if include_history:
        record["submission_history"] = getattr(submission, "submission_history", []) or []
    return {key: normalize_json(value) for key, value in record.items()}


def submission_comment_record(comment: Any) -> dict[str, Any]:
    def field(name: str) -> Any:
        return comment.get(name) if isinstance(comment, dict) else getattr(comment, name, None)

    return {
        "id": field("id"),
        "author_id": field("author_id"),
        "author_name": field("author_name") or "",
        "comment": field("comment") or "",
        "created_at": field("created_at"),
    }


def write_submission_export(output: Path, rows: list[dict[str, Any]], *, overwrite: bool) -> None:
    refuse_overwrite(output, overwrite)
    if output.suffix.lower() == ".csv":
        flattened = [flatten_submission_row(row) for row in rows]
        fields = list(dict.fromkeys(key for row in flattened for key in row))
        write_rows(output, flattened, fields or SUBMISSION_EXPORT_FIELDS)
    elif output.suffix.lower() == ".json":
        write_json(output, {"private_student_data": True, "submissions": rows})
    else:
        raise SystemExit("Submission export output must end in .json or .csv.")
    mark_private(output)
    print(f"Wrote private submission export: {output}")


def flatten_submission_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
        for key, value in row.items()
    }


def refuse_overwrite(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing output: {path}")


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
    print_mutation_banner(
        "upload feedback comments",
        {
            "course": args.course_id,
            "assignment": args.assignment_id,
            "files": len(matched),
            "comment": args.comment,
        },
    )
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
    layout = getattr(args, "layout", "assignment-subdir")
    assignment_name = clean_filename(assignment.name)
    if layout not in {"flat", "assignment-subdir"}:
        raise SystemExit("--layout must be flat or assignment-subdir.")
    if layout == "assignment-subdir" and clean_filename(output_root.name) == assignment_name:
        print(
            f"WARNING: output already looks like the assignment directory; using {output_root} "
            "without another nested directory."
        )
        assignment_dir = output_root
    else:
        assignment_dir = output_root if layout == "flat" else output_root / assignment_name
    assignment_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    manifest: list[dict[str, Any]] = []
    for submission in assignment.get_submissions(include=["submission_comments", "user"]):
        student_name = clean_filename(student_label(submission))
        prefix = f"{student_name}_sub{submission.id}"
        for attachment in getattr(submission, "attachments", []) or []:
            filename = f"{prefix}_{clean_filename(attachment.filename)}"
            result = download_file(
                attachment.url,
                assignment_dir / filename,
                content_type=getattr(attachment, "content_type", ""),
                stable_id=getattr(attachment, "id", None),
                source="canvas_attachment",
                overwrite=bool(getattr(args, "overwrite", False)),
            )
            manifest.append(
                {
                    **submission_manifest_fields(submission),
                    **result,
                    "canvas_filename": getattr(attachment, "filename", ""),
                }
            )
            if result["download_status"] == "downloaded":
                count += 1
        media = getattr(submission, "media_comment", None)
        if media:
            result = download_media(
                media,
                assignment_dir,
                prefix,
                overwrite=bool(getattr(args, "overwrite", False)),
            )
            manifest.append({**submission_manifest_fields(submission), **result})
            count += result["download_status"] == "downloaded"
        for index, comment in enumerate(
            getattr(submission, "submission_comments", []) or [], start=1
        ):
            media = getattr(comment, "media_comment", None)
            if media:
                author = clean_filename(getattr(comment, "author_name", f"comment{index}"))
                result = download_media(
                    media,
                    assignment_dir,
                    f"{prefix}_{author}_comment{index}",
                    overwrite=bool(getattr(args, "overwrite", False)),
                )
                manifest.append({**submission_manifest_fields(submission), **result})
                count += result["download_status"] == "downloaded"
    manifest_path = collision_safe_path(assignment_dir / "submissions-manifest.json")
    write_json(
        manifest_path,
        {
            "private_student_data": True,
            "course_id": args.course_id,
            "assignment_id": args.assignment_id,
            "assignment_title": assignment.name,
            "files": manifest,
        },
    )
    mark_private(manifest_path)
    print(f"Downloaded {count} files to {assignment_dir}")
    print(f"Wrote private submission manifest: {manifest_path}")


def student_label(submission: Any) -> str:
    user = getattr(submission, "user", None)
    if isinstance(user, dict):
        return user.get("sortable_name") or user.get("name") or f"UserID_{submission.user_id}"
    return f"UserID_{getattr(submission, 'user_id', 'unknown')}"


def download_media(
    media: dict[str, Any], directory: Path, prefix: str, *, overwrite: bool
) -> dict[str, Any]:
    url = media.get("url")
    if not url:
        return download_result(directory / f"{prefix}_media", "missing_url")
    display = clean_filename(media.get("display_name") or media.get("media_id") or "media")
    if "." not in display:
        content_type = media.get("content-type") or "video/mp4"
        display = f"{display}.{content_type.split('/')[-1]}"
    return download_file(
        url,
        directory / f"{prefix}_{display}",
        content_type=media.get("content-type", ""),
        stable_id=media.get("media_id"),
        source="canvas_media_comment",
        overwrite=overwrite,
    )


def download_file(
    url: str,
    path: Path,
    *,
    content_type: str,
    stable_id: Any,
    source: str,
    overwrite: bool,
) -> dict[str, Any]:
    if path.exists() and not overwrite:
        print(f"Skipped existing: {path}")
        return download_result(
            path,
            "skipped_exists",
            stable_id=stable_id,
            source=source,
            content_type=content_type,
        )
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        temporary = path.with_name(f"{path.name}.part")
        temporary.unlink(missing_ok=True)
        with temporary.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        temporary.replace(path)
        mark_private(path)
        sha256 = file_sha256(path)
        integrity_status, integrity_error = file_integrity(path)
        metadata = {
            "private_student_data": True,
            "stable_canvas_id": stable_id,
            "source": source,
            "content_type_from_header": response.headers.get("Content-Type"),
            "content_type_from_canvas": content_type,
            "downloaded_filename": path.name,
            "sha256": sha256,
            "size": path.stat().st_size,
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "integrity_status": integrity_status,
            "integrity_error": integrity_error,
        }
        sidecar = path.with_suffix(path.suffix + ".info.json")
        sidecar.write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        mark_private(sidecar)
        print(f"Downloaded: {path}")
        return {
            **download_result(
                path,
                "downloaded",
                stable_id=stable_id,
                source=source,
                content_type=content_type,
            ),
            **metadata,
        }
    except requests.RequestException as exc:
        path.with_name(f"{path.name}.part").unlink(missing_ok=True)
        print(f"Failed download {path.name}: {safe_error(str(exc))}")
        return {
            **download_result(
                path,
                "failed",
                stable_id=stable_id,
                source=source,
                content_type=content_type,
            ),
            "error": safe_error(f"{type(exc).__name__}: {exc}"),
        }


def submission_manifest_fields(submission: Any) -> dict[str, Any]:
    return {
        "canvas_user_id": getattr(submission, "user_id", None),
        "student": student_label(submission),
        "submission_id": getattr(submission, "id", None),
        "attempt": getattr(submission, "attempt", None),
        "submitted_at": getattr(submission, "submitted_at", None),
    }


def download_result(
    path: Path,
    status: str,
    *,
    stable_id: Any = None,
    source: str = "",
    content_type: str = "",
) -> dict[str, Any]:
    result = {
        "stable_canvas_id": stable_id,
        "source": source,
        "local_path": str(path),
        "download_status": status,
        "content_type_from_canvas": content_type,
    }
    if path.is_file():
        integrity_status, integrity_error = file_integrity(path)
        result.update(
            {
                "sha256": file_sha256(path),
                "size": path.stat().st_size,
                "integrity_status": integrity_status,
                "integrity_error": integrity_error,
            }
        )
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_integrity(path: Path) -> tuple[str, str]:
    if path.suffix.lower() not in {".zip", ".docx", ".xlsx", ".pptx"}:
        return "not_checked", ""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                return "invalid", f"corrupt ZIP member: {bad}"
            if path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
                names = set(archive.namelist())
                required_root = {".docx": "word/", ".xlsx": "xl/", ".pptx": "ppt/"}[
                    path.suffix.lower()
                ]
                if "[Content_Types].xml" not in names or not any(
                    name.startswith(required_root) for name in names
                ):
                    return "invalid", f"missing required OOXML package parts for {path.suffix.lower()}"
    except (OSError, zipfile.BadZipFile) as exc:
        return "invalid", f"{type(exc).__name__}: {exc}"
    return "valid", ""


def collision_safe_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1
