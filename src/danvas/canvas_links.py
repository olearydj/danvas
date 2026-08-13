"""Safe Canvas URL and rich-content file identity helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

FILE_URL_ATTRS = ("href", "src", "data-api-endpoint", "data-download-url")
FILE_PATH_RE = re.compile(
    r"^/(?:api/v1/)?(?:(?:courses/(\d+)/)?files/(\d+))(?:/(?:download|preview))?/?$"
)
SENSITIVE_QUERY_NAMES = {
    "access_token",
    "api_key",
    "expires",
    "key-pair-id",
    "policy",
    "secure_params",
    "signature",
    "token",
    "verifier",
}


def normalized_url_origin(value: str) -> tuple[str, str, int] | None:
    """Return a normalized HTTP(S) origin tuple, including the effective port."""
    try:
        parsed = urlsplit(str(value or ""))
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, parsed.hostname.casefold(), port


def same_url_origin(value: str, canvas_origin: str | None) -> bool:
    """Return whether an absolute URL belongs to the configured Canvas origin."""
    if not canvas_origin:
        return False
    return normalized_url_origin(value) == normalized_url_origin(canvas_origin)


def canvas_origin_url(canvas_origin: str) -> str:
    """Return a validated origin-only Canvas URL."""
    normalized = normalized_url_origin(canvas_origin)
    if normalized is None:
        raise ValueError("Canvas origin must be an absolute HTTP(S) URL without credentials.")
    scheme, hostname, port = normalized
    default_port = 443 if scheme == "https" else 80
    host = hostname if port == default_port else f"{hostname}:{port}"
    return f"{scheme}://{host}"


def stable_course_file_url(canvas_origin: str, course_id: int, file_id: int) -> str:
    """Build the supported stable course-file view URL."""
    return f"{canvas_origin_url(canvas_origin)}/courses/{int(course_id)}/files/{int(file_id)}?wrap=1"


def canonical_canvas_object_url(value: Any, *, canvas_origin: str | None) -> str:
    """Keep only a stable same-origin Canvas object URL without query or fragment."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme or parsed.netloc:
        if not same_url_origin(text, canvas_origin):
            return ""
        origin = canvas_origin_url(str(canvas_origin))
        return f"{origin}{parsed.path}"
    if not parsed.path.startswith("/"):
        return ""
    return urlunsplit(("", "", parsed.path, "", ""))


def canvas_file_reference(
    value: Any,
    *,
    current_course_id: int,
    canvas_origin: str | None,
) -> dict[str, Any] | None:
    """Parse a Canvas-looking file URL without retaining its raw value."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError:
        return malformed_reference(text, "malformed_url") if looks_file_like(text) else None
    match = FILE_PATH_RE.match(parsed.path)
    if not match:
        return None
    explicit_course_id = int(match.group(1)) if match.group(1) else None
    file_id = int(match.group(2))
    absolute = bool(parsed.scheme or parsed.netloc)
    if parsed.username or parsed.password:
        status = "unsafe"
        reason = "credentials_in_url"
    elif absolute and not same_url_origin(text, canvas_origin):
        status = "foreign_origin"
        reason = "canvas_file_path_on_untrusted_origin"
    elif explicit_course_id is not None and explicit_course_id != int(current_course_id):
        status = "cross_course"
        reason = "file_targets_different_course"
    else:
        status = "valid"
        reason = ""
    query_names = sensitive_query_names(parsed.query)
    result = {
        "status": status,
        "reason": reason,
        "course_id": explicit_course_id or int(current_course_id),
        "file_id": file_id,
        "volatile_query_present": bool(query_names),
        "volatile_query_names": query_names,
    }
    if status == "valid" and canvas_origin:
        try:
            result["canvas_url"] = stable_course_file_url(
                canvas_origin, int(current_course_id), file_id
            )
        except ValueError:
            result["status"] = "unsafe"
            result["reason"] = "invalid_canvas_origin"
    return result


def extract_canvas_file_references(
    html: str,
    *,
    current_course_id: int,
    canvas_origin: str | None,
) -> list[dict[str, Any]]:
    """Extract one safe Canvas file identity record per rich-content element."""
    soup = BeautifulSoup(str(html or ""), "html.parser")
    references: list[dict[str, Any]] = []
    occurrence = 0
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        candidates = []
        attributes = []
        for attribute in FILE_URL_ATTRS:
            raw = tag.get(attribute)
            if not isinstance(raw, str):
                continue
            parsed = canvas_file_reference(
                raw,
                current_course_id=current_course_id,
                canvas_origin=canvas_origin,
            )
            if parsed is not None:
                candidates.append(parsed)
                attributes.append(attribute)
            elif attribute in {"href", "src"} and relative_asset_url(raw):
                candidates.append(malformed_reference(raw, "relative_local_asset"))
                candidates[-1]["status"] = "relative_asset"
                attributes.append(attribute)
            elif attribute in {"href", "src"} and blocked_root_relative_url(
                raw, current_course_id=current_course_id
            ):
                candidates.append(malformed_reference(raw, "blocked_root_relative"))
                candidates[-1]["status"] = "blocked_root_relative"
                attributes.append(attribute)
        declared_file = str(tag.get("data-api-returntype") or "").casefold() == "file"
        if declared_file and not candidates:
            candidates.append(malformed_reference(str(tag), "declared_file_target_unparseable"))
            attributes.append("data-api-returntype")
        if not candidates:
            continue
        occurrence += 1
        identity_pairs = {
            (item.get("course_id"), item.get("file_id"))
            for item in candidates
            if item.get("file_id") is not None
        }
        statuses = {str(item.get("status")) for item in candidates}
        if len(identity_pairs) > 1:
            record: dict[str, Any] = {
                "status": "conflict",
                "reason": "element_file_identities_disagree",
                "course_id": None,
                "file_id": None,
                "conflicting_identities": [
                    {"course_id": course, "file_id": file}
                    for course, file in sorted(identity_pairs)
                ],
            }
        else:
            record = dict(worst_reference(candidates, statuses))
        record.update(
            {
                "tag": tag.name,
                "attributes": sorted(set(attributes)),
                "occurrence": occurrence,
            }
        )
        references.append(record)
    return references


def worst_reference(
    candidates: list[dict[str, Any]], statuses: set[str]
) -> dict[str, Any]:
    priority = (
        "unsafe",
        "foreign_origin",
        "cross_course",
        "blocked_root_relative",
        "malformed",
        "relative_asset",
        "valid",
    )
    selected_status = next((status for status in priority if status in statuses), "malformed")
    selected = next(item for item in candidates if item.get("status") == selected_status)
    result = dict(selected)
    query_names = sorted(
        {
            name
            for item in candidates
            for name in item.get("volatile_query_names", [])
        }
    )
    result["volatile_query_present"] = bool(query_names)
    result["volatile_query_names"] = query_names
    return result


def sensitive_query_names(query: str) -> list[str]:
    names = []
    for part in str(query or "").split("&"):
        name = part.partition("=")[0].casefold()
        if (
            name in SENSITIVE_QUERY_NAMES
            or name.startswith("x-amz-")
            or name.startswith("x-goog-")
        ):
            names.append(name)
    return sorted(set(names))


def looks_file_like(value: str) -> bool:
    return bool(re.search(r"(?:^|/)(?:api/v1/)?(?:courses/\d+/)?files(?:/|$)", value))


def relative_asset_url(value: str) -> bool:
    """Return whether a URL is structurally project-relative, regardless of suffix."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return not (
        parsed.scheme
        or parsed.netloc
        or not parsed.path
        or parsed.path.startswith(("/", "#"))
    )


def current_course_root_relative_url(value: str, *, current_course_id: int) -> bool:
    """Return whether a root-relative URL belongs to the current Canvas course."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith(f"/courses/{int(current_course_id)}/")
    )


def blocked_root_relative_url(value: str, *, current_course_id: int) -> bool:
    """Return whether an unrecognized URL occupies the blocked root-relative bucket."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith("/")
        and not current_course_root_relative_url(
            value, current_course_id=current_course_id
        )
    )


def malformed_reference(value: str, reason: str) -> dict[str, Any]:
    return {
        "status": "malformed",
        "reason": reason,
        "course_id": None,
        "file_id": None,
        "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "volatile_query_present": False,
        "volatile_query_names": [],
    }
