"""Shared comparison and datetime primitives for authored Canvas content."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

ComparisonPolicy = Literal[
    "scalar",
    "boolean",
    "exact",
    "normalized-text",
    "datetime",
    "date-or-datetime",
    "unordered-sequence",
    "allowed-extensions",
]

SCALAR: ComparisonPolicy = "scalar"
BOOLEAN: ComparisonPolicy = "boolean"
EXACT: ComparisonPolicy = "exact"
NORMALIZED_TEXT: ComparisonPolicy = "normalized-text"
DATETIME: ComparisonPolicy = "datetime"
DATE_OR_DATETIME: ComparisonPolicy = "date-or-datetime"
UNORDERED_SEQUENCE: ComparisonPolicy = "unordered-sequence"
ALLOWED_EXTENSIONS: ComparisonPolicy = "allowed-extensions"

DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DatetimeValidationIssue:
    """A source-load-safe datetime problem without command-specific wording."""

    field: str
    reason: Literal["invalid", "date_only", "offset_required"]

    def message(self, source_type: str) -> str:
        prefix = f"{source_type} {self.field}"
        if self.reason == "invalid":
            return f"{prefix} must be a valid ISO 8601 timestamp."
        if self.reason == "date_only":
            return (
                f"{prefix} requires an ISO 8601 timestamp with Z or an explicit UTC offset; "
                "date-only values are not accepted by Canvas."
            )
        return (
            f"{prefix} requires Z or an explicit UTC offset; "
            "offset-free timestamps are ambiguous."
        )


def normalized_text(value: str) -> str:
    """Collapse whitespace for authored scalar and rendered-text comparison."""
    return " ".join(value.split())


def comparable_value(  # noqa: C901 - docs/backlog.md: Sprint 17 legacy hotspot.
    value: Any, policy: ComparisonPolicy = SCALAR
) -> Any:
    """Return a stable evidence value under an explicit field policy."""
    if policy == BOOLEAN:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = normalized_text(value).casefold()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        return value
    if policy == EXACT:
        return value
    if policy == NORMALIZED_TEXT:
        return value if value is None else normalized_text(str(value))
    if policy == ALLOWED_EXTENSIONS:
        if value is None or value == "":
            return []
        values = value.split(",") if isinstance(value, str) else value
        if isinstance(values, (list, tuple, set)):
            return sorted(
                {
                    str(item).strip().removeprefix(".").casefold()
                    for item in values
                    if str(item).strip()
                }
            )
    if policy == UNORDERED_SEQUENCE:
        if value is None or value == "":
            return []
        values = value.split(",") if isinstance(value, str) else value
        if isinstance(values, (list, tuple, set)):
            return sorted(str(item).strip() for item in values if str(item).strip())
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [comparable_value(item) for item in value]
    text = normalized_text(str(value)).replace("+00:00", "Z")
    if text.casefold() == "true":
        return True
    if text.casefold() == "false":
        return False
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def comparison_check(
    field: str,
    local_value: Any,
    canvas_value: Any,
    *,
    policy: ComparisonPolicy = SCALAR,
    project: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Build the standard authored comparison row."""
    local = comparable_value(local_value, policy)
    canvas = comparable_value(canvas_value, policy)
    if policy in {DATETIME, DATE_OR_DATETIME}:
        matches = datetime_values_match(canvas_value, local_value)
    else:
        matches = local == canvas
    projector = project or (lambda value: value)
    return {
        "field": field,
        "status": "matches" if matches else "mismatch",
        "matches": matches,
        "local": projector(local),
        "canvas": projector(canvas),
    }


def comparison_checks(
    local: Mapping[str, Any],
    canvas: Mapping[str, Any],
    fields: Iterable[str],
    *,
    policies: Mapping[str, ComparisonPolicy] | None = None,
    project: Callable[[Any], Any] | None = None,
) -> list[dict[str, Any]]:
    """Build standard rows for a bounded set of explicitly supported fields."""
    field_policies = policies or {}
    return [
        comparison_check(
            field,
            local.get(field),
            canvas.get(field),
            policy=field_policies.get(field, SCALAR),
            project=project,
        )
        for field in sorted(fields)
    ]


def first_value(obj: Any, payload: Mapping[str, Any], *names: str) -> Any:
    """Select the first nonblank Canvas object or raw-payload value."""
    for name in names:
        if obj is not None:
            value = getattr(obj, name, None)
            if value is not None and value != "":
                return value
        value = payload.get(name)
        if value is not None and value != "":
            return value
    return ""


def datetime_validation_issue(
    field: str,
    value: Any,
    *,
    allow_date_only: bool = False,
) -> DatetimeValidationIssue | None:
    """Return a structured issue for invalid or ambiguous authored datetimes."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return None if allow_date_only else DatetimeValidationIssue(field, "date_only")
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value).strip()
    if DATE_ONLY_RE.fullmatch(raw):
        return None if allow_date_only else DatetimeValidationIssue(field, "date_only")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return DatetimeValidationIssue(field, "invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return DatetimeValidationIssue(field, "offset_required")
    return None


def require_valid_datetimes(
    metadata: Mapping[str, Any],
    policies: Mapping[str, ComparisonPolicy],
    *,
    source_type: str,
) -> None:
    """Reject the first declared invalid authored datetime before Canvas access."""
    for field in sorted(set(metadata) & set(policies)):
        policy = policies[field]
        if policy not in {DATETIME, DATE_OR_DATETIME}:
            continue
        issue = datetime_validation_issue(
            field,
            metadata.get(field),
            allow_date_only=policy == DATE_OR_DATETIME,
        )
        if issue:
            raise SystemExit(issue.message(source_type))


def datetime_values_match(canvas_value: Any, local_value: Any) -> bool:
    """Compare Canvas/local ISO values by date or absolute instant when possible."""
    canvas_text = str(canvas_value or "").strip()
    local_text = str(local_value or "").strip()
    if not canvas_text or not local_text:
        return canvas_text == local_text

    canvas_date_only = DATE_ONLY_RE.fullmatch(canvas_text)
    local_date_only = DATE_ONLY_RE.fullmatch(local_text)
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
