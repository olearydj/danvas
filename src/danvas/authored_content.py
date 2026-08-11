"""Shared comparison primitives for authored Canvas content."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any


def datetime_values_match(canvas_value: Any, local_value: Any) -> bool:
    """Compare Canvas/local ISO values by date or absolute instant when possible."""
    canvas_text = str(canvas_value or "").strip()
    local_text = str(local_value or "").strip()
    if not canvas_text or not local_text:
        return canvas_text == local_text

    canvas_date_only = re.fullmatch(r"\d{4}-\d{2}-\d{2}", canvas_text)
    local_date_only = re.fullmatch(r"\d{4}-\d{2}-\d{2}", local_text)
    try:
        canvas_datetime = datetime.fromisoformat(canvas_text.replace("Z", "+00:00"))
        local_datetime = datetime.fromisoformat(local_text.replace("Z", "+00:00"))
    except ValueError:
        return canvas_text == local_text

    if canvas_date_only or local_date_only:
        return canvas_datetime.date() == local_datetime.date()
    if canvas_datetime.tzinfo is None or local_datetime.tzinfo is None:
        return canvas_datetime == local_datetime
    return canvas_datetime.astimezone(UTC) == local_datetime.astimezone(UTC)
