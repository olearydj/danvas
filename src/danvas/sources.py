"""Local course source discovery for status and sync commands."""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from danvas.assignment_sources import expand_date_only_metadata
from danvas.authored_content import DATE_OR_DATETIME, DATETIME, require_valid_datetimes
from danvas.frontmatter import normalize_canvas_value, parse_frontmatter
from danvas.page_sources import canonicalize_page_html, load_page_source
from danvas.source_layouts import (
    LEGACY_SOURCE_EXCLUDES as DEFAULT_SOURCE_EXCLUDES,  # noqa: F401 - compatibility re-export
)
from danvas.source_layouts import (
    LEGACY_SOURCE_PATTERNS as DEFAULT_SOURCE_PATTERNS,  # noqa: F401 - compatibility re-export
)
from danvas.source_layouts import SOURCE_KINDS, source_options

COMPARABLE_FIELDS = {
    "assignment": ["points_possible", "due_at", "unlock_at", "lock_at", "published"],
    "announcement": ["published", "delayed_post_at"],
    "discussion": ["points_possible", "due_at", "published"],
    "quiz": [],
    "page": ["published", "front_page", "publish_at", "editing_roles"],
}

QUIZ_TITLE_RE = re.compile(r"^quiz title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FRONTMATTER_DELIMITERS = {"---", "+++"}
ASSIGNMENT_SOURCE_MARKER_FIELDS = {
    "allowed_attempts",
    "allowed_extensions",
    "assignment_group",
    "assignment_group_id",
    "assignment_group_name",
    "due_at",
    "due_date",
    "grading_type",
    "group_category_id",
    "lock_at",
    "lock_date",
    "peer_reviews",
    "points_possible",
    "published",
    "submission_types",
    "unlock_at",
    "unlock_date",
}


def scan_sources(
    root: Path,
    source_config: dict[str, Any] | None = None,
    *,
    course_id: int | None = None,
    canvas_origin: str | None = None,
) -> list[dict[str, Any]]:
    records = []
    for kind in SOURCE_KINDS:
        options = source_options(kind, source_config)
        for path in source_paths(root, options["include"], options["exclude"]):
            record = source_record(
                kind,
                path,
                root,
                require_assignment_metadata=options["require_assignment_metadata"],
                course_id=course_id,
                canvas_origin=canvas_origin,
            )
            if record is not None:
                records.append(record)
    return records


def source_paths(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    seen = set()
    paths = []
    for pattern in include:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path.name.lower() == "readme.md":
                continue
            relative = path.relative_to(root).as_posix()
            if relative in seen or is_excluded(relative, exclude):
                continue
            seen.add(relative)
            paths.append(path)
    return paths


def is_excluded(relative_path: str, exclude: list[str]) -> bool:
    name = Path(relative_path).name
    return any(fnmatch(relative_path, pattern) or fnmatch(name, pattern) for pattern in exclude)


def source_record(
    kind: str,
    path: Path,
    root: Path,
    *,
    require_assignment_metadata: bool = False,
    course_id: int | None = None,
    canvas_origin: str | None = None,
) -> dict[str, Any] | None:
    record: dict[str, Any] = {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "title": "",
        "metadata": {},
        "source_metadata": {},
        "artifacts": {},
        "error": "",
    }
    try:
        text = path.read_text(encoding="utf-8-sig")
        if kind == "quiz":
            record["title"] = quiz_source_title(text)
            record["artifacts"]["qti_zip"] = find_qti_zip(path, root)
        elif kind == "page":
            local = load_page_source(
                path,
                course_id=course_id,
                canvas_origin=canvas_origin,
            )
            canonical = canonicalize_page_html(
                local.html,
                course_id=course_id,
                canvas_origin=canvas_origin,
            )
            record["title"] = str(local.metadata["title"])
            record["metadata"] = comparable_metadata(kind, local.metadata)
            record["source_metadata"] = normalize_canvas_value(local.metadata)
            record["artifacts"].update(
                {
                    "body_sha256": canonical["body_sha256"],
                    "body_hash_status": canonical["body_hash_status"],
                    "anchors": local.anchors,
                    "unresolved_assets": local.unresolved_assets,
                }
            )
        else:
            if (
                kind == "assignment"
                and require_assignment_metadata
                and not starts_with_frontmatter(text)
            ):
                return None
            metadata, _body = parse_frontmatter(
                text, path, kind.capitalize()
            )
            if kind == "assignment":
                expand_date_only_metadata(metadata, path)
            validate_source_datetimes(kind, metadata)
            if (
                kind == "assignment"
                and require_assignment_metadata
                and not has_assignment_metadata(metadata)
            ):
                return None
            record["title"] = str(metadata.get("title") or metadata.get("name") or "")
            record["metadata"] = comparable_metadata(kind, metadata)
            record["source_metadata"] = normalize_canvas_value(metadata)
    except SystemExit as exc:
        record["error"] = str(exc)
    except OSError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    if not record["error"] and not record["title"]:
        record["error"] = "No title found in source."
    return record


def starts_with_frontmatter(text: str) -> bool:
    first_line = next(iter(text.splitlines()), "").strip()
    return first_line in FRONTMATTER_DELIMITERS


def has_assignment_metadata(metadata: dict[str, Any]) -> bool:
    return bool(set(metadata) & ASSIGNMENT_SOURCE_MARKER_FIELDS)


def comparable_metadata(kind: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        field: normalize_canvas_value(metadata[field])
        for field in COMPARABLE_FIELDS.get(kind, [])
        if field in metadata
    }


def validate_source_datetimes(kind: str, metadata: dict[str, Any]) -> None:
    policies = {
        field: DATETIME
        for field in ("due_at", "unlock_at", "lock_at", "delayed_post_at")
    }
    if kind == "assignment":
        policies.update(
            {
                "due_date": DATE_OR_DATETIME,
                "unlock_date": DATE_OR_DATETIME,
                "lock_date": DATE_OR_DATETIME,
            }
        )
    if kind == "page":
        policies["publish_at"] = DATE_OR_DATETIME
    require_valid_datetimes(metadata, policies, source_type=kind.capitalize())


def quiz_source_title(text: str) -> str:
    match = QUIZ_TITLE_RE.search(text)
    return match.group(1) if match else ""


def find_qti_zip(path: Path, root: Path) -> str:
    candidate = path.with_suffix(".zip")
    return candidate.relative_to(root).as_posix() if candidate.is_file() else ""
