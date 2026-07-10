"""Project source-map helpers for Canvas round-trip provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from danvas import __version__
from danvas.reports import course_id_for_config, find_config_dir, now_for_config
from danvas.utils import normalize_json, write_json_atomic

SOURCE_MAP_SCHEMA_VERSION = 1
SOURCE_MAP_FILENAME = "source-map.json"


def source_map_path(project_root: Path | None = None) -> Path:
    config_dir = find_config_dir(project_root)
    if config_dir:
        return config_dir / SOURCE_MAP_FILENAME
    root = (project_root or Path.cwd()).resolve()
    if root.is_file():
        root = root.parent
    return root / ".danvas" / SOURCE_MAP_FILENAME


def source_map_project_root(project_root: Path | None = None) -> Path:
    config_dir = find_config_dir(project_root)
    if config_dir:
        return config_dir.parent
    root = (project_root or Path.cwd()).resolve()
    return root.parent if root.is_file() else root


def source_path_key(source: Path, project_root: Path | None = None) -> str:
    root = source_map_project_root(project_root)
    resolved = source.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def load_source_map(project_root: Path | None = None) -> dict[str, Any]:
    path = source_map_path(project_root)
    if not path.is_file():
        return empty_source_map(project_root)
    try:
        payload = normalize_json_object(path)
    except ValueError as exc:
        raise SystemExit(f"Invalid source map {path}: {exc}") from exc
    if payload.get("schema_version") != SOURCE_MAP_SCHEMA_VERSION:
        raise SystemExit(
            f"Unsupported source map schema_version in {path}: {payload.get('schema_version')!r}"
        )
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise SystemExit(f"Invalid source map {path}: sources must be a list.")
    return payload


def normalize_json_object(path: Path) -> dict[str, Any]:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ValueError("root value must be an object")
    return payload


def empty_source_map(project_root: Path | None = None) -> dict[str, Any]:
    config_dir = find_config_dir(project_root)
    return {
        "schema_version": SOURCE_MAP_SCHEMA_VERSION,
        "course_id": course_id_for_config(config_dir),
        "generated_at": now_for_config(config_dir).isoformat(timespec="seconds"),
        "sources": [],
    }


def find_source_entry(payload: dict[str, Any], *, kind: str, path: str) -> dict[str, Any] | None:
    for entry in payload.get("sources") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") == kind and entry.get("path") == path:
            return entry
    return None


def source_entry_canvas_id(entry: dict[str, Any] | None) -> int | None:
    if not entry:
        return None
    canvas = entry.get("canvas")
    if not isinstance(canvas, dict):
        return None
    raw_id = canvas.get("id")
    if raw_id is None or str(raw_id).strip() == "":
        return None
    return int(raw_id)


def resolve_source_canvas_id(
    *,
    kind: str,
    source: Path,
    explicit_id: int | None,
    frontmatter_id: int | None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    payload = load_source_map(project_root)
    path_key = source_path_key(source, project_root)
    entry = find_source_entry(payload, kind=kind, path=path_key)
    map_id = source_entry_canvas_id(entry)
    if explicit_id is not None:
        return {
            "id": int(explicit_id),
            "source": "cli",
            "path": path_key,
            "source_map_entry": entry,
        }
    if frontmatter_id is not None and map_id is not None and int(frontmatter_id) != map_id:
        raise SystemExit(
            f"Front matter ID {frontmatter_id} conflicts with source-map ID {map_id} "
            f"for {path_key}. Pass an explicit CLI ID to resolve the conflict."
        )
    if frontmatter_id is not None:
        return {
            "id": int(frontmatter_id),
            "source": "frontmatter",
            "path": path_key,
            "source_map_entry": entry,
        }
    if map_id is not None:
        return {
            "id": map_id,
            "source": "source_map",
            "path": path_key,
            "source_map_entry": entry,
        }
    return {"id": None, "source": "none", "path": path_key, "source_map_entry": entry}


def write_source_map_entry(
    *,
    kind: str,
    source: Path,
    course_id: int | None,
    canvas: dict[str, Any],
    command: str,
    fields: dict[str, Any],
    body_sha256: str | None = None,
    project_root: Path | None = None,
) -> Path:
    path = source_map_path(project_root)
    payload = load_source_map(project_root)
    config_dir = find_config_dir(project_root)
    path_key = source_path_key(source, project_root)
    generated_at = now_for_config(config_dir).isoformat(timespec="seconds")
    payload["schema_version"] = SOURCE_MAP_SCHEMA_VERSION
    payload["course_id"] = course_id if course_id is not None else payload.get("course_id")
    payload["generated_at"] = generated_at
    entry = {
        "kind": kind,
        "path": path_key,
        "canvas": normalize_json(canvas),
        "last_posted": {
            "command": command,
            "posted_at": generated_at,
            "danvas_version": __version__,
            "fields": normalize_json(fields),
        },
    }
    if body_sha256:
        entry["last_posted"]["body_sha256"] = body_sha256
    sources = [
        item
        for item in payload.get("sources", [])
        if not (
            isinstance(item, dict) and item.get("kind") == kind and item.get("path") == path_key
        )
    ]
    sources.append(entry)
    sources.sort(key=lambda item: (str(item.get("kind") or ""), str(item.get("path") or "")))
    payload["sources"] = sources
    write_json_atomic(path, payload)
    return path
