"""Authority-aware Canvas collection for course snapshots."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Literal

from canvasapi.exceptions import (
    CanvasException,
    Forbidden,
    InvalidAccessToken,
    RateLimitExceeded,
    Unauthorized,
)
from requests.exceptions import RequestException

from danvas.files import canvas_file_record
from danvas.overrides import redacted_assignment_overrides
from danvas.page_sources import (
    BODY_NORMALIZER_VERSION,
    canonicalize_page_html,
    canonicalize_page_url,
    page_record,
)
from danvas.utils import canvas_object_to_dict, html_to_text

CollectionStatus = Literal["available", "unavailable", "failed", "partial"]
Collector = Callable[[Any, Mapping[str, list[dict[str, Any]]], str | None], "CollectionResult"]


@dataclass(frozen=True)
class ExceptionClassification:
    status: Literal["unavailable", "failed"]
    reason: str
    error_type: str


@dataclass(frozen=True)
class CollectionResult:
    items: list[dict[str, Any]]
    status: CollectionStatus = "available"
    reason: str | None = None
    error_type: str | None = None
    dependency: str | None = None

    @property
    def authoritative(self) -> bool:
        return self.status == "available"

    def metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "authoritative": self.authoritative,
            "item_count": len(self.items),
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.dependency:
            payload["dependency"] = self.dependency
        return payload


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    required: bool
    collector: Collector
    dependencies: tuple[str, ...] = ()


COLLECTION_NAMES = (
    "assignment_groups",
    "assignments",
    "folders",
    "files",
    "discussions",
    "announcements",
    "quizzes",
    "pages",
    "group_categories",
)


def available(items: list[dict[str, Any]]) -> CollectionResult:
    return CollectionResult(items=items)


def classify_collection_exception(exc: Exception) -> ExceptionClassification | None:
    """Return a bounded classification for expected Canvas/request failures."""
    if isinstance(exc, InvalidAccessToken):
        return ExceptionClassification("failed", "invalid_access_token", "InvalidAccessToken")
    if isinstance(exc, RateLimitExceeded):
        return ExceptionClassification("failed", "rate_limited", "RateLimitExceeded")
    if isinstance(exc, Unauthorized):
        return ExceptionClassification("unavailable", "unauthorized", "Unauthorized")
    if isinstance(exc, Forbidden):
        return ExceptionClassification("unavailable", "forbidden", "Forbidden")
    if isinstance(exc, RequestException):
        return ExceptionClassification("failed", "network_error", "RequestException")
    if isinstance(exc, CanvasException):
        return ExceptionClassification("failed", "collection_error", "CanvasException")
    return None


def collect_snapshot_collections(
    course: Any, *, canvas_origin: str | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    results: dict[str, CollectionResult] = {}
    values: dict[str, list[dict[str, Any]]] = {}
    for spec in COLLECTION_SPECS:
        blocked_by = next(
            (
                dependency
                for dependency in spec.dependencies
                if not results[dependency].authoritative
            ),
            None,
        )
        if blocked_by:
            dependency_result = results[blocked_by]
            status: Literal["unavailable", "failed"] = (
                "unavailable"
                if dependency_result.status == "unavailable"
                else "failed"
            )
            result = CollectionResult(
                items=[],
                status=status,
                reason=f"dependency_{status}",
                error_type=dependency_result.error_type,
                dependency=blocked_by,
            )
        else:
            try:
                result = spec.collector(course, values, canvas_origin)
            except Exception as exc:
                classification = classify_collection_exception(exc)
                if classification is None:
                    raise
                if classification.reason == "invalid_access_token":
                    raise SystemExit(
                        "Canvas access token is invalid; snapshot collection stopped and no snapshot was written."
                    ) from exc
                if spec.required:
                    raise SystemExit(
                        f"Required snapshot collection {spec.name!r} "
                        f"{classification.status} ({classification.reason})."
                    ) from exc
                result = CollectionResult(
                    items=[],
                    status=classification.status,
                    reason=classification.reason,
                    error_type=classification.error_type,
                )
        results[spec.name] = result
        values[spec.name] = result.items
    return values, {name: results[name].metadata() for name in COLLECTION_NAMES}


def snapshot_collection_metadata(
    snapshot: Mapping[str, Any], name: str
) -> dict[str, Any]:
    """Return normalized authority metadata, including legacy snapshot support."""
    version = int(snapshot.get("schema_version") or 1)
    if version >= 5:
        collections = snapshot.get("collections")
        raw = collections.get(name) if isinstance(collections, Mapping) else None
        if not isinstance(raw, Mapping):
            return {
                "status": "failed",
                "authoritative": False,
                "reason": "metadata_missing",
                "error_type": "",
                "item_count": 0,
            }
        status = str(raw.get("status") or "failed")
        authoritative = status == "available" and raw.get("authoritative") is True
        return {
            "status": status,
            "authoritative": authoritative,
            "reason": str(raw.get("reason") or ""),
            "error_type": str(raw.get("error_type") or ""),
            "item_count": int(raw.get("item_count") or 0),
            **(
                {"dependency": str(raw["dependency"])}
                if raw.get("dependency")
                else {}
            ),
        }
    if name == "pages" and version < 4:
        return {
            "status": "unavailable",
            "authoritative": False,
            "reason": "snapshot_schema",
            "error_type": "",
            "item_count": 0,
        }
    rows = snapshot.get(name)
    return {
        "status": "available",
        "authoritative": True,
        "reason": "",
        "error_type": "",
        "item_count": len(rows) if isinstance(rows, list) else 0,
    }


def snapshot_is_complete(collections: Mapping[str, Mapping[str, Any]]) -> bool:
    return all(collections[name].get("authoritative") is True for name in COLLECTION_NAMES)


def snapshot_collection_warnings(snapshot: Mapping[str, Any]) -> list[str]:
    warnings = []
    for name in COLLECTION_NAMES:
        metadata = snapshot_collection_metadata(snapshot, name)
        if metadata["authoritative"]:
            continue
        reason = metadata.get("reason") or "collection_error"
        warnings.append(
            f"WARNING: snapshot collection {name} is {metadata['status']} ({reason}); "
            "its rows are not authoritative."
        )
    return warnings


def collect_assignment_groups(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    groups = [
        canvas_object_to_dict(group)
        for group in sorted(
            course.get_assignment_groups(),
            key=lambda group: str(getattr(group, "name", "")),
        )
    ]
    return available(groups)


def collect_assignments(
    course: Any, values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    groups_by_id = {
        int(group["id"]): group
        for group in values["assignment_groups"]
        if group.get("id") is not None
    }
    assignments = []
    for assignment in course.get_assignments(include=["all_dates", "overrides"]):
        group = groups_by_id.get(
            int(getattr(assignment, "assignment_group_id", 0) or 0), {}
        )
        row = {
            "id": getattr(assignment, "id", ""),
            "name": getattr(assignment, "name", ""),
            "assignment_group_id": getattr(assignment, "assignment_group_id", ""),
            "assignment_group_name": group.get("name", ""),
            "points_possible": getattr(assignment, "points_possible", ""),
            "due_at": getattr(assignment, "due_at", ""),
            "unlock_at": getattr(assignment, "unlock_at", ""),
            "lock_at": getattr(assignment, "lock_at", ""),
            "published": getattr(assignment, "published", ""),
            "html_url": getattr(assignment, "html_url", ""),
            "submission_types": getattr(assignment, "submission_types", []) or [],
            "description_text": html_to_text(getattr(assignment, "description", "")),
        }
        row.update(redacted_assignment_overrides(assignment))
        assignments.append(row)
    assignments.sort(key=lambda row: (str(row["due_at"] or ""), str(row["name"] or "")))
    return available(assignments)


def collect_folders(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    folders = [
        canvas_object_to_dict(folder)
        for folder in sorted(
            course.get_folders(),
            key=lambda folder: str(getattr(folder, "full_name", "")),
        )
    ]
    return available(folders)


def collect_files(
    course: Any, values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    folders_by_id = {
        int(folder["id"]): SimpleNamespace(**folder)
        for folder in values["folders"]
        if folder.get("id") is not None
    }
    rows = [canvas_file_record(file_obj, folders_by_id) for file_obj in course.get_files()]
    rows.sort(key=lambda row: (str(row["folder_full_name"]), str(row["display_name"])))
    return available(rows)


def collect_discussions(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    rows = [discussion_record(topic) for topic in course.get_discussion_topics()]
    rows.sort(key=lambda row: str(row["title"]))
    return available(rows)


def collect_announcements(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    rows = [
        discussion_record(topic)
        for topic in course.get_discussion_topics(only_announcements=True)
    ]
    rows.sort(key=lambda row: (str(row["posted_at"]), str(row["title"])))
    return available(rows)


def discussion_record(topic: Any) -> dict[str, Any]:
    return {
        "id": getattr(topic, "id", None),
        "title": getattr(topic, "title", "") or "",
        "html_url": getattr(topic, "html_url", "") or "",
        "assignment_id": getattr(topic, "assignment_id", None),
        "published": getattr(topic, "published", None),
        "locked": getattr(topic, "locked", None),
        "posted_at": getattr(topic, "posted_at", "") or "",
        "delayed_post_at": getattr(topic, "delayed_post_at", "") or "",
        "message_text": html_to_text(getattr(topic, "message", "") or ""),
    }


def collect_quizzes(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    rows = []
    for quiz in course.get_quizzes():
        rows.append(
            {
                "id": getattr(quiz, "id", None),
                "assignment_id": getattr(quiz, "assignment_id", None),
                "title": getattr(quiz, "title", "") or "",
                "description_text": html_to_text(getattr(quiz, "description", "") or ""),
                "quiz_type": getattr(quiz, "quiz_type", "") or "",
                "points_possible": getattr(quiz, "points_possible", None),
                "question_count": getattr(quiz, "question_count", None),
                "due_at": getattr(quiz, "due_at", "") or "",
                "unlock_at": getattr(quiz, "unlock_at", "") or "",
                "lock_at": getattr(quiz, "lock_at", "") or "",
                "published": getattr(quiz, "published", None),
                "time_limit": getattr(quiz, "time_limit", None),
                "allowed_attempts": getattr(quiz, "allowed_attempts", None),
                "html_url": getattr(quiz, "html_url", "") or "",
            }
        )
    rows.sort(key=lambda row: str(row["title"]))
    return available(rows)


def collect_pages(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], origin: str | None
) -> CollectionResult:
    rows = []
    course_id = int(getattr(course, "id", 0) or 0)
    for summary in course.get_pages():
        record = page_record(summary)
        if not record["body"] and record["url"]:
            record = page_record(course.get_page(record["url"]))
        canonical = canonicalize_page_html(
            record.pop("body", ""), course_id=course_id, canvas_origin=origin
        )
        record["html_url"], unsafe_html_url = canonicalize_page_url(
            str(record.get("html_url") or ""),
            course_id=course_id,
            canvas_origin=origin,
        )
        if unsafe_html_url:
            record["html_url"] = ""
        rows.append(
            {
                **record,
                "body_sha256": canonical["body_sha256"],
                "body_hash_status": canonical["body_hash_status"],
                "volatile_url_count": canonical["volatile_url_count"],
                "body_normalizer": BODY_NORMALIZER_VERSION,
            }
        )
    rows.sort(
        key=lambda row: (
            " ".join(str(row.get("title") or "").casefold().split()),
            str(row.get("page_id") or row.get("url") or ""),
        )
    )
    return available(rows)


def collect_group_categories(
    course: Any, _values: Mapping[str, list[dict[str, Any]]], _origin: str | None
) -> CollectionResult:
    rows = []
    nested_failures: list[ExceptionClassification] = []
    for category in course.get_group_categories():
        try:
            groups = sorted(
                category.get_groups(),
                key=lambda group: str(getattr(group, "name", "")),
            )
        except Exception as exc:
            classification = classify_collection_exception(exc)
            if classification is None:
                raise
            if classification.reason == "invalid_access_token":
                raise SystemExit(
                    "Canvas access token is invalid; snapshot collection stopped and no snapshot was written."
                ) from exc
            nested_failures.append(classification)
            rows.append(
                {
                    "id": getattr(category, "id", None),
                    "name": getattr(category, "name", "") or "",
                    "self_signup": getattr(category, "self_signup", None),
                    "group_count": None,
                    "member_count": None,
                    "groups": [],
                    "groups_status": classification.status,
                    "groups_reason": classification.reason,
                    "groups_error_type": classification.error_type,
                }
            )
            continue
        rows.append(
            {
                "id": getattr(category, "id", None),
                "name": getattr(category, "name", "") or "",
                "self_signup": getattr(category, "self_signup", None),
                "group_count": len(groups),
                "member_count": sum(
                    int(getattr(group, "members_count", 0) or 0) for group in groups
                ),
                "groups": [
                    {
                        "id": getattr(group, "id", None),
                        "name": getattr(group, "name", "") or "",
                        "members_count": getattr(group, "members_count", None),
                    }
                    for group in groups
                ],
                "groups_status": "available",
            }
        )
    rows.sort(key=lambda row: str(row["name"]))
    if not nested_failures:
        return available(rows)
    reasons = {failure.status for failure in nested_failures}
    reason = (
        "nested_collection_unavailable"
        if reasons == {"unavailable"}
        else "nested_collection_failed"
    )
    error_types = {failure.error_type for failure in nested_failures}
    return CollectionResult(
        items=rows,
        status="partial",
        reason=reason,
        error_type=next(iter(error_types)) if len(error_types) == 1 else "CanvasException",
    )


COLLECTION_SPECS = (
    CollectionSpec("assignment_groups", True, collect_assignment_groups),
    CollectionSpec("assignments", True, collect_assignments, ("assignment_groups",)),
    CollectionSpec("folders", False, collect_folders),
    CollectionSpec("files", False, collect_files, ("folders",)),
    CollectionSpec("discussions", False, collect_discussions),
    CollectionSpec("announcements", False, collect_announcements),
    CollectionSpec("quizzes", False, collect_quizzes),
    CollectionSpec("pages", False, collect_pages),
    CollectionSpec("group_categories", False, collect_group_categories),
)
