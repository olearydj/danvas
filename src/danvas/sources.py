"""Local course source discovery for status and sync commands."""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from danvas.frontmatter import normalize_canvas_value, parse_frontmatter

SOURCE_KINDS = ("announcement", "discussion", "quiz", "assignment", "page")
SOURCE_CONFIG_KEYS = {
    "announcement": "announcements",
    "discussion": "discussions",
    "quiz": "quizzes",
    "assignment": "assignments",
    "page": "pages",
}
DEFAULT_SOURCE_PATTERNS = {
    "announcement": ["content/announcements/*.md"],
    "discussion": ["content/discussions/*.md"],
    "quiz": ["content/quizzes/chap*.md"],
    "assignment": ["content/cases/*-assignment.md"],
    "page": ["content/pages/*.md", "content/pages/*.html"],
}

DEFAULT_SOURCE_EXCLUDES = {"page": ["content/pages/*-preview.html"]}

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
    "grading_type",
    "group_category_id",
    "lock_at",
    "peer_reviews",
    "points_possible",
    "published",
    "submission_types",
    "unlock_at",
}


def scan_sources(
    root: Path,
    source_config: dict[str, Any] | None = None,
    *,
    course_id: int | None = None,
    canvas_origin: str | None = None,
) -> list[dict[str, Any]]:
    source_config = source_config or {}
    if not isinstance(source_config, dict):
        raise SystemExit("[sources] must be a TOML table.")
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


def source_options(kind: str, source_config: dict[str, Any]) -> dict[str, Any]:
    config_key = SOURCE_CONFIG_KEYS[kind]
    raw_options = source_config.get(config_key) or source_config.get(kind) or {}
    if not isinstance(raw_options, dict):
        raise SystemExit(f"[sources.{config_key}] must be a TOML table.")

    custom_include = "include" in raw_options or "includes" in raw_options
    include = patterns_from_config(
        raw_options.get("include", raw_options.get("includes")),
        default=DEFAULT_SOURCE_PATTERNS[kind],
        label=f"sources.{config_key}.include",
    )
    exclude = patterns_from_config(
        raw_options.get("exclude", raw_options.get("excludes")),
        default=DEFAULT_SOURCE_EXCLUDES.get(kind, []),
        label=f"sources.{config_key}.exclude",
    )
    require_assignment_metadata = False
    if kind == "assignment":
        require_assignment_metadata = bool_from_config(
            raw_options.get("require_assignment_metadata"),
            default=custom_include,
            label=f"sources.{config_key}.require_assignment_metadata",
        )
    return {
        "include": include,
        "exclude": exclude,
        "require_assignment_metadata": require_assignment_metadata,
    }


def patterns_from_config(value: Any, *, default: list[str], label: str) -> list[str]:
    patterns: list[str]
    if value is None:
        return list(default)
    if isinstance(value, str):
        patterns = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        patterns = [str(item) for item in value]
    else:
        raise SystemExit(f"{label} must be a string or list of strings.")
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise SystemExit(f"{label} patterns must be relative paths inside the course root.")
    return patterns


def bool_from_config(value: Any, *, default: bool, label: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SystemExit(f"{label} must be true or false.")
    return value


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
            from danvas.pages import canonicalize_page_html, load_page_source

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


def quiz_source_title(text: str) -> str:
    match = QUIZ_TITLE_RE.search(text)
    return match.group(1) if match else ""


def find_qti_zip(path: Path, root: Path) -> str:
    candidate = path.with_suffix(".zip")
    return candidate.relative_to(root).as_posix() if candidate.is_file() else ""
