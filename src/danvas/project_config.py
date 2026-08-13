"""Dependency-light access to project-local danvas configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONFIG_DIR_NAME = ".danvas"
CONFIG_FILE_NAME = "config.toml"
COURSE_SNAPSHOT_NAME = "course.json"


def project_dir(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / CONFIG_DIR_NAME


def config_path(root: Path | None = None) -> Path:
    return project_dir(root) / CONFIG_FILE_NAME


def course_snapshot_path(root: Path | None = None) -> Path:
    return project_dir(root) / COURSE_SNAPSHOT_NAME


def find_config_dir(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        path = candidate / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if path.is_file():
            return path.parent
    return None


def load_config_dir(config_dir: Path | None) -> dict[str, Any]:
    if config_dir is None:
        return {}
    path = config_dir / CONFIG_FILE_NAME
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"danvas config must be a TOML table: {path}")
    return data


def load_project_config(start: Path | None = None) -> dict[str, Any]:
    return load_config_dir(find_config_dir(start))


def configured_course_id(config_dir: Path | None) -> int | None:
    course_id = (load_config_dir(config_dir).get("canvas") or {}).get("course_id")
    if course_id is None:
        return None
    try:
        return int(course_id)
    except (TypeError, ValueError):
        return None


def configured_timezone(config_dir: Path | None) -> str | None:
    timezone = (load_config_dir(config_dir).get("canvas") or {}).get("timezone")
    return str(timezone) if timezone else None


def resolve_course_id(explicit: int | None, *, start: Path | None = None) -> int:
    if explicit is not None:
        return explicit
    course_id = (load_project_config(start).get("canvas") or {}).get("course_id")
    if course_id is None:
        raise SystemExit(
            "Canvas course ID required. Pass --course-id or run `danvas init COURSE_ID` "
            "from the course project."
        )
    return int(course_id)


def resolve_api_url(explicit: str | None, *, start: Path | None = None) -> str | None:
    if explicit:
        return explicit
    value = (load_project_config(start).get("canvas") or {}).get("api_url")
    return str(value) if value else None


def resolve_course_timezone(start: Path | None = None) -> ZoneInfo:
    timezone = (load_project_config(start).get("canvas") or {}).get("timezone")
    if not timezone:
        raise SystemExit(
            "Date-only assignment metadata requires [canvas].timezone in .danvas/config.toml. "
            "Run `danvas init` or use explicit *_at datetime fields."
        )
    try:
        return ZoneInfo(str(timezone))
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"Unknown course timezone in .danvas/config.toml: {timezone}") from exc
