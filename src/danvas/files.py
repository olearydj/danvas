"""Canvas course file inventory operations."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from danvas.auth import canvas_from_args
from danvas.utils import canvas_object_to_dict, write_rows

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


def command_files_inventory(args: Any) -> None:
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    output_dir = Path(args.output_dir)
    local_root = Path(args.local_root).resolve() if args.local_root else None

    inventory = build_file_inventory(course, local_root=local_root)
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

    statuses = Counter(row["status"] for row in inventory["comparison"])
    print(f"Wrote {inventory_json}")
    print(f"Wrote {inventory_csv}")
    print(f"Wrote {report_md}")
    print(json.dumps(dict(sorted(statuses.items())), indent=2, sort_keys=True))


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
