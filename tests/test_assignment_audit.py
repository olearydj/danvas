from pathlib import Path

from danvas.assignment_audit import (
    assignment_group_weights,
    audit_assignment_file,
    load_assignment_snapshot,
    render_assignment_audit_markdown,
)
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


def test_assignment_audit_reports_unavailable_expected_weights(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    policy = tmp_path / "course.yaml"
    policy.write_text("grading:\n  categories:\n    Homework: 40\n", encoding="utf-8")

    payload = audit_assignment_file(assignments, policy)
    markdown = render_assignment_audit_markdown(payload)

    assert payload["expected_weights"] == {}
    assert payload["expected_weights_status"] == "unavailable"
    assert "Expected weights unavailable" in payload["expected_weights_note"]
    assert "Expected weights unavailable" in markdown


def test_assignment_snapshot_file_preserves_top_level_groups(tmp_path: Path) -> None:
    path = tmp_path / "course.json"
    path.write_text(
        '{"assignments": [{"name": "Practice", "assignment_group_name": "Practice"}], '
        '"assignment_groups": [{"id": 9, "name": "Practice", "group_weight": 0}]}',
        encoding="utf-8",
    )

    snapshot = load_assignment_snapshot(path)

    assert snapshot["assignment_groups"] == [
        {"id": 9, "name": "Practice", "group_weight": 0}
    ]


def test_assignment_group_weights_preserves_zero_weight() -> None:
    weights = assignment_group_weights(
        {"assignment_groups": [{"name": "Practice", "group_weight": 0}]}
    )

    assert weights == {"Practice": 0.0}
