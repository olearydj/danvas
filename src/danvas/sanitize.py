"""Dependency-free sanitization for public errors and retained evidence."""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "awsaccesskeyid",
    "aws_access_key_id",
    "awssecretaccesskey",
    "aws_secret_access_key",
    "download_url",
    "error_url",
    "expires",
    "file_param",
    "file_url",
    "key_pair_id",
    "policy",
    "secure_params",
    "secret",
    "signature",
    "token",
    "upload_url",
    "url",
    "verifier",
}
EMBEDDED_SENSITIVE_NAMES = {
    "download_url",
    "error_url",
    "file_param",
    "file_url",
    "token",
    "upload_url",
    "url",
    "verifier",
}

URLISH_RE = re.compile(r"https?://\S+|[A-Za-z]+://\S+")
AUTHORIZATION_RE = re.compile(r"(?i)\b(authorization\s*[:=]\s*bearer|bearer)\s+[^\s,;]+")
SENSITIVE_NAME_PATTERN = (
    r"(?:access_)?token|verifier|secret|api[_-]?key|secure[_-]?params|signature|policy|"
    r"expires|key[_-]?pair[_-]?id|aws[_-]?access[_-]?key[_-]?id|"
    r"aws[_-]?secret[_-]?access[_-]?key|"
    r"x-amz-[a-z0-9-]+|x-goog-[a-z0-9-]+"
)
ASSIGNED_VALUE_PATTERN = r'(?:"[^"\r\n]+"|\'[^\'\r\n]+\'|[^&\s,;"\']+)'
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    rf"({SENSITIVE_NAME_PATTERN})"
    rf"\s*([=:])\s*({ASSIGNED_VALUE_PATTERN})"
)
UNAMBIGUOUS_CREDENTIAL_RE = re.compile(
    rf"(?i)(?<![A-Za-z0-9])(?:access[_-]?token|verifier|secret|api[_-]?key|"
    rf"secure[_-]?params|key[_-]?pair[_-]?id|aws[_-]?access[_-]?key[_-]?id|"
    rf"aws[_-]?secret[_-]?access[_-]?key|x-amz-[a-z0-9-]+|x-goog-[a-z0-9-]+)"
    rf"\s*[:=]\s*{ASSIGNED_VALUE_PATTERN}"
)
AMBIGUOUS_EQUALS_RE = re.compile(
    rf"(?i)(?<![A-Za-z0-9])(?:token|signature|policy|expires)\s*=\s*"
    rf"{ASSIGNED_VALUE_PATTERN}"
)
# "policy" and "expires" are omitted here on purpose: colon forms commonly read
# as grading prose ("your extension expires: 2026-09-01"). Signed-request forms
# stay covered by SENSITIVE_VALUE_RE for error sanitizing instead of making the
# whole-comment guard discard prose-capable recovery rows.
AMBIGUOUS_COLON_RE = re.compile(
    rf"(?i)(?<![A-Za-z0-9])(?:token|signature)\s*:\s*"
    rf"(?P<value>{ASSIGNED_VALUE_PATTERN})"
)
AUTHORIZATION_BEARER_RE = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*bearer\s+[^\s,;]+"
)
BARE_BEARER_RE = re.compile(r"(?i)\bbearer\s+(?P<value>[^\s,;]+)")
SK_STYLE_CREDENTIAL_RE = re.compile(r"(?i)^sk-[a-z]+-[a-z0-9_-]{6,}$")


def normalize_sensitive_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def is_sensitive_key(key: str, *, embedded: bool = False) -> bool:
    """Recognize canonical keys, optionally including upload-style embedded names."""
    normalized = normalize_sensitive_name(key)
    return (
        normalized in SENSITIVE_NAMES
        or normalized.startswith("x_amz_")
        or normalized.startswith("x_goog_")
        or (embedded and any(name in normalized for name in EMBEDDED_SENSITIVE_NAMES))
    )


def contains_sensitive_text(value: Any) -> bool:
    """Detect a sensitive value marker without returning sanitized prose."""
    text = str(value or "")
    if (
        UNAMBIGUOUS_CREDENTIAL_RE.search(text)
        or AMBIGUOUS_EQUALS_RE.search(text)
        or AUTHORIZATION_BEARER_RE.search(text)
    ):
        return True
    return any(
        _credential_shaped_payload(match.group("value"))
        for pattern in (AMBIGUOUS_COLON_RE, BARE_BEARER_RE)
        for match in pattern.finditer(text)
    )


def _credential_shaped_payload(value: str) -> bool:
    """Distinguish opaque credential values from ordinary comment prose."""
    payload = value.strip().strip("\"'").rstrip(".,!?)]}")
    return bool(SK_STYLE_CREDENTIAL_RE.fullmatch(payload)) or (
        len(payload) >= 6
        and any(
            character.isdigit() or character in "._~+/=" for character in payload
        )
    )


def sanitize_error(value: Any, *, url_marker: str = "[url]") -> str:
    """Collapse and sanitize exception text intended for public evidence."""
    text = " ".join(str(value).split())
    text = SENSITIVE_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        text,
    )
    text = AUTHORIZATION_RE.sub(lambda match: f"{match.group(1)} [redacted]", text)
    return URLISH_RE.sub(url_marker, text)


def sanitize_public(
    value: Any,
    *,
    url_marker: str = "[url]",
    embedded_keys: bool = False,
) -> Any:
    """Drop sensitive keys and recursively sanitize public retained evidence."""
    if isinstance(value, dict):
        return {
            str(key): sanitize_public(
                item,
                url_marker=url_marker,
                embedded_keys=embedded_keys,
            )
            for key, item in value.items()
            if not is_sensitive_key(str(key), embedded=embedded_keys)
        }
    if isinstance(value, list):
        return [
            sanitize_public(item, url_marker=url_marker, embedded_keys=embedded_keys)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            sanitize_public(item, url_marker=url_marker, embedded_keys=embedded_keys)
            for item in value
        ]
    if isinstance(value, str):
        return sanitize_error(value, url_marker=url_marker)
    return value
