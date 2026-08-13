"""Canvas timezone normalization for project initialization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Canvas can expose Rails-style ActiveSupport names rather than IANA timezone IDs.
# Keep this mapping deliberately explicit: unknown names are reported, never guessed.
RAILS_TO_IANA = {
    "Alaska": "America/Anchorage",
    "Arizona": "America/Phoenix",
    "Central Time (US & Canada)": "America/Chicago",
    "Eastern Time (US & Canada)": "America/New_York",
    "Hawaii": "Pacific/Honolulu",
    "Mountain Time (US & Canada)": "America/Denver",
    "Pacific Time (US & Canada)": "America/Los_Angeles",
    "UTC": "UTC",
}


def normalize_timezone(value: object) -> str | None:
    """Return an IANA timezone for a Canvas/IANA value, or ``None`` if unknown."""
    if value is None:
        return None
    name = str(value).strip()
    if not name:
        return None
    mapped = RAILS_TO_IANA.get(name, name)
    try:
        ZoneInfo(mapped)
    except ZoneInfoNotFoundError:
        return None
    return mapped


def require_timezone(value: str, *, source: str) -> str:
    """Normalize a timezone or raise an actionable configuration error."""
    normalized = normalize_timezone(value)
    if normalized is None:
        raise SystemExit(f"Unknown timezone in {source}: {value}")
    return normalized


def course_timezone_value(course: Any) -> object | None:
    """Read the timezone fields used by Canvas course objects and mappings."""
    if isinstance(course, Mapping):
        return course.get("time_zone") or course.get("timezone")
    return getattr(course, "time_zone", None) or getattr(course, "timezone", None)
