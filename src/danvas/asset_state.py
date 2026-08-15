"""Typed internal state for authored-asset transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

PlanStatus = Literal[
    "blocked",
    "planned",
    "would_reuse",
    "deployed",
    "failed",
    "indeterminate",
    "created",
    "updated",
    "readback_mismatch",
    "readback_indeterminate",
    "content_failed",
    "content_indeterminate",
]
AssetStatus = Literal[
    "blocked",
    "conflict",
    "would_reuse",
    "would_upload",
    "would_rename",
    "reused",
    "uploaded",
    "renamed",
    "failed",
    "indeterminate",
]
MutationStatus = Literal[
    "not_started",
    "not_needed",
    "in_progress",
    "succeeded",
    "failed",
    "partial",
    "indeterminate",
]
EvidenceStatus = Literal[
    "not_started",
    "in_progress",
    "complete",
    "failed",
    "indeterminate",
    "partial",
    "not_available",
]
VerificationStatus = Literal["not_checked", "matches", "mismatch", "indeterminate"]

PLAN_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "blocked": frozenset(),
    "planned": frozenset({"blocked", "would_reuse", "deployed", "failed", "indeterminate"}),
    "would_reuse": frozenset({"deployed", "failed"}),
    "deployed": frozenset(
        {
            "created",
            "updated",
            "readback_mismatch",
            "readback_indeterminate",
            "content_failed",
            "content_indeterminate",
        }
    ),
    "failed": frozenset(),
    "indeterminate": frozenset(),
    "created": frozenset(),
    "updated": frozenset(),
    "readback_mismatch": frozenset(),
    "readback_indeterminate": frozenset(),
    "content_failed": frozenset(),
    "content_indeterminate": frozenset(),
}
ASSET_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "blocked": frozenset({"conflict", "would_reuse", "would_upload", "would_rename"}),
    "conflict": frozenset(),
    "would_reuse": frozenset({"reused"}),
    "would_upload": frozenset({"uploaded", "renamed", "failed", "indeterminate"}),
    "would_rename": frozenset({"uploaded", "renamed", "failed", "indeterminate"}),
    "reused": frozenset(),
    "uploaded": frozenset(),
    "renamed": frozenset(),
    "failed": frozenset(),
    "indeterminate": frozenset(),
}
MUTATION_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_started": frozenset({"in_progress", "not_needed"}),
    "in_progress": frozenset(
        {"not_started", "not_needed", "succeeded", "failed", "partial", "indeterminate"}
    ),
    "not_needed": frozenset(),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "partial": frozenset(),
    "indeterminate": frozenset(),
}
EVIDENCE_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_started": frozenset({"in_progress", "complete"}),
    "in_progress": frozenset(
        {"complete", "failed", "indeterminate", "partial", "not_available"}
    ),
    "complete": frozenset(),
    "failed": frozenset(),
    "indeterminate": frozenset(),
    "partial": frozenset(),
    "not_available": frozenset(),
}
VERIFICATION_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "not_checked": frozenset({"matches", "mismatch", "indeterminate"}),
    "matches": frozenset(),
    "mismatch": frozenset(),
    "indeterminate": frozenset(),
}


def require_transition(
    vocabulary: dict[str, frozenset[str]],
    current: str,
    target: str,
    *,
    dimension: str,
) -> None:
    if target == current:
        return
    if target not in vocabulary.get(current, frozenset()):
        raise ValueError(f"Invalid {dimension} transition: {current} -> {target}")


class AssetPublicEvidence(TypedDict, total=False):
    evidence_schema: str
    status: str
    course_id: int
    source: str
    source_body_sha256: str
    deployed_body_sha256: str | None
    deployed_body_status: str
    destination: dict[str, Any] | None
    mutation_status: str
    content_mutation_status: str
    evidence_status: str
    verification_status: str
    verification: dict[str, Any] | None
    content_error: str | None
    verification_error: str | None
    recovery_guidance: str | None
    assets: list[dict[str, Any]]
    blocked: list[dict[str, Any]]


@dataclass(frozen=True)
class AssetOccurrence:
    occurrence: int
    tag: str
    attribute: str
    fragment: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> AssetOccurrence:
        return cls(
            occurrence=int(value["occurrence"]),
            tag=str(value["tag"]),
            attribute=str(value["attribute"]),
            fragment=str(value.get("fragment") or ""),
        )

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def public_dict(self, *, include_position: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tag": self.tag,
            "attribute": self.attribute,
            "fragment": self.fragment,
        }
        if include_position:
            result["occurrence"] = self.occurrence
        return result


@dataclass(frozen=True)
class LocalAssetIdentity:
    path: str
    source_path: Path
    sha256: str
    size: int
    content_type: str
    name: str


@dataclass
class CanvasFileIdentity:
    course_id: int
    id: int
    folder_id: int | None
    path: str
    url: str
    display_name: str = ""
    present_fields: set[str] = field(default_factory=set, repr=False)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> CanvasFileIdentity:
        identity = cls(
            course_id=int(value["course_id"]),
            id=int(value["id"]),
            folder_id=(int(value["folder_id"]) if value.get("folder_id") is not None else None),
            path=str(value.get("path") or ""),
            url=str(value.get("url") or ""),
            display_name=str(value.get("display_name") or ""),
        )
        identity.present_fields.update(value)
        return identity

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if not hasattr(self, key):
            raise KeyError(key)
        setattr(self, key, value)
        self.present_fields.add(key)

    def to_dict(self) -> dict[str, Any]:
        values = {
            "course_id": self.course_id,
            "id": self.id,
            "folder_id": self.folder_id,
            "path": self.path,
            "url": self.url,
            "display_name": self.display_name,
        }
        return {
            key: value
            for key, value in values.items()
            if not self.present_fields or key in self.present_fields
        }


@dataclass(frozen=True)
class AssetDestination:
    id: int | None
    full_name: str

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "full_name": self.full_name}


@dataclass
class AssetItem:
    local: LocalAssetIdentity
    occurrences: list[AssetOccurrence]
    status: AssetStatus = "blocked"
    reason: str = ""
    existing_canvas_ids: list[int] = field(default_factory=list)
    mutation_status: MutationStatus | None = None
    evidence_status: EvidenceStatus | None = None
    canvas: CanvasFileIdentity | None = None
    mapping: dict[str, Any] | None = None
    present_fields: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        require_known_status(ASSET_STATUS_TRANSITIONS, self.status, dimension="asset status")
        if self.mutation_status is not None:
            require_known_status(
                MUTATION_STATUS_TRANSITIONS,
                self.mutation_status,
                dimension="asset mutation status",
            )
        if self.evidence_status is not None:
            require_known_status(
                EVIDENCE_STATUS_TRANSITIONS,
                self.evidence_status,
                dimension="asset evidence status",
            )

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "status" and key in self.__dict__:
            require_transition(
                ASSET_STATUS_TRANSITIONS,
                str(self.__dict__[key]),
                str(value),
                dimension="asset status",
            )
        object.__setattr__(self, key, value)

    @classmethod
    def from_scan_record(cls, value: dict[str, Any]) -> AssetItem:
        item = cls(
            local=LocalAssetIdentity(
                path=str(value["path"]),
                source_path=Path(str(value["source_path"])),
                sha256=str(value["sha256"]),
                size=int(value["size"]),
                content_type=str(value["content_type"]),
                name=str(value["name"]),
            ),
            occurrences=[AssetOccurrence.from_mapping(row) for row in value["occurrences"]],
            status=cast(AssetStatus, value.get("status") or "blocked"),
            reason=str(value.get("reason") or ""),
        )
        item.present_fields.update(value)
        return item

    @property
    def occurrence_count(self) -> int:
        return len(self.occurrences)

    def _value(self, key: str) -> Any:
        if hasattr(self.local, key):
            value = getattr(self.local, key)
            return str(value) if key == "source_path" else value
        if key == "occurrence_count":
            return self.occurrence_count
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self._value(key)
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        return self._value(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "status":
            require_transition(
                ASSET_STATUS_TRANSITIONS,
                self.status,
                str(value),
                dimension="asset status",
            )
            self.status = cast(AssetStatus, value)
        elif key == "reason":
            self.reason = str(value)
        elif key == "existing_canvas_ids":
            self.existing_canvas_ids = [int(item) for item in value]
        elif key == "mutation_status":
            require_known_status(
                MUTATION_STATUS_TRANSITIONS,
                str(value),
                dimension="asset mutation status",
            )
            self.mutation_status = cast(MutationStatus, value)
        elif key == "evidence_status":
            require_known_status(
                EVIDENCE_STATUS_TRANSITIONS,
                str(value),
                dimension="asset evidence status",
            )
            self.evidence_status = cast(EvidenceStatus, value)
        elif key == "canvas":
            self.canvas = (
                value if isinstance(value, CanvasFileIdentity) else CanvasFileIdentity.from_mapping(value)
            )
        elif key == "mapping":
            self.mapping = value
        else:
            raise KeyError(key)
        self.present_fields.add(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self.present_fields or hasattr(self.local, key) or key in {
            "occurrences",
            "occurrence_count",
        }

    def update(self, value: dict[str, Any]) -> None:
        for key, item in value.items():
            self[key] = item

    def signature_dict(self) -> dict[str, Any]:
        return {
            "path": self.local.path,
            "sha256": self.local.sha256,
            "size": self.local.size,
            "content_type": self.local.content_type,
            "name": self.local.name,
            "occurrences": [row.public_dict() for row in self.occurrences],
        }


@dataclass
class AssetRuntime:
    source_html: str
    source_path: Path
    project_root: Path
    source_file_sha256: str
    canvas_origin: str
    canvas: Any | None = None
    course: Any | None = None
    folder: Any | None = None
    report_run: Any | None = None


@dataclass
class AssetVerification:
    status: VerificationStatus
    expected: list[dict[str, Any]] = field(default_factory=list)
    actual: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[dict[str, Any]] = field(default_factory=list)
    expected_invalid: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    remote_bytes_match: str = "not_checked"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> AssetVerification:
        return cls(
            status=cast(VerificationStatus, value["status"]),
            expected=list(value.get("expected") or []),
            actual=list(value.get("actual") or []),
            invalid=list(value.get("invalid") or []),
            expected_invalid=list(value.get("expected_invalid") or []),
            files=list(value.get("files") or []),
            remote_bytes_match=str(value.get("remote_bytes_match") or "not_checked"),
        )

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "invalid": self.invalid,
            "expected_invalid": self.expected_invalid,
            "files": self.files,
            "remote_bytes_match": self.remote_bytes_match,
        }


@dataclass
class AssetPlan:
    evidence_schema: str
    status: PlanStatus
    course_id: int
    source: str
    source_body_sha256: str
    assets: list[AssetItem]
    blocked: list[dict[str, Any]]
    runtime: AssetRuntime
    deployed_body_sha256: str | None = None
    destination: AssetDestination | None = None
    rewritten_html: str | None = None
    mutation_status: MutationStatus = "not_started"
    content_mutation_status: MutationStatus = "not_started"
    evidence_status: EvidenceStatus = "not_started"
    verification_status: VerificationStatus = "not_checked"
    verification: AssetVerification | None = None
    content_error: str | None = None
    verification_error: str | None = None
    recovery_guidance: str | None = None

    def __post_init__(self) -> None:
        require_known_status(PLAN_STATUS_TRANSITIONS, self.status, dimension="plan status")
        require_known_status(
            MUTATION_STATUS_TRANSITIONS,
            self.mutation_status,
            dimension="mutation status",
        )
        require_known_status(
            MUTATION_STATUS_TRANSITIONS,
            self.content_mutation_status,
            dimension="content mutation status",
        )
        require_known_status(
            EVIDENCE_STATUS_TRANSITIONS,
            self.evidence_status,
            dimension="evidence status",
        )
        require_known_status(
            VERIFICATION_STATUS_TRANSITIONS,
            self.verification_status,
            dimension="verification status",
        )

    def __setattr__(self, key: str, value: Any) -> None:
        transitions = {
            "status": (PLAN_STATUS_TRANSITIONS, "plan status"),
            "mutation_status": (MUTATION_STATUS_TRANSITIONS, "mutation status"),
            "content_mutation_status": (
                MUTATION_STATUS_TRANSITIONS,
                "content mutation status",
            ),
            "evidence_status": (EVIDENCE_STATUS_TRANSITIONS, "evidence status"),
            "verification_status": (
                VERIFICATION_STATUS_TRANSITIONS,
                "verification status",
            ),
        }
        if key in transitions and key in self.__dict__:
            vocabulary, dimension = transitions[key]
            require_transition(vocabulary, str(self.__dict__[key]), str(value), dimension=dimension)
        object.__setattr__(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if not hasattr(self, key) or key == "runtime":
            raise KeyError(key)
        if key == "status":
            require_transition(
                PLAN_STATUS_TRANSITIONS,
                self.status,
                str(value),
                dimension="plan status",
            )
            value = cast(PlanStatus, value)
        elif key in {"mutation_status", "content_mutation_status"}:
            value = cast(MutationStatus, value)
        elif key == "evidence_status":
            value = cast(EvidenceStatus, value)
        elif key == "verification_status":
            value = cast(VerificationStatus, value)
        elif key == "verification" and isinstance(value, dict):
            value = AssetVerification.from_mapping(value)
        setattr(self, key, value)

    def update(self, value: dict[str, Any]) -> None:
        for key, item in value.items():
            self[key] = item


@dataclass(frozen=True)
class AssetTransitionResult:
    stop: bool
    reason: str = ""


def require_known_status(
    vocabulary: dict[str, frozenset[str]], value: str, *, dimension: str
) -> None:
    if value not in vocabulary:
        raise ValueError(f"Unknown {dimension}: {value}")
