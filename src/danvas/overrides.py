"""Assignment-override snapshot, export, and local comparison helpers."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from danvas.utils import normalize_json


def value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def list_value(obj: Any, key: str) -> list[Any]:
    raw = value(obj, key, []) or []
    return list(raw) if isinstance(raw, (list, tuple)) else []


def override_id(row: Any) -> int | None:
    raw = value(row, "id", value(row, "assignment_override_id"))
    return int(raw) if raw not in {None, ""} else None


def assignee_ids(row: Any) -> list[int]:
    ids = value(row, "student_ids", []) or []
    return sorted(int(item) for item in ids if item not in {None, ""})


def assignee_count(row: Any) -> int:
    ids = assignee_ids(row)
    if ids:
        return len(ids)
    raw = value(row, "assignee_count", value(row, "student_count"))
    if raw not in {None, ""}:
        return int(raw)
    return 0


def window_record(row: Any) -> dict[str, Any]:
    return {
        "id": override_id(row),
        "title": str(value(row, "title", "") or ""),
        "base": bool(value(row, "base", False)),
        "due_at": value(row, "due_at"),
        "unlock_at": value(row, "unlock_at"),
        "lock_at": value(row, "lock_at"),
        "assignee_count": assignee_count(row),
    }


def redacted_assignment_overrides(assignment: Any) -> dict[str, Any]:
    all_dates = [window_record(row) for row in list_value(assignment, "all_dates")]
    overrides = list_value(assignment, "overrides")
    if not all_dates and overrides:
        all_dates = [window_record(row) for row in overrides]
    has_overrides = bool(overrides or any(not row["base"] for row in all_dates))
    return {
        "has_overrides": has_overrides,
        "all_dates": normalize_json(all_dates),
        "override_summaries": [
            {
                "id": override_id(row),
                "title": str(value(row, "title", "") or ""),
                "assignee_count": assignee_count(row),
            }
            for row in overrides
        ],
    }


def private_assignment_overrides(assignment: Any, *, source: str = "") -> dict[str, Any]:
    redacted = redacted_assignment_overrides(assignment)
    all_dates = list_value(assignment, "all_dates")
    overrides = list_value(assignment, "overrides")
    base = next((window_record(row) for row in all_dates if bool(value(row, "base", False))), None)
    if base is None:
        base = {
            "due_at": value(assignment, "due_at"),
            "unlock_at": value(assignment, "unlock_at"),
            "lock_at": value(assignment, "lock_at"),
        }
    return {
        "private_student_data": True,
        "assignment_id": int(value(assignment, "id", 0) or 0),
        "source": source,
        "base": base,
        "overrides": [private_override_record(row) for row in overrides],
        "has_overrides": redacted["has_overrides"],
    }


def private_override_record(row: Any) -> dict[str, Any]:
    record = window_record(row)
    record["assignees"] = {
        "canvas_user_ids": assignee_ids(row),
        "course_section_id": value(row, "course_section_id"),
        "group_id": value(row, "group_id"),
    }
    return record


def base_window(row: dict[str, Any]) -> dict[str, Any] | None:
    windows = row.get("all_dates") or []
    return next(
        (
            window
            for window in windows
            if isinstance(window, dict)
            and (window.get("base") or str(window.get("title") or "").lower() == "everyone else")
        ),
        None,
    )


def assignment_base_compare_row(row: dict[str, Any]) -> dict[str, Any]:
    comparable = dict(row)
    base = base_window(row)
    if base:
        for field in ("due_at", "unlock_at", "lock_at"):
            comparable[field] = base.get(field)
    return comparable


def load_local_override_file(root: Path, reference: str) -> tuple[dict[str, Any] | None, str]:
    path = (root / reference).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None, "override reference must stay inside the course project"
    if not path.is_file():
        return None, f"override reference not found: {reference}"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        return None, f"invalid override reference {reference}: {type(exc).__name__}"
    except yaml.YAMLError:
        return None, f"invalid override reference {reference}: YAML parse error"
    if not isinstance(payload, dict):
        return None, f"override reference must contain a mapping: {reference}"
    return payload, ""


def compare_local_overrides(
    canvas_row: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, list[str]]:
    assignment_id = payload.get("assignment_id")
    if assignment_id not in {None, ""} and int(assignment_id) != int(canvas_row.get("id") or 0):
        return "override mismatch", ["override reference assignment_id does not match Canvas"]
    local_rows = payload.get("overrides") or []
    if not isinstance(local_rows, list):
        return "override mismatch", ["local overrides must be a list"]
    canvas_rows = {
        int(row["id"]): row
        for row in canvas_row.get("all_dates") or []
        if isinstance(row, dict) and row.get("id") not in {None, ""} and not row.get("base")
    }
    local_by_id = {
        int(row.get("canvas_override_id", row.get("id"))): row
        for row in local_rows
        if isinstance(row, dict) and row.get("canvas_override_id", row.get("id")) not in {None, ""}
    }
    details: list[str] = []
    if canvas_rows.keys() - local_by_id.keys():
        details.append(f"Canvas-only overrides: {len(canvas_rows.keys() - local_by_id.keys())}")
    if local_by_id.keys() - canvas_rows.keys():
        details.append(f"local-only overrides: {len(local_by_id.keys() - canvas_rows.keys())}")
    for key in canvas_rows.keys() & local_by_id.keys():
        canvas = canvas_rows[key]
        local = local_by_id[key]
        for field in ("title", "due_at", "unlock_at", "lock_at"):
            if normalize_scalar(local.get(field)) != normalize_scalar(canvas.get(field)):
                details.append(f"override {key} {field} mismatch")
        local_count = len((local.get("assignees") or {}).get("canvas_user_ids") or [])
        if local_count and local_count != int(canvas.get("assignee_count") or 0):
            details.append(f"override {key} assignee count mismatch")
    return ("override exact", []) if not details else ("override mismatch", details)


def normalize_scalar(value: Any) -> str:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.astimezone(dt.UTC).isoformat()
