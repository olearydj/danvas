"""Project-local danvas configuration and Canvas metadata snapshots."""

from __future__ import annotations

import datetime as dt
import json
import tomllib
from pathlib import Path
from typing import Any

from danvas.auth import canvas_from_args
from danvas.utils import canvas_object_to_dict, html_to_text

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


def load_project_config(start: Path | None = None) -> dict[str, Any]:
    config_dir = find_config_dir(start)
    if not config_dir:
        return {}
    data = tomllib.loads((config_dir / CONFIG_FILE_NAME).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"danvas config must be a TOML table: {config_dir / CONFIG_FILE_NAME}")
    return data


def resolve_course_id(explicit: int | None, *, start: Path | None = None) -> int:
    if explicit is not None:
        return explicit
    config = load_project_config(start)
    course_id = (config.get("canvas") or {}).get("course_id")
    if course_id is None:
        raise SystemExit(
            "Canvas course ID required. Pass --course-id or run `danvas init COURSE_ID` "
            "from the course project."
        )
    return int(course_id)


def resolve_api_url(explicit: str | None, *, start: Path | None = None) -> str | None:
    if explicit:
        return explicit
    config = load_project_config(start)
    value = (config.get("canvas") or {}).get("api_url")
    return str(value) if value else None


def resolve_assignment_group_id(
    name: str, *, explicit_id: int | None = None, start: Path | None = None
) -> int:
    if explicit_id is not None:
        raise SystemExit("Use either assignment_group_id or assignment_group_name, not both.")
    config_dir = find_config_dir(start)
    config = load_project_config(start)
    groups = config.get("assignment_groups") or {}
    if name in groups:
        return int(groups[name])
    if config_dir:
        snapshot_path = config_dir / COURSE_SNAPSHOT_NAME
        if snapshot_path.is_file():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            matches = [
                group
                for group in snapshot.get("assignment_groups", [])
                if str(group.get("name") or "") == name
            ]
            if len(matches) == 1:
                return int(matches[0]["id"])
            if len(matches) > 1:
                raise SystemExit(f"Assignment group name is ambiguous in course snapshot: {name}")
    raise SystemExit(
        f"Unknown assignment group name: {name}. Run `danvas refresh` or use assignment_group_id."
    )


def command_init(args: Any) -> None:
    root = Path(args.project_root).resolve()
    config = config_path(root)
    snapshot = course_snapshot_path(root)
    if config.exists() and not args.force:
        raise SystemExit(f"Config already exists: {config}. Use --force to replace it.")
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    payload = build_course_snapshot(course)
    write_project_config(
        config,
        course_snapshot=payload,
        api_url=args.api_url,
        timezone=args.timezone,
    )
    write_course_snapshot(snapshot, payload)
    maybe_ignore_course_snapshot(root)
    print(f"Wrote {config}")
    print(f"Wrote {snapshot}")


def command_refresh(args: Any) -> None:
    root = Path(args.project_root).resolve()
    args.course_id = resolve_course_id(args.course_id, start=root)
    canvas = canvas_from_args(args)
    course = canvas.get_course(args.course_id)
    payload = build_course_snapshot(course)
    snapshot = course_snapshot_path(root)
    write_course_snapshot(snapshot, payload)
    print(f"Wrote {snapshot}")


def build_course_snapshot(course: Any) -> dict[str, Any]:
    course_payload = canvas_object_to_dict(course)
    for key in ("id", "name", "course_code", "start_at", "end_at"):
        value = getattr(course, key, None)
        if value is not None and course_payload.get(key) is None:
            course_payload[key] = value
    groups = [
        canvas_object_to_dict(group)
        for group in sorted(
            course.get_assignment_groups(), key=lambda group: str(getattr(group, "name", ""))
        )
    ]
    groups_by_id = {int(group["id"]): group for group in groups if group.get("id") is not None}
    assignments = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        group = groups_by_id.get(int(getattr(assignment, "assignment_group_id", 0) or 0), {})
        assignments.append(
            {
                "id": getattr(assignment, "id", ""),
                "name": getattr(assignment, "name", ""),
                "assignment_group_id": getattr(assignment, "assignment_group_id", ""),
                "assignment_group_name": group.get("name", ""),
                "points_possible": getattr(assignment, "points_possible", ""),
                "due_at": getattr(assignment, "due_at", ""),
                "unlock_at": getattr(assignment, "unlock_at", ""),
                "lock_at": getattr(assignment, "lock_at", ""),
                "published": getattr(assignment, "published", ""),
                "html_url": getattr(assignment, "html_url", ""),
                "submission_types": getattr(assignment, "submission_types", []) or [],
                "description_text": html_to_text(getattr(assignment, "description", "")),
            }
        )
    assignments.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    folders = [
        canvas_object_to_dict(folder)
        for folder in sorted(
            course.get_folders(), key=lambda folder: str(getattr(folder, "full_name", ""))
        )
    ]
    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "course": course_payload,
        "assignment_groups": groups,
        "assignments": assignments,
        "folders": folders,
    }


def write_course_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_project_config(
    path: Path, *, course_snapshot: dict[str, Any], api_url: str, timezone: str
) -> None:
    course = course_snapshot.get("course") or {}
    course_id = course.get("id")
    if course_id is None:
        raise SystemExit("Course snapshot is missing course.id; cannot write danvas config.")
    lines = [
        "# danvas project configuration",
        "# Generated by `danvas init`; edit stable project defaults here.",
        "",
        "[canvas]",
        f"api_url = {toml_string(api_url)}",
        f"course_id = {int(course_id)}",
        f"course_name = {toml_string(str(course.get('name') or ''))}",
        f"timezone = {toml_string(timezone)}",
        "",
        "[assignment_groups]",
    ]
    for group in course_snapshot.get("assignment_groups", []):
        name = str(group.get("name") or "")
        if name:
            lines.append(f"{toml_key(name)} = {int(group['id'])}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def maybe_ignore_course_snapshot(root: Path) -> None:
    if not (root / ".git").exists():
        return
    gitignore = root / ".gitignore"
    ignore_line = f"{CONFIG_DIR_NAME}/{COURSE_SNAPSHOT_NAME}"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ignore_line in existing.splitlines():
        return
    with gitignore.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"{ignore_line}\n")


def toml_key(value: str) -> str:
    if value.isascii() and value.replace("_", "").replace("-", "").isalnum():
        return value
    return toml_string(value)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
