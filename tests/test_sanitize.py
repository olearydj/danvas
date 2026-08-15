from __future__ import annotations

import itertools

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


DETECTOR_CREDENTIAL_NAMES = (
    "token",
    "access_token",
    "verifier",
    "secret",
    "api_key",
    "secure_params",
    "signature",
    "policy",
    "expires",
    "key_pair_id",
    "awsaccesskeyid",
    "aws_access_key_id",
    "aws_secret_access_key",
    "x-amz-signature",
    "x-goog-credential",
)
CREDENTIAL_PREFIXES = (
    "",
    "my_",
    "client_",
    "session_",
    "refresh_",
    "app_",
    "canvas_",
    "x-",
)
CREDENTIAL_SEPARATORS = ("=", " = ", ":", " : ")
OPAQUE_CREDENTIAL_VALUES = (
    "abc123xyz",
    "eyJhbGci.abc123.signature",
    "YWJjZGVm+/=",
    "sk-live-opaquevalue",
    '"abc123xyz"',
    "'abc123xyz'",
)
COLON_RESERVED_NAMES = ("policy", "expires")
AMBIGUOUS_PROSE_NAMES = ("token", "signature", "policy", "expires", "bearer")
AMBIGUOUS_PROSE_SEPARATORS = (": ", " ")
ORDINARY_PROSE_VALUES = (
    "see rubric",
    "hand-written",
    "co-signed by both partners",
    "student's draft",
    "n/a",
    "page 3",
)
SCHEDULING_PROSE_VALUES = (
    "2026-09-01",
    "2026-09-01T23:59:00Z",
    "11:59pm",
    "10-point deduction",
)


def credential_assignment_cases() -> list[str]:
    return [
        f"{prefix}{name}{separator}{value}"
        # Colon-form "policy"/"expires" is deliberately excluded: it collides with
        # ordinary scheduling prose, so it is reserved for error sanitizing and
        # asserted by test_colon_reserved_names_are_error_sanitized instead.
        for prefix, name, separator, value in itertools.product(
            CREDENTIAL_PREFIXES,
            DETECTOR_CREDENTIAL_NAMES,
            CREDENTIAL_SEPARATORS,
            OPAQUE_CREDENTIAL_VALUES,
        )
        if not (name in COLON_RESERVED_NAMES and ":" in separator)
    ]


def colon_reserved_credential_cases() -> list[str]:
    return [
        f"{prefix}{name}{separator}{value}"
        for prefix, name, separator, value in itertools.product(
            CREDENTIAL_PREFIXES,
            COLON_RESERVED_NAMES,
            (":", " : "),
            OPAQUE_CREDENTIAL_VALUES,
        )
    ]


def scheduling_prose_cases() -> list[str]:
    return [
        f"{name}{separator}{value}"
        for name, separator, value in itertools.product(
            COLON_RESERVED_NAMES,
            AMBIGUOUS_PROSE_SEPARATORS,
            SCHEDULING_PROSE_VALUES,
        )
    ]


def ambiguous_prose_cases() -> list[str]:
    return [
        f"{name}{separator}{value}"
        for name, separator, value in itertools.product(
            AMBIGUOUS_PROSE_NAMES,
            AMBIGUOUS_PROSE_SEPARATORS,
            ORDINARY_PROSE_VALUES,
        )
    ]


@pytest.mark.parametrize(
    "key",
    [
        "AWS_ACCESS_KEY_ID",
        "AWSAccessKeyId",
        "aws-access-key-id",
        "AWS_SECRET_ACCESS_KEY",
        "AWSSecretAccessKey",
    ],
)
def test_paired_aws_credential_names_are_symmetrically_sensitive(key: str) -> None:
    assert is_sensitive_key(key)


def test_public_sanitizer_drops_both_halves_of_env_form_aws_credentials() -> None:
    payload = {
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI",
        "course": "kept",
    }

    assert sanitize_public(payload) == {"course": "kept"}


def test_error_sanitizer_redacts_env_form_aws_access_key_id() -> None:
    sanitized = sanitize_error("boto failed AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE afterward")

    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "afterward" in sanitized


def test_aws_credential_widening_preserves_ordinary_prose() -> None:
    assert not contains_sensitive_text("the access key is in the shared drive")
    assert not contains_sensitive_text("students access key readings each week")


def test_sensitive_detector_supports_whole_value_hashing_without_near_matches() -> None:
    assert contains_sensitive_text("comment contains secret=abc")
    assert not contains_sensitive_text("the secretive assignment is complete")


def test_sensitive_detector_covers_credential_assignment_cross_product() -> None:
    missed = [
        value for value in credential_assignment_cases() if not contains_sensitive_text(value)
    ]

    assert not missed, f"credential assignments missed: {missed[:10]}"


def test_sensitive_detector_preserves_ambiguous_prose_cross_product() -> None:
    over_redacted = [
        value for value in ambiguous_prose_cases() if contains_sensitive_text(value)
    ]

    assert not over_redacted, f"ordinary prose detected: {over_redacted[:10]}"


def test_colon_reserved_names_are_error_sanitized() -> None:
    failures = [
        value
        for value in colon_reserved_credential_cases()
        if contains_sensitive_text(value) or "[redacted]" not in sanitize_error(value)
    ]

    assert not failures, f"colon-reserved handling changed: {failures[:10]}"


def test_sensitive_detector_preserves_scheduling_prose() -> None:
    over_redacted = [value for value in scheduling_prose_cases() if contains_sensitive_text(value)]

    assert not over_redacted, f"scheduling prose detected: {over_redacted[:10]}"


def test_sensitive_detector_preserves_embedded_ordinary_vocabulary() -> None:
    prose = (
        "Your extension expires: 2026-09-01.",
        "Policy: 2026-09-01 is the cutoff.",
        "This accommodation expires: Friday.",
        "The bearer of the group report should submit it.",
        "Please give this feedback to the bearer directly.",
        "The bearer token concept is covered in week 4.",
        "Discuss bearer instruments in your finance memo.",
    )

    assert not [value for value in prose if contains_sensitive_text(value)]


def test_detector_and_error_sanitizer_cover_same_assignment_matrix() -> None:
    failures = []
    for value in credential_assignment_cases():
        detector_redacts = contains_sensitive_text(value)
        error_redacts = "[redacted]" in sanitize_error(value)
        if not detector_redacts or not error_redacts:
            failures.append((value, detector_redacts, error_redacts))

    assert not failures, f"cross-path credential mismatch: {failures[:10]}"


@pytest.mark.parametrize(
    "value",
    ["token: password", "signature: deadbeef", "Bearer abcdefghijklmnop"],
)
def test_alpha_only_ambiguous_payloads_are_error_sanitized(value: str) -> None:
    assert not contains_sensitive_text(value)
    assert "[redacted]" in sanitize_error(value)


@pytest.mark.parametrize("value", ['token="abc123"', "token='abc123'"])
def test_sanitize_error_redacts_quoted_credentials(value: str) -> None:
    assert "abc123" not in sanitize_error(value)
