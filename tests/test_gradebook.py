import csv
from pathlib import Path

import pytest

from danvas.gradebook import (
    CanvasGradebook,
    audit_gradebook,
    check_gradebook,
    resolve_gradebook_heading_aliases,
)
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


def test_audit_gradebook_detects_reconstruction_difference(tmp_path: Path) -> None:
    path = tmp_path / "gradebook.csv"
    write_gradebook_fixture(path)
    text = path.read_text(encoding="utf-8").replace('"Doe, Jane",1,90,90,80,85', '"Doe, Jane",1,90,90,80,70')
    path.write_text(text, encoding="utf-8")
    gradebook = CanvasGradebook.read(path, exclude_patterns=["^Student, Test$"])

    payload = audit_gradebook(
        gradebook,
        policy={
            "final_score_column": "Unposted Final Score",
            "weights": {"Homework": 50, "Tests": 50, "Missing": 10},
        },
    )

    assert payload["missing_weight_groups"] == ["Missing"]
    assert payload["reconstruction"]["status"] == "differs"
    assert payload["reconstruction"]["max_abs_diff"] == 15
    assert payload["reconstruction"]["rows_over_tolerance"] == 1


def write_aliased_gradebook(path: Path) -> dict[str, list[str]]:
    aliases = {
        "student": ["Étudiant"],
        "id": ["Identifiant"],
        "points_possible": ["Points possibles"],
        "unposted_final_score": ["Note finale non publiée"],
        "final_score": ["Note finale"],
        "unposted_final_grade": ["Évaluation finale non publiée"],
        "sis_login_id": ["Identifiant de connexion"],
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                " Étudiant ",
                "Identifiant",
                "Identifiant de connexion",
                "Devoir (1)",
                "Travaux Note finale non publiée",
                "Note finale non publiée",
                "Évaluation finale non publiée",
            ]
        )
        writer.writerow(["Points possibles", "", "", "10", "", "", ""])
        writer.writerow(["Apprenant Exemple", "1", "login@example.edu", "9", "90", "90", "A"])
    return aliases


def test_gradebook_aliases_cover_metadata_points_scores_grades_and_groups(
    tmp_path: Path,
) -> None:
    path = tmp_path / "gradebook.csv"
    aliases = write_aliased_gradebook(path)

    gradebook = CanvasGradebook.read(path, heading_aliases=aliases)
    checked = check_gradebook(gradebook)
    audited = audit_gradebook(gradebook, policy={"weights": {"Travaux": 100}})

    assert checked["structure"]["student_column_present"] is True
    assert checked["structure"]["id_column_present"] is True
    assert checked["structure"]["final_score_column"] == "Note finale non publiée"
    assert checked["structure"]["final_grade_column"] == "Évaluation finale non publiée"
    assert checked["assignments"]["detected_columns"] == 1
    assert audited["matched_group_columns"] == {
        "Travaux": "Travaux Note finale non publiée"
    }
    assert audited["reconstruction"]["status"] == "matches"


def test_exact_requested_observed_heading_wins_after_alias_resolution(tmp_path: Path) -> None:
    path = tmp_path / "gradebook.csv"
    aliases = write_aliased_gradebook(path)
    gradebook = CanvasGradebook.read(path, heading_aliases=aliases)

    assert gradebook.choose_final_score_column("Note finale non publiée") == (
        "Note finale non publiée",
        5,
    )


def test_gradebook_alias_cannot_map_to_multiple_roles() -> None:
    with pytest.raises(ValueError, match="maps to multiple canonical roles"):
        resolve_gradebook_heading_aliases(
            {"student": ["Identité"], "id": ["Identité"]}
        )


def test_gradebook_rejects_unknown_alias_role() -> None:
    with pytest.raises(ValueError, match="gradebook_heading_aliases.typo"):
        resolve_gradebook_heading_aliases({"typo": ["Heading"]})


def test_gradebook_rejects_multiple_observed_headers_for_one_role(tmp_path: Path) -> None:
    path = tmp_path / "gradebook.csv"
    path.write_text(
        "Student,Étudiant,ID,Unposted Final Score\n"
        "Points Possible,,,\n"
        "PRIVATE STUDENT NAME,OTHER PRIVATE NAME,1,90\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        CanvasGradebook.read(path, heading_aliases={"student": ["Étudiant"]})

    message = str(exc_info.value)
    assert "role 'student' is ambiguous" in message
    assert "Student" in message
    assert "Étudiant" in message
    assert "PRIVATE STUDENT NAME" not in message


def test_missing_points_and_final_score_diagnostics_are_bounded_and_row_free(
    tmp_path: Path,
) -> None:
    missing_points = tmp_path / "missing-points.csv"
    missing_points.write_text(
        "Student,ID,Assignment\n"
        "Possible Points,,10\n"
        "PRIVATE STUDENT NAME,1,9\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as points_error:
        CanvasGradebook.read(missing_points)
    assert "points_possible" in str(points_error.value)
    assert "Points Possible" in str(points_error.value)
    assert "PRIVATE STUDENT NAME" not in str(points_error.value)

    missing_final = tmp_path / "missing-final.csv"
    missing_final.write_text(
        "Student,ID,Assignment\n"
        "Points Possible,,10\n"
        "PRIVATE STUDENT NAME,1,9\n",
        encoding="utf-8",
    )
    gradebook = CanvasGradebook.read(missing_final)
    with pytest.raises(ValueError) as final_error:
        gradebook.choose_final_score_column()
    assert "final score" in str(final_error.value)
    assert "Unposted Final Score" in str(final_error.value)
    assert "PRIVATE STUDENT NAME" not in str(final_error.value)
