from __future__ import annotations

import pytest

from danvas.sanitize import (
    contains_sensitive_text,
    is_sensitive_key,
    sanitize_error,
    sanitize_public,
)


@pytest.mark.parametrize(
    "value",
    [
        "token=abc",
        "ACCESS_TOKEN: abc",
        "secret=abc",
        "api-key=abc",
        "Authorization: Bearer abc",
        "bearer abc",
        "X-Amz-Signature=abc",
        "X-Goog-Credential=abc",
        "key-pair-id=abc",
    ],
)
def test_sanitize_error_redacts_shared_vocabulary(value: str) -> None:
    sanitized = sanitize_error(f"failed {value} afterward")

    assert "abc" not in sanitized
    assert "afterward" in sanitized


def test_sanitize_error_removes_whole_urls() -> None:
    sanitized = sanitize_error("GET https://canvas.test/upload?verifier=abc failed")

    assert sanitized == "GET [url] failed"


@pytest.mark.parametrize(
    "key",
    ["token", "upload-url", "download_url", "x-amz-policy", "X_Goog_Signature"],
)
def test_sensitive_key_vocabulary_is_case_and_separator_insensitive(key: str) -> None:
    assert is_sensitive_key(key)


def test_recursive_public_sanitizer_drops_keys_and_cleans_strings() -> None:
    payload = {
        "message": "failed bearer abc",
        "nested": {"upload_url": "https://canvas.test/abc", "safe": "kept"},
    }

    assert sanitize_public(payload) == {
        "message": "failed bearer [redacted]",
        "nested": {"safe": "kept"},
    }


def test_sensitive_detector_supports_whole_value_hashing_without_near_matches() -> None:
    assert contains_sensitive_text("comment contains secret=abc")
    assert not contains_sensitive_text("the secretive assignment is complete")


@pytest.mark.parametrize(
    "value",
    [
        "access_token: eyJabc123",
        "x-amz-signature: abc123",
        "secret: hunter2",
        "token: abc123",
        "signature: sig123",
        'token="abc123"',
        "token='abc123'",
        "Bearer abc123",
        "Authorization: Bearer abc123",
    ],
)
def test_sensitive_detector_catches_credential_shaped_text(value: str) -> None:
    assert contains_sensitive_text(value)


@pytest.mark.parametrize(
    "value",
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
def test_sensitive_detector_preserves_benign_prose(value: str) -> None:
    assert not contains_sensitive_text(value)


@pytest.mark.parametrize("value", ["Policy: eyJabc123", "Expires: 1770000000"])
def test_sensitive_detector_reserves_colon_policy_fields_for_error_sanitizing(
    value: str,
) -> None:
    assert not contains_sensitive_text(value)
    assert "[redacted]" in sanitize_error(value)


@pytest.mark.parametrize("value", ['token="abc123"', "token='abc123'"])
def test_sanitize_error_redacts_quoted_credentials(value: str) -> None:
    assert "abc123" not in sanitize_error(value)
