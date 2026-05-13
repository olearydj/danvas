from pathlib import Path

from danvas.gradebook import CanvasGradebook, audit_gradebook, check_gradebook
from tests.fixtures import write_gradebook_fixture


def test_check_gradebook_detects_structure_and_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "gradebook.csv"
    write_gradebook_fixture(path)

    gradebook = CanvasGradebook.read(path, exclude_patterns=["^Student, Test$"])
    payload = check_gradebook(gradebook)

    assert payload["structure"]["included_rows"] == 2
    assert payload["structure"]["final_score_column"] == "Unposted Final Score"
    assert payload["assignments"]["detected_columns"] == 1
    assert payload["assignments"]["detected_groups"] == 2
    assert payload["missing"]["totals"] == {"N/A": 1}


def test_audit_gradebook_reconstructs_weighted_total(tmp_path: Path) -> None:
    path = tmp_path / "gradebook.csv"
    write_gradebook_fixture(path)
    gradebook = CanvasGradebook.read(path, exclude_patterns=["^Student, Test$"])

    payload = audit_gradebook(
        gradebook,
        policy={
            "final_score_column": "Unposted Final Score",
            "weights": {"Homework": 50, "Tests": 50},
        },
    )

    assert payload["weight_sum"] == 100
    assert payload["matched_group_columns"] == {
        "Homework": "Homework Unposted Final Score",
        "Tests": "Tests Unposted Final Score",
    }
    assert payload["reconstruction"]["status"] == "matches"
    assert payload["reconstruction"]["max_abs_diff"] == 0
