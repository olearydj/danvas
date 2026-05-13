"""Assignment export and course-policy audit helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from danvas.gradebook import load_policy, weights_from_policy


def load_assignment_snapshot(path: Path) -> dict[str, Any]:
    if path.is_dir():
        course_json = path / "course.json"
        if not course_json.is_file():
            raise ValueError(f"Assignment export directory is missing course.json: {path}")
        payload = json.loads(course_json.read_text(encoding="utf-8"))
        assignments = payload.get("assignments") or []
        groups = payload.get("assignment_groups") or []
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assignments = payload if isinstance(payload, list) else payload.get("assignments", [])
        groups_by_name: dict[str, dict[str, Any]] = {}
        for assignment in assignments:
            group = assignment.get("assignment_group") or {}
            name = group.get("name") or assignment.get("assignment_group_name")
            if name and name not in groups_by_name:
                groups_by_name[name] = group or {"name": name}
        groups = list(groups_by_name.values())
    return {"source": str(path), "assignments": assignments, "assignment_groups": groups}


def assignment_group_weights(snapshot: dict[str, Any]) -> dict[str, float]:
    weights = {}
    for group in snapshot.get("assignment_groups") or []:
        name = group.get("name")
        weight = group.get("group_weight") or group.get("weight")
        if name and weight is not None:
            weights[str(name)] = float(weight)
    return weights


def audit_assignment_setup(
    snapshot: dict[str, Any], policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    policy = policy or {}
    expected = weights_from_policy(policy)
    actual = assignment_group_weights(snapshot)
    assignments = snapshot.get("assignments") or []
    group_counts: dict[str, int] = {}
    unpublished = []
    missing_due_dates = []
    for assignment in assignments:
        group_name = assignment.get("assignment_group_name")
        if not group_name and isinstance(assignment.get("assignment_group"), dict):
            group_name = assignment["assignment_group"].get("name")
        group_name = group_name or "Ungrouped/unknown"
        group_counts[group_name] = group_counts.get(group_name, 0) + 1
        if assignment.get("published") is False:
            unpublished.append(assignment.get("name") or assignment.get("id"))
        if not assignment.get("due_at"):
            missing_due_dates.append(assignment.get("name") or assignment.get("id"))
    weight_diffs = {
        group: {
            "expected": expected.get(group),
            "actual": actual.get(group),
            "diff": (actual[group] - expected[group]) if group in actual else None,
        }
        for group in expected
    }
    return {
        "source": snapshot.get("source"),
        "expected_weights": expected,
        "canvas_weights": actual,
        "weight_sum": sum(actual.values()) if actual else None,
        "missing_groups": [group for group in expected if group not in actual],
        "extra_groups": [group for group in actual if group not in expected] if expected else [],
        "weight_diffs": weight_diffs,
        "assignments": {
            "count": len(assignments),
            "by_group": group_counts,
            "unpublished": unpublished,
            "missing_due_dates": missing_due_dates,
        },
    }


def audit_assignment_file(
    assignments_path: Path, policy_path: Path | None = None
) -> dict[str, Any]:
    return audit_assignment_setup(
        load_assignment_snapshot(assignments_path), load_policy(policy_path)
    )
