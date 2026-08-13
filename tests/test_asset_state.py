from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from danvas.asset_state import (
    ASSET_STATUS_TRANSITIONS,
    EVIDENCE_STATUS_TRANSITIONS,
    MUTATION_STATUS_TRANSITIONS,
    PLAN_STATUS_TRANSITIONS,
    VERIFICATION_STATUS_TRANSITIONS,
    AssetItem,
    AssetPlan,
    AssetRuntime,
    AssetStatus,
    EvidenceStatus,
    LocalAssetIdentity,
    PlanStatus,
)

# This table is an independent compatibility contract. Do not derive it from
# the implementation: a missing production edge must make this test fail.
EXPECTED_PLAN_STATUS_TRANSITIONS = {
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
EXPECTED_ASSET_STATUS_TRANSITIONS = {
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
EXPECTED_MUTATION_STATUS_TRANSITIONS = {
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
EXPECTED_EVIDENCE_STATUS_TRANSITIONS = {
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
EXPECTED_VERIFICATION_STATUS_TRANSITIONS = {
    "not_checked": frozenset({"matches", "mismatch", "indeterminate"}),
    "matches": frozenset(),
    "mismatch": frozenset(),
    "indeterminate": frozenset(),
}


def asset_item(status: str) -> AssetItem:
    return AssetItem(
        local=LocalAssetIdentity(
            path="assets/example.pdf",
            source_path=Path("assets/example.pdf"),
            sha256="a" * 64,
            size=12,
            content_type="application/pdf",
            name="example.pdf",
        ),
        occurrences=[],
        status=cast(AssetStatus, status),
    )


def asset_plan(status: str) -> AssetPlan:
    return AssetPlan(
        evidence_schema="authored-assets-v1",
        status=cast(PlanStatus, status),
        course_id=42,
        source="content/example.md",
        source_body_sha256="b" * 64,
        assets=[],
        blocked=[],
        runtime=AssetRuntime(
            source_html="<p>Example</p>",
            source_path=Path("content/example.md"),
            project_root=Path("."),
            source_file_sha256="c" * 64,
            canvas_origin="https://canvas.test",
        ),
    )


def test_transition_vocabulary_matches_independent_contract() -> None:
    assert PLAN_STATUS_TRANSITIONS == EXPECTED_PLAN_STATUS_TRANSITIONS
    assert ASSET_STATUS_TRANSITIONS == EXPECTED_ASSET_STATUS_TRANSITIONS
    assert MUTATION_STATUS_TRANSITIONS == EXPECTED_MUTATION_STATUS_TRANSITIONS
    assert EVIDENCE_STATUS_TRANSITIONS == EXPECTED_EVIDENCE_STATUS_TRANSITIONS
    assert VERIFICATION_STATUS_TRANSITIONS == EXPECTED_VERIFICATION_STATUS_TRANSITIONS


def test_required_reuse_failure_transition_is_constructible() -> None:
    plan = asset_plan("would_reuse")
    plan.status = "failed"
    assert plan.status == "failed"


def test_undeclared_transitions_are_rejected() -> None:
    plan = asset_plan("failed")
    with pytest.raises(ValueError, match="Invalid plan status transition"):
        plan.status = "deployed"

    item = asset_item("uploaded")
    with pytest.raises(ValueError, match="Invalid asset status transition"):
        item.status = "failed"

    plan = asset_plan("planned")
    with pytest.raises(ValueError, match="Invalid evidence status transition"):
        plan.evidence_status = "failed"


def test_unknown_statuses_cannot_be_constructed_or_assigned() -> None:
    with pytest.raises(ValueError, match="Unknown plan status"):
        asset_plan("invented")
    with pytest.raises(ValueError, match="Unknown asset status"):
        asset_item("invented")

    plan = asset_plan("planned")
    with pytest.raises(ValueError, match="Invalid evidence status transition"):
        plan.evidence_status = cast(EvidenceStatus, "invented")
