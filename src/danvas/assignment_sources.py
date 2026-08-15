"""Dependency-light normalization for authored assignment sources."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from danvas.project_config import resolve_course_timezone

DATE_ONLY_ALIASES = {
    "due_date": ("due_at", time(23, 59)),
    "unlock_date": ("unlock_at", time(0, 0)),
    "lock_date": ("lock_at", time(23, 59)),
}
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def expand_date_only_metadata(metadata: dict[str, Any], source: Path) -> None:
    for alias, (target, default_time) in DATE_ONLY_ALIASES.items():
        if alias not in metadata:
            continue
        if target in metadata and not is_blank_metadata_value(metadata.get(target)):
            raise SystemExit(f"Use either {alias} or {target}, not both.")
        value = metadata.pop(alias)
        if is_blank_metadata_value(value):
            continue
        timezone = resolve_course_timezone(source)
        day = parse_date_only_value(alias, value)
        metadata[target] = datetime.combine(day, default_time, tzinfo=timezone).isoformat(
            timespec="seconds"
        )


def parse_date_only_value(field: str, value: Any) -> date:
    if isinstance(value, datetime):
        raise SystemExit(f"{field} must be a date-only value in YYYY-MM-DD format.")
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not DATE_ONLY_RE.match(text):
        raise SystemExit(f"{field} must be a date-only value in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"{field} must be a valid date in YYYY-MM-DD format.") from exc


def is_blank_metadata_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
