"""Dependency-free sanitization for public errors and retained evidence."""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "awsaccesskeyid",
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
    r"expires|key[_-]?pair[_-]?id|awsaccesskeyid|x-amz-[a-z0-9-]+|x-goog-[a-z0-9-]+"
)
CREDENTIAL_NAME_PATTERN = (
    r"(?:access_)?token|verifier|secret|api[_-]?key|secure[_-]?params|signature|"
    r"key[_-]?pair[_-]?id|awsaccesskeyid|x-amz-[a-z0-9-]+|x-goog-[a-z0-9-]+"
)
ASSIGNED_VALUE_PATTERN = r'(?:"[^"\r\n]+"|\'[^\'\r\n]+\'|[^&\s,;"\']+)'
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    rf"({SENSITIVE_NAME_PATTERN})"
    rf"\s*([=:])\s*({ASSIGNED_VALUE_PATTERN})"
)
SENSITIVE_TEXT_RE = re.compile(
    rf"(?i)(?<![A-Za-z0-9])(?:{CREDENTIAL_NAME_PATTERN})\s*[:=]\s*"
    rf"{ASSIGNED_VALUE_PATTERN}"
    rf"|(?<![A-Za-z0-9])(?:policy|expires)\s*=\s*{ASSIGNED_VALUE_PATTERN}"
    r"|\bauthorization\s*[:=]\s*bearer\s+[^\s,;]+"
    r"|\bbearer\s+(?!of\b)[^\s,;]+"
)


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
    return bool(SENSITIVE_TEXT_RE.search(str(value or "")))


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
