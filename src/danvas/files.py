"""Canvas course file inventory operations."""

from __future__ import annotations

import json
import mimetypes
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from danvas.auth import canvas_from_args
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.utils import canvas_object_to_dict, print_mutation_banner, write_json, write_rows

GENERATED_INVENTORY_NAMES = {
    "files-inventory.csv",
    "files-inventory.json",
    "files-missing-report.md",
}

EXCLUDED_LOCAL_PARTS = {
    ".git",
    ".obsidian",
    "_inventory",
    "grading",
    "node_modules",
    "__pycache__",
}

INVENTORY_CSV_FIELDS = [
    "status",
    "id",
    "display_name",
    "filename",
    "folder_full_name",
    "canvas_path",
    "size",
    "content_type",
    "created_at",
    "updated_at",
    "local_matches",
]

OFFICE_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
SENSITIVE_UPLOAD_KEYS = {
    "download_url",
    "error_url",
    "file_param",
    "file_url",
    "token",
    "upload_url",
    "url",
    "verifier",
}
SAFE_UPLOAD_ERROR_KEYS = ("error", "message", "errors", "status", "status_code")
URLISH_RE = re.compile(r"https?://\S+|[A-Za-z]+://\S+")
VERIFIER_RE = re.compile(r"(?i)(verifier|token|secret)=([^&\s]+)")


def command_files_inventory(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    local_root = Path(args.local_root).resolve() if args.local_root else None

    inventory = build_file_inventory(course, local_root=local_root)
    explicit_output_dir = bool(getattr(args, "output_dir", None))
    report_root = getattr(args, "report_root", None)
    report_dir = getattr(args, "report_dir", None)
    report_slug = getattr(args, "report_slug", None)
    no_report = bool(getattr(args, "no_report", False))
    project_root = getattr(args, "project_root", None)
    report_option = bool(report_root or report_dir or report_slug)
    if no_report and report_option:
        raise SystemExit("Use either --no-report or report output options, not both.")
    if no_report and not explicit_output_dir:
        raise SystemExit("Pass --output-dir when using --no-report with files inventory.")

    if explicit_output_dir:
        write_file_inventory_bundle(Path(args.output_dir), inventory)

    report_run = None
    report_enabled = not no_report and (not explicit_output_dir or report_option)
    if report_enabled:
        report_run = create_report_run(
            command="files inventory",
            slug=report_slug or "files-inventory",
            project_root=Path(project_root) if project_root else None,
            report_root=Path(report_root) if report_root else None,
            report_dir=Path(report_dir) if report_dir else None,
            course_id=getattr(course, "id", args.course_id),
            input_paths=[local_root] if local_root else [],
            private_data=False,
        )
        try:
            write_file_inventory_bundle(report_run.path, inventory, report_run=report_run)
            manifest_path = report_run.finish()
            print(f"Wrote {manifest_path}")
            print(f"Report directory: {report_run.path}")
        except Exception as exc:
            report_run.finish("failed", error=str(exc))
            raise

    statuses = Counter(row["status"] for row in inventory["comparison"])
    print(json.dumps(dict(sorted(statuses.items())), indent=2, sort_keys=True))


def write_file_inventory_bundle(
    output_dir: Path, inventory: dict[str, Any], *, report_run: ReportRun | None = None
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_json = output_dir / "files-inventory.json"
    inventory_csv = output_dir / "files-inventory.csv"
    report_md = output_dir / "files-missing-report.md"

    inventory_json.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    write_rows(
        inventory_csv,
        [
            {
                key: "; ".join(row[key]) if key == "local_matches" else row.get(key)
                for key in INVENTORY_CSV_FIELDS
            }
            for row in inventory["comparison"]
        ],
        INVENTORY_CSV_FIELDS,
    )
    write_missing_report(report_md, inventory)

    print(f"Wrote {inventory_json}")
    print(f"Wrote {inventory_csv}")
    print(f"Wrote {report_md}")
    if report_run:
        report_run.record_file(inventory_json)
        report_run.record_file(inventory_csv)
        report_run.record_file(report_md)


def command_files_download(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    folders = list(course.get_folders())
    folders_by_id = {int(folder.id): folder for folder in folders if getattr(folder, "id", None)}
    pairs = [
        (file_obj, canvas_file_record(file_obj, folders_by_id)) for file_obj in course.get_files()
    ]
    path_counts = Counter(download_relative_path(record) for _, record in pairs)
    rows = []
    for file_obj, record in pairs:
        relative_path = download_relative_path(record)
        deduplicated = path_counts[relative_path] > 1
        if deduplicated:
            relative_path = relative_path.with_name(
                f"{relative_path.stem}-{record['id']}{relative_path.suffix}"
            )
        target = output_dir / relative_path
        skipped = target.exists() and not args.overwrite
        if not skipped:
            target.parent.mkdir(parents=True, exist_ok=True)
            file_obj.download(str(target))
        rows.append(
            {
                **record,
                "download_path": target.relative_to(output_dir).as_posix(),
                "deduplicated": deduplicated,
                "status": "skipped_exists" if skipped else "downloaded",
            }
        )

    manifest = {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "files": rows,
    }
    manifest_path = output_dir / "files-download-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    statuses = Counter(row["status"] for row in rows)
    print(f"Wrote {manifest_path}")
    print(json.dumps(dict(sorted(statuses.items())), indent=2, sort_keys=True))


def command_files_upload(args: Any) -> None:
    local_rows = validate_upload_files([Path(path) for path in args.files], args.on_duplicate)
    validate_upload_destination(args.folder, args.folder_id)
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    folder = resolve_upload_folder(canvas, course, folder=args.folder, folder_id=args.folder_id)
    folder_id = getattr(folder, "id", None)
    folder_full_name = str(getattr(folder, "full_name", "") or "")
    report = {
        "course_id": getattr(course, "id", args.course_id),
        "course_name": str(getattr(course, "name", "") or ""),
        "folder_id": folder_id,
        "folder_full_name": folder_full_name,
        "on_duplicate": args.on_duplicate,
        "dry_run": bool(args.dry_run),
        "files": [],
    }
    report_run = make_files_upload_report_run(args, report, local_rows)
    if args.dry_run:
        report["files"] = [{**row, "status": "dry-run"} for row in local_rows]
        print("Dry run - no files uploaded.")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.output:
            write_json(Path(args.output), report)
            print(f"Wrote {args.output}")
        write_files_upload_report_run(report_run, report)
        return

    print_mutation_banner(
        f"upload {len(local_rows)} file(s)",
        {
            "course": report["course_id"],
            "folder": folder_full_name or folder_id,
            "on_duplicate": args.on_duplicate,
        },
    )
    failures = 0
    results = []
    for row in local_rows:
        try:
            ok, response = folder.upload(
                row["source"],
                on_duplicate=args.on_duplicate,
                content_type=row["content_type"],
            )
        except Exception as exc:  # pragma: no cover - exact CanvasAPI exceptions vary.
            ok = False
            response = {"error": safe_upload_error_text(f"{type(exc).__name__}: {exc}")}
        result = upload_result_row(row, ok=bool(ok), response=response, folder=folder)
        results.append(result)
        report["files"] = results
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if result["status"] != "uploaded":
            failures += 1
    if args.output:
        write_json(Path(args.output), report)
        print(f"Wrote {args.output}")
    write_files_upload_report_run(report_run, report)
    if failures:
        uploaded = sum(1 for row in results if row["status"] == "uploaded")
        print(f"Upload incomplete: {uploaded} uploaded, {failures} failed.")
        raise SystemExit(1)


def make_files_upload_report_run(
    args: Any, report: dict[str, Any], local_rows: list[dict[str, Any]]
) -> ReportRun | None:
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=bool(getattr(args, "output", None)),
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="files upload",
        slug=report_slug or "files-upload",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=report["course_id"],
        input_paths=[Path(row["source"]) for row in local_rows],
        private_data=False,
    )


def write_files_upload_report_run(report_run: ReportRun | None, report: dict[str, Any]) -> None:
    if report_run is None:
        return
    try:
        json_path = report_run.write_json("files-upload.json", report)
        status = (
            "failed"
            if any(row.get("status") == "failed" for row in report["files"])
            else "success"
        )
        manifest_path = report_run.finish(status)
        print(f"Wrote {json_path}")
        print(f"Wrote {manifest_path}")
        print(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def build_file_inventory(course: Any, local_root: Path | None = None) -> dict[str, Any]:
    folders = list(course.get_folders())
    folders_by_id = {int(folder.id): folder for folder in folders if getattr(folder, "id", None)}
    canvas_rows = [
        canvas_file_record(file_obj, folders_by_id) for file_obj in course.get_files()
    ]
    local_rows = local_files(local_root) if local_root else []
    local_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in local_rows:
        local_by_name[row["normalized_name"]].append(row)

    comparison_rows = []
    for record in canvas_rows:
        if local_root:
            status, matches = status_for(record, local_by_name)
        else:
            status, matches = "not_compared", []
        comparison_rows.append(
            {
                **record,
                "status": status,
                "local_matches": [match["relative_path"] for match in matches],
            }
        )

    return {
        "course": canvas_object_to_dict(course),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "local_root": str(local_root) if local_root else "",
        "local_files_compared": len(local_rows),
        "canvas_files": canvas_rows,
        "comparison": comparison_rows,
    }


def validate_upload_files(files: list[Path], on_duplicate: str) -> list[dict[str, Any]]:
    if not files:
        raise SystemExit("At least one FILE is required.")
    rows = []
    basenames = Counter(path.name for path in files)
    duplicates = sorted(name for name, count in basenames.items() if count > 1)
    if duplicates and on_duplicate != "rename":
        raise SystemExit(
            "Duplicate local filenames require --on-duplicate rename: "
            + ", ".join(duplicates)
        )
    for path in files:
        if not path.exists():
            raise SystemExit(f"Upload source not found: {path}")
        if not path.is_file():
            raise SystemExit(f"Upload source is not a file: {path}")
        try:
            with path.open("rb"):
                pass
        except OSError as exc:
            raise SystemExit(f"Upload source is not readable: {path}: {exc}") from exc
        stat = path.stat()
        rows.append(
            {
                "source": str(path),
                "name": path.name,
                "size": stat.st_size,
                "content_type": content_type_for(path),
            }
        )
    return rows


def validate_upload_destination(folder: str | None, folder_id: int | None) -> None:
    if folder and folder_id is not None:
        raise SystemExit("Use either --folder or --folder-id, not both.")
    if not folder and folder_id is None:
        raise SystemExit("Destination folder required. Pass --folder or --folder-id.")


def resolve_upload_folder(
    canvas: Any,
    course: Any,
    *,
    folder: str | None,
    folder_id: int | None,
) -> Any:
    if folder_id is not None:
        resolved = canvas.get_folder(folder_id)
        validate_folder_belongs_to_course(resolved, course)
        return resolved

    requested = str(folder or "")
    matches = [
        candidate
        for candidate in course.get_folders()
        if str(getattr(candidate, "full_name", "") or "") == requested
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(f"Canvas folder name is ambiguous: {requested}")
    folders = sorted(str(getattr(candidate, "full_name", "") or "") for candidate in course.get_folders())
    suggestions = nearby_folder_names(requested, folders)
    message = f"Canvas folder not found: {requested}"
    if suggestions:
        message += ". Available nearby folders: " + ", ".join(suggestions)
    raise SystemExit(message)


def validate_folder_belongs_to_course(folder: Any, course: Any) -> None:
    course_id = int(get_canvas_value(course, "id"))
    folder_id = get_canvas_value(folder, "id")
    context_type = get_canvas_value(folder, "context_type", "context-type")
    context_id = get_canvas_value(folder, "context_id", "context-id")
    if context_type is not None or context_id is not None:
        if str(context_type) != "Course" or int_or_none(context_id) != course_id:
            raise SystemExit(
                f"Canvas folder {folder_id} does not belong to course {course_id}."
            )
        return

    course_folder_ids = {
        int(candidate_id)
        for candidate in course.get_folders()
        if (candidate_id := get_canvas_value(candidate, "id")) is not None
    }
    if folder_id is None or int(folder_id) not in course_folder_ids:
        raise SystemExit(f"Canvas folder {folder_id} was not found in course {course_id}.")


def get_canvas_value(obj: Any, *keys: str) -> Any:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                return obj[key]
        return None
    for key in keys:
        attr = key.replace("-", "_")
        if hasattr(obj, attr):
            return getattr(obj, attr)
    return None


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def nearby_folder_names(requested: str, folders: list[str], limit: int = 5) -> list[str]:
    requested_lower = requested.lower()
    requested_parts = [part for part in requested_lower.split("/") if part]
    suggestions = [
        folder
        for folder in folders
        if requested_lower in folder.lower()
        or folder.lower() in requested_lower
        or any(part in folder.lower() for part in requested_parts)
    ]
    if not suggestions:
        suggestions = folders
    return suggestions[:limit]


def content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in OFFICE_CONTENT_TYPES:
        return OFFICE_CONTENT_TYPES[suffix]
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def upload_result_row(
    local_row: dict[str, Any],
    *,
    ok: bool,
    response: Any,
    folder: Any,
) -> dict[str, Any]:
    payload = canvas_object_to_dict(response)
    content_type = payload.get("content-type") or payload.get("content_type") or local_row[
        "content_type"
    ]
    row = {
        **local_row,
        "status": "uploaded" if ok else "failed",
        "canvas_id": payload.get("id"),
        "display_name": payload.get("display_name") or payload.get("filename") or local_row["name"],
        "filename": payload.get("filename") or local_row["name"],
        "folder_id": payload.get("folder_id") or getattr(folder, "id", None),
        "content_type": content_type,
        "url_present": bool(payload.get("url") or payload.get("download_url")),
    }
    if payload.get("size") is not None:
        row["size"] = payload.get("size")
    if not ok:
        row["error"] = safe_upload_error(payload)
    return row


def safe_upload_error(payload: dict[str, Any]) -> str:
    scrubbed = scrub_sensitive_upload_payload(payload)
    for key in SAFE_UPLOAD_ERROR_KEYS:
        if key in scrubbed and scrubbed[key]:
            return safe_upload_error_text(scrubbed[key])
    return "Upload failed without a Canvas error message."


def scrub_sensitive_upload_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): scrub_sensitive_upload_payload(item)
            for key, item in value.items()
            if not is_sensitive_upload_key(str(key))
        }
    if isinstance(value, list):
        return [scrub_sensitive_upload_payload(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_sensitive_upload_payload(item) for item in value]
    if isinstance(value, str):
        return safe_upload_error_text(value)
    return value


def is_sensitive_upload_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_UPLOAD_KEYS)


def safe_upload_error_text(value: Any) -> str:
    text = str(value)
    text = URLISH_RE.sub("[redacted-url]", text)
    text = VERIFIER_RE.sub(r"\1=[redacted]", text)
    return text


def download_relative_path(record: dict[str, Any]) -> Path:
    folder = str(record.get("folder_full_name") or "").strip("/")
    if folder == "course files":
        folder_parts: list[str] = []
    elif folder.startswith("course files/"):
        folder_parts = folder.removeprefix("course files/").split("/")
    elif folder:
        folder_parts = folder.split("/")
    else:
        folder_parts = ["unfiled"]
    parts = [safe_path_component(part) for part in folder_parts if part]
    filename = safe_path_component(str(record.get("display_name") or record.get("filename") or "file"))
    return Path(*parts, filename) if parts else Path(filename)


def safe_path_component(value: str) -> str:
    value = value.replace("\\", "/").split("/")[-1]
    value = re.sub(r'[<>:"|?*\x00-\x1f]', "", value).strip()
    return value or "untitled"


def canvas_file_record(file_obj: Any, folders_by_id: dict[int, Any]) -> dict[str, Any]:
    payload = canvas_object_to_dict(file_obj)
    folder_id = payload.get("folder_id")
    folder = folders_by_id.get(int(folder_id)) if folder_id is not None else None
    folder_full_name = str(getattr(folder, "full_name", "") or "") if folder else ""
    display_name = str(payload.get("display_name") or payload.get("filename") or "")
    filename = str(payload.get("filename") or display_name)
    canvas_path = "/".join(part for part in [folder_full_name, display_name] if part)
    return {
        "id": payload.get("id"),
        "uuid": payload.get("uuid"),
        "display_name": display_name,
        "filename": filename,
        "folder_id": folder_id,
        "folder_full_name": folder_full_name,
        "canvas_path": canvas_path,
        "content_type": payload.get("content-type") or payload.get("content_type") or "",
        "size": payload.get("size"),
        "created_at": payload.get("created_at") or "",
        "updated_at": payload.get("updated_at") or "",
    }


def local_files(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in root.rglob("*"):
        if not path.is_file() or should_skip_local(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        rows.append(
            {
                "relative_path": rel,
                "name": path.name,
                "normalized_name": normalize_text(path.name),
                "normalized_path": normalize_text(rel),
                "size": stat.st_size,
            }
        )
    return rows


def should_skip_local(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.name in GENERATED_INVENTORY_NAMES:
        return True
    if path.name == ".DS_Store":
        return True
    if any(part.startswith(".") for part in rel.parts):
        return True
    if any(part in EXCLUDED_LOCAL_PARTS for part in rel.parts):
        return True
    parts = rel.parts
    return len(parts) >= 3 and parts[0] == "_archive" and parts[2] == "grading"


def status_for(
    record: dict[str, Any], local_by_name: dict[str, list[dict[str, Any]]]
) -> tuple[str, list[dict[str, Any]]]:
    display_name = normalize_text(str(record.get("display_name") or ""))
    filename = normalize_text(str(record.get("filename") or ""))
    matches = list(local_by_name.get(display_name, [])) if display_name else []
    if not matches and filename and filename != display_name:
        matches = list(local_by_name.get(filename, []))
    if not matches:
        return "missing", []
    size = record.get("size")
    if size is not None and any(match.get("size") == size for match in matches):
        return "present_by_name_and_size", matches
    if len(matches) == 1:
        return "present_by_name", matches
    return "ambiguous_name_match", matches


def write_missing_report(output: Path, inventory: dict[str, Any]) -> None:
    comparison_rows = inventory["comparison"]
    canvas_rows = inventory["canvas_files"]
    local_files_compared = inventory["local_files_compared"]
    missing = [row for row in comparison_rows if row["status"] == "missing"]
    present_size = [row for row in comparison_rows if row["status"] == "present_by_name_and_size"]
    present_name = [row for row in comparison_rows if row["status"] == "present_by_name"]
    ambiguous = [row for row in comparison_rows if row["status"] == "ambiguous_name_match"]
    by_folder = Counter(row["folder_full_name"] or "(no folder)" for row in canvas_rows)
    missing_by_folder = Counter(row["folder_full_name"] or "(no folder)" for row in missing)

    course = inventory.get("course", {})
    course_label = course.get("name") or course.get("course_code") or course.get("id") or ""
    lines = [
        "# Canvas Files Inventory",
        "",
        f"- Course: `{course_label}`",
        f"- Canvas course ID: `{course.get('id', '')}`",
        f"- Generated: `{inventory['generated_at']}`",
        f"- Canvas files inventoried: `{len(canvas_rows)}`",
        f"- Local files compared: `{local_files_compared}`",
        f"- Present by filename and size: `{len(present_size)}`",
        f"- Present by filename only: `{len(present_name)}`",
        f"- Ambiguous local filename matches: `{len(ambiguous)}`",
        f"- Missing locally by filename: `{len(missing)}`",
        "",
        "Local comparison excludes generated `_inventory` output, grading folders, hidden files, and student-response grading archives.",
        "",
        "## Canvas Folder Summary",
        "",
        "| Canvas folder | Files | Missing locally |",
        "|---|---:|---:|",
    ]
    for folder, count in sorted(by_folder.items()):
        lines.append(f"| {escape_markdown_table(folder)} | {count} | {missing_by_folder.get(folder, 0)} |")
    lines.extend(["", "## Missing Locally", ""])
    if not inventory.get("local_root"):
        lines.append("Local comparison skipped; run with --local-root to compare.")
    elif missing:
        lines.extend(["| Canvas folder | File | Size | Updated | Type |", "|---|---|---:|---|---|"])
        for row in sorted(missing, key=lambda r: (r["folder_full_name"], r["display_name"])):
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_markdown_table(str(row["folder_full_name"] or "")),
                        escape_markdown_table(str(row["display_name"] or row["filename"])),
                        human_size(row.get("size")),
                        escape_markdown_table(str(row.get("updated_at") or "")),
                        escape_markdown_table(str(row.get("content_type") or "")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No Canvas files are missing by filename.")
    lines.extend(["", "## Present Or Matched", "", "| Status | Canvas file | Local match(es) |", "|---|---|---|"])
    for row in sorted(
        [r for r in comparison_rows if r["status"] not in {"missing", "not_compared"}],
        key=lambda r: (r["status"], r["folder_full_name"], r["display_name"]),
    ):
        matches = "<br>".join(escape_markdown_table(match) for match in row.get("local_matches", []))
        lines.append(
            f"| {row['status']} | {escape_markdown_table(row['canvas_path'])} | {matches} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def normalize_text(value: str) -> str:
    decoded = unquote(value or "")
    normalized = unicodedata.normalize("NFKC", decoded)
    normalized = normalized.replace("\\", "/")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def human_size(size: Any) -> str:
    if size is None or size == "":
        return ""
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return str(size)


def escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
