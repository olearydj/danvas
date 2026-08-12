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
