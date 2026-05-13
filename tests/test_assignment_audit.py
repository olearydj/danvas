from pathlib import Path

from danvas.assignment_audit import audit_assignment_file
from tests.fixtures import write_assignment_fixture


def test_assignment_audit_compares_group_weights(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    policy = tmp_path / "course.yaml"
    policy.write_text("weights:\n  Homework: 40\n  Tests: 60\n", encoding="utf-8")

    payload = audit_assignment_file(assignments, policy)

    assert payload["weight_sum"] == 100
    assert payload["missing_groups"] == []
    assert payload["assignments"]["count"] == 2
    assert payload["assignments"]["unpublished"] == ["Test 1"]
    assert payload["assignments"]["missing_due_dates"] == ["Test 1"]
