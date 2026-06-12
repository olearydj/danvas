"""Local course source discovery for status and sync commands."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from danvas.frontmatter import normalize_canvas_value, parse_frontmatter

SOURCE_CONVENTIONS = [
    ("announcement", "content/announcements", "*.md"),
    ("discussion", "content/discussions", "*.md"),
    ("quiz", "content/quizzes", "chap*.md"),
    ("assignment", "content/cases", "*-assignment.md"),
]

COMPARABLE_FIELDS = {
    "assignment": ["points_possible", "due_at", "unlock_at", "lock_at", "published"],
    "announcement": ["published", "delayed_post_at"],
    "discussion": ["points_possible", "due_at", "published"],
    "quiz": [],
}

QUIZ_TITLE_RE = re.compile(r"^quiz title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def scan_sources(root: Path) -> list[dict[str, Any]]:
    records = []
    for kind, directory, pattern in SOURCE_CONVENTIONS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob(pattern)):
            if path.is_file():
                records.append(source_record(kind, path, root))
    return records


def source_record(kind: str, path: Path, root: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "title": "",
        "metadata": {},
        "artifacts": {},
        "error": "",
    }
    try:
        if kind == "quiz":
            record["title"] = quiz_source_title(path)
            record["artifacts"]["qti_zip"] = find_qti_zip(path, root)
        else:
            metadata, _body = parse_frontmatter(
                path.read_text(encoding="utf-8-sig"), path, kind.capitalize()
            )
            record["title"] = str(metadata.get("title") or metadata.get("name") or "")
            record["metadata"] = comparable_metadata(kind, metadata)
    except SystemExit as exc:
        record["error"] = str(exc)
    except OSError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    if not record["error"] and not record["title"]:
        record["error"] = "No title found in source."
    return record


def comparable_metadata(kind: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        field: normalize_canvas_value(metadata[field])
        for field in COMPARABLE_FIELDS.get(kind, [])
        if field in metadata
    }


def quiz_source_title(path: Path) -> str:
    match = QUIZ_TITLE_RE.search(path.read_text(encoding="utf-8-sig"))
    return match.group(1) if match else ""


def find_qti_zip(path: Path, root: Path) -> str:
    candidate = path.with_suffix(".zip")
    return candidate.relative_to(root).as_posix() if candidate.is_file() else ""
