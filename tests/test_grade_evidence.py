from __future__ import annotations

from types import SimpleNamespace

import pytest

from danvas.grade_evidence import (
    assignment_release_context,
    candidate_recovery_row,
    classify_effect_outcome,
    classify_release_state,
    recovery_text,
)


@pytest.mark.parametrize(
    ("effects", "had_error", "expected", "detail"),
    [
        (
            {"grade": "desired", "comment": "desired"},
            False,
            "verified_applied",
            None,
        ),
        (
            {"grade": "original", "comment": "original"},
            True,
            "unchanged_failure",
            None,
        ),
        (
            {"grade": "desired", "comment": "original"},
            True,
            "partially_applied",
            "grade_only",
        ),
        (
            {"grade": "original", "comment": "desired"},
            True,
            "partially_applied",
            "comment_only",
        ),
        (
            {"grade": "other", "comment": "original"},
            False,
            "applied_unverified",
            None,
        ),
    ],
)
def test_classify_effect_outcome(
    effects: dict[str, str],
    had_error: bool,
    expected: str,
    detail: str | None,
) -> None:
    assert classify_effect_outcome(effects, had_error=had_error) == (expected, detail)


def release_row(
    *, posted_at: str | None, assignment_visible: bool, verified: bool = True
) -> dict[str, object]:
    return {
        "desired_verified": verified,
        "observed": {
            "readback_available": True,
            "posted_at_available": True,
            "posted_at": posted_at,
            "assignment_visible_available": True,
            "assignment_visible": assignment_visible,
        },
    }


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([release_row(posted_at="2026-08-11T12:00:00Z", assignment_visible=True)], "verified_visible"),
        ([release_row(posted_at=None, assignment_visible=True)], "verified_hidden"),
        (
            [
                release_row(posted_at="2026-08-11T12:00:00Z", assignment_visible=True),
                release_row(posted_at=None, assignment_visible=True),
            ],
            "mixed",
        ),
        (
            [release_row(posted_at="2026-08-11T12:00:00Z", assignment_visible=False)],
            "not_determined",
        ),
        ([release_row(posted_at=None, assignment_visible=True, verified=False)], "not_determined"),
    ],
)
def test_classify_release_state_is_conservative(
    rows: list[dict[str, object]], expected: str
) -> None:
    assignment = SimpleNamespace(
        published=True,
        unlock_at=None,
        due_at="2026-08-11T12:00:00Z",
        lock_at=None,
        post_manually=True,
    )

    result = classify_release_state(
        rows,
        assignment_context=assignment_release_context(assignment),
        require_desired_verified=True,
        basis="verified_target_state",
    )

    assert result["conclusion"] == expected
    assert result["assignment_context"]["post_manually"]["value"] is True


def test_release_state_requires_documented_visibility_fields() -> None:
    result = classify_release_state(
        [
            {
                "desired_verified": True,
                "observed": {
                    "readback_available": True,
                    "posted_at_available": False,
                    "assignment_visible_available": False,
                },
            }
        ],
        assignment_context={},
        require_desired_verified=True,
        basis="verified_target_state",
    )

    assert result["conclusion"] == "not_determined"
    assert result["reason"] == "required_submission_visibility_fields_unavailable"


def test_recovery_text_redacts_sensitive_url_parameters() -> None:
    text = "Restore https://canvas.example/file?verifier=secret-value"

    result = recovery_text(text)

    assert isinstance(result, dict)
    assert result["status"] == "redacted_sensitive_value"
    assert "secret-value" not in str(result)


@pytest.mark.parametrize(
    "text",
    [
        "Policy: late work is accepted through Friday.",
        "This accommodation expires: Friday.",
        "The bearer of the group report should submit it.",
        "Signature: missing on page 3, please resubmit.",
        "signature: see attached form",
        "token: see rubric",
        "Please give this feedback to the bearer directly.",
        "The bearer token concept is covered in week 4.",
        "Discuss bearer instruments in your finance memo.",
    ],
)
def test_recovery_text_preserves_benign_sensitive_vocabulary(text: str) -> None:
    assert recovery_text(text) == text


@pytest.mark.parametrize(
    "text",
    ["token: abc123", "signature: sig123", "Bearer abc123"],
)
def test_recovery_text_hashes_credential_shaped_comment_text(text: str) -> None:
    result = recovery_text(text)

    assert isinstance(result, dict)
    assert result["status"] == "redacted_sensitive_value"
    assert text not in str(result)


def test_forward_recovery_requires_representable_grade_baseline() -> None:
    action = {
        "canvas_id": 1,
        "name": "Example",
        "proposed_grade": "90",
        "comment_change": False,
    }
    result = {
        "observed": {
            "readback_available": True,
            "grade": None,
            "score": None,
            "comments": [],
        },
        "effect_status": {"grade": "original", "comment": "not_planned"},
    }

    assert candidate_recovery_row(action, result, mode="post") is None
