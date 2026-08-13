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

from danvas.artifacts import (
    commit_private_staged_pair,
    ensure_private_directory,
    private_staged_file,
    resolve_private_path,
    warn_if_external_private_path,
    write_private_json,
    write_private_rows,
)
from danvas.auth import canvas_from_args
from danvas.reports import safe_error
from danvas.utils import (
    canvas_object_to_dict,
    clean_filename,
    normalize_json,
    print_mutation_banner,
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
    resolved = resolve_private_path(
        explicit=getattr(args, "output", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative=f"submissions/assignment-{args.assignment_id}/submissions.json",
        option_name="--output",
    )
    warn_if_external_private_path(resolved)
    raw_resolved = None
    if getattr(args, "save_raw", None):
        raw_resolved = resolve_private_path(
            explicit=args.save_raw,
            project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
            default_relative=f"submissions/assignment-{args.assignment_id}/raw.json",
            option_name="--save-raw",
        )
        warn_if_external_private_path(raw_resolved)
    _refuse_private_targets(resolved.path, bool(args.overwrite))
    if raw_resolved:
        _refuse_private_targets(raw_resolved.path, bool(args.overwrite))
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
    write_submission_export(resolved.path, rows, overwrite=bool(args.overwrite))
    if raw_resolved:
        write_private_json(
            raw_resolved.path,
            {
                "private_student_data": True,
                "raw_canvas_payloads": [canvas_object_to_dict(row) for row in submissions],
            },
            command="submissions export",
            overwrite=bool(args.overwrite),
        )
        print(f"Wrote private raw submission export: {raw_resolved.path}")


def command_submissions_grades(args: Any) -> None:
    resolved = resolve_private_path(
        explicit=getattr(args, "output", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative=f"submissions/assignment-{args.assignment_id}/grades.csv",
        option_name="--output",
    )
    warn_if_external_private_path(resolved)
    _refuse_private_targets(resolved.path, bool(args.overwrite))
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
    write_submission_export(resolved.path, rows, overwrite=bool(args.overwrite))


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
    if output.suffix.lower() == ".csv":
        flattened = [flatten_submission_row(row) for row in rows]
        fields = list(dict.fromkeys(key for row in flattened for key in row))
        write_private_rows(
            output,
            flattened,
            fields or SUBMISSION_EXPORT_FIELDS,
            command="submissions export",
            overwrite=overwrite,
        )
    elif output.suffix.lower() == ".json":
        write_private_json(
            output,
            {"private_student_data": True, "submissions": rows},
            command="submissions export",
            overwrite=overwrite,
        )
    else:
        raise SystemExit("Submission export output must end in .json or .csv.")
    print(f"Wrote private submission export: {output}")


def _refuse_private_targets(path: Path, overwrite: bool) -> None:
    if overwrite:
        return
    sidecar = path.with_name(f"{path.name}.artifact.json")
    if path.exists() or (path.suffix.lower() == ".csv" and sidecar.exists()):
        raise SystemExit(f"Refusing to overwrite existing private output: {path}")


def flatten_submission_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
        for key, value in row.items()
    }


def refuse_overwrite(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing output: {path}")


def command_submissions_feedback(args: Any) -> None:
    default_filename = "feedback-plan.json" if args.dry_run else "feedback-results.json"
    resolved = resolve_private_path(
        explicit=getattr(args, "output", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative=f"submissions/assignment-{args.assignment_id}/{default_filename}",
        option_name="--output",
    )
    warn_if_external_private_path(resolved)
    _refuse_private_targets(resolved.path, False)
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
    print(f"Unmatched: {len(unmatched)}")
    evidence: dict[str, Any] = {
        "private_student_data": True,
        "course_id": args.course_id,
        "assignment_id": args.assignment_id,
        "status": "planned" if args.dry_run else "running",
        "matched": [
            {
                "canvas_user_id": canvas_id,
                "student": canvas_ids[canvas_id],
                "feedback_file": path.name,
            }
            for canvas_id, path in matched
        ],
        "unmatched_files": [path.name for path in unmatched],
        "results": [],
    }
    if args.dry_run:
        write_private_json(resolved.path, evidence, command="submissions feedback")
        print(f"Private artifact: {resolved.path}")
        return
    print_mutation_banner(
        "upload feedback comments",
        {
            "course": args.course_id,
            "assignment": args.assignment_id,
            "files": len(matched),
        },
    )
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    success = failed = 0
    for canvas_id, path in matched:
        try:
            assignment.get_submission(canvas_id).upload_comment(
                file=str(path), comment=args.comment
            )
            success += 1
            evidence["results"].append(
                {"canvas_user_id": canvas_id, "status": "uploaded", "error": ""}
            )
            time.sleep(args.sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            evidence["results"].append(
                {
                    "canvas_user_id": canvas_id,
                    "status": "failed",
                    "error": safe_error(f"{type(exc).__name__}: {exc}"),
                }
            )
    evidence["status"] = "success" if not failed else "partial"
    write_private_json(resolved.path, evidence, command="submissions feedback")
    print(f"Done. Uploaded: {success}, Failed: {failed}")
    print(f"Private artifact: {resolved.path}")
    if failed:
        raise SystemExit(1)


def load_roster_ids(path: Path) -> dict[int, str]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "CanvasID" not in fieldnames:
            raise SystemExit(f"Roster CSV must include CanvasID: {path}")
        rows = list(reader)
        if {"LoginID", "Email"} <= set(fieldnames):
            conflicting = [
                row
                for row in rows
                if str(row.get("LoginID") or "").strip().casefold()
                != str(row.get("Email") or "").strip().casefold()
            ]
            if conflicting:
                raise SystemExit(
                    "Roster CSV contains both LoginID and Email with different values."
                )
        return {
            int(row["CanvasID"]): row.get("Name", row["CanvasID"])
            for row in rows
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
    resolved = resolve_private_path(
        explicit=getattr(args, "output_dir", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative=f"submissions/assignment-{args.assignment_id}/media",
        option_name="--output-dir",
    )
    warn_if_external_private_path(resolved)
    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(args.assignment_id)
    output_root = resolved.path
    layout = getattr(args, "layout", "assignment-subdir")
    assignment_name = clean_filename(assignment.name)
    if layout not in {"flat", "assignment-subdir"}:
        raise SystemExit("--layout must be flat or assignment-subdir.")
    if resolved.used_project_default:
        assignment_dir = output_root
    elif layout == "assignment-subdir" and clean_filename(output_root.name) == assignment_name:
        print(
            f"WARNING: output already looks like the assignment directory; using {output_root} "
            "without another nested directory."
        )
        assignment_dir = output_root
    else:
        assignment_dir = output_root if layout == "flat" else output_root / assignment_name
    ensure_private_directory(
        assignment_dir,
        tighten_existing=resolved.used_project_default,
    )
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
    manifest_path = assignment_dir / "artifact-manifest.json"
    write_private_json(
        manifest_path,
        {
            "private_student_data": True,
            "course_id": args.course_id,
            "assignment_id": args.assignment_id,
            "assignment_title": assignment.name,
            "files": manifest,
        },
        command="submissions media",
    )
    print(f"Downloaded: {count}; records: {len(manifest)}")
    print(f"Private artifact bundle: {assignment_dir}")


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
    sidecar = path.with_suffix(path.suffix + ".info.json")
    temporary = path.with_name(f"{path.name}.part")
    if temporary.exists() or temporary.is_symlink():
        raise SystemExit(f"Refusing pre-existing private temporary file: {temporary}")
    if path.exists() and not overwrite:
        return download_result(
            path,
            "skipped_exists",
            stable_id=stable_id,
            source=source,
            content_type=content_type,
        )
    if sidecar.exists() and not overwrite:
        raise SystemExit(f"Refusing existing private media sidecar: {sidecar}")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with private_staged_file(temporary) as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        sha256 = file_sha256(temporary)
        integrity_status, integrity_error = file_integrity(temporary, filename=path.name)
        metadata = {
            "private_student_data": True,
            "stable_canvas_id": stable_id,
            "source": source,
            "content_type_from_header": response.headers.get("Content-Type"),
            "content_type_from_canvas": content_type,
            "downloaded_filename": path.name,
            "sha256": sha256,
            "size": temporary.stat().st_size,
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "integrity_status": integrity_status,
            "integrity_error": integrity_error,
        }
        commit_private_staged_pair(
            temporary,
            path,
            command="submissions media",
            overwrite=overwrite,
            sidecar_path=sidecar,
            sidecar_fields=metadata,
        )
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
        print(f"Private download failed: {safe_error(str(exc))}")
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
        "local_path": path.name,
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


def file_integrity(path: Path, *, filename: str | None = None) -> tuple[str, str]:
    suffix = Path(filename or path.name).suffix.lower()
    if suffix not in {".zip", ".docx", ".xlsx", ".pptx"}:
        return "not_checked", ""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                return "invalid", f"corrupt ZIP member: {bad}"
            if suffix in {".docx", ".xlsx", ".pptx"}:
                names = set(archive.namelist())
                required_root = {".docx": "word/", ".xlsx": "xl/", ".pptx": "ppt/"}[
                    suffix
                ]
                if "[Content_Types].xml" not in names or not any(
                    name.startswith(required_root) for name in names
                ):
                    return "invalid", f"missing required OOXML package parts for {suffix}"
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
