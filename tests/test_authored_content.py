from __future__ import annotations

from datetime import date, datetime

import pytest

from danvas.authored_content import (
    ALLOWED_EXTENSIONS,
    BOOLEAN,
    DATE_OR_DATETIME,
    DATETIME,
    EXACT,
    NORMALIZED_TEXT,
    UNORDERED_SEQUENCE,
    comparable_value,
    comparison_check,
    datetime_validation_issue,
    first_value,
    require_valid_datetimes,
)


def test_scalar_and_sequence_policies_are_explicit() -> None:
    assert comparable_value("  10.0 ") == 10
    assert comparable_value(" TRUE ") is True
    assert comparable_value(["b", "a"]) == ["b", "a"]
    assert comparable_value(["b", "a"], UNORDERED_SEQUENCE) == ["a", "b"]
    assert comparable_value([".PDF", "docx", "pdf"], ALLOWED_EXTENSIONS) == [
        "docx",
        "pdf",
    ]


@pytest.mark.parametrize(
    ("local", "canvas"),
    [("3.10", "3.1"), ("0100", "100")],
)
def test_text_policies_do_not_coerce_numeric_looking_text(
    local: str, canvas: str
) -> None:
    assert comparison_check("title", local, canvas, policy=NORMALIZED_TEXT)["matches"] is False
    assert comparison_check("title", local, canvas, policy=EXACT)["matches"] is False


def test_normalized_text_keeps_nan_as_text() -> None:
    assert comparison_check("title", "nan", "nan", policy=NORMALIZED_TEXT)["matches"] is True


@pytest.mark.parametrize(
    ("local", "canvas", "matches"),
    [
        (False, None, True),
        ("false", False, True),
        ("false", True, False),
        ("true", True, True),
        ("no", True, False),
        ("0", True, False),
    ],
)
def test_boolean_policy_uses_closed_textual_vocabulary(
    local: object, canvas: object, matches: bool
) -> None:
    assert comparison_check("published", local, canvas, policy=BOOLEAN)["matches"] is matches


def test_datetime_comparison_uses_absolute_instant_and_standard_row() -> None:
    row = comparison_check(
        "due_at",
        "2026-09-01T18:00:00-05:00",
        "2026-09-01T23:00:00Z",
        policy=DATETIME,
    )

    assert row == {
        "field": "due_at",
        "status": "matches",
        "matches": True,
        "local": "2026-09-01T18:00:00-05:00",
        "canvas": "2026-09-01T23:00:00Z",
    }


@pytest.mark.parametrize(
    ("value", "allow_date_only", "reason"),
    [
        ("not-a-date", False, "invalid"),
        ("2026-09-01", False, "date_only"),
        (date(2026, 9, 1), False, "date_only"),
        ("2026-09-01T23:59:00", False, "offset_required"),
        (datetime(2026, 9, 1, 23, 59), False, "offset_required"),
    ],
)
def test_datetime_validation_returns_structured_issue(
    value: object, allow_date_only: bool, reason: str
) -> None:
    issue = datetime_validation_issue("due_at", value, allow_date_only=allow_date_only)

    assert issue is not None
    assert issue.field == "due_at"
    assert issue.reason == reason


def test_date_or_datetime_policy_accepts_date_and_aware_timestamp() -> None:
    require_valid_datetimes(
        {"publish_at": "2026-09-01"},
        {"publish_at": DATE_OR_DATETIME},
        source_type="Page",
    )
    require_valid_datetimes(
        {"publish_at": "2026-09-01T23:59:00-05:00"},
        {"publish_at": DATE_OR_DATETIME},
        source_type="Page",
    )


def test_aware_datetime_policy_rejects_offset_free_value() -> None:
    with pytest.raises(SystemExit, match="requires Z or an explicit UTC offset"):
        require_valid_datetimes(
            {"due_at": "2026-09-01T23:59:00"},
            {"due_at": DATETIME},
            source_type="Assignment",
        )


def test_first_value_reads_object_then_raw_payload() -> None:
    class Row:
        title = "Object title"

    assert first_value(Row(), {"title": "Payload title"}, "title") == "Object title"
    assert first_value(None, {"html_url": "https://canvas.test/item"}, "html_url") == (
        "https://canvas.test/item"
    )
