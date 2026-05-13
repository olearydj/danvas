from pathlib import Path

from typer.testing import CliRunner

from danvas.cli import app
from tests.fixtures import write_assignment_fixture, write_gradebook_fixture, write_quiz_fixture

runner = CliRunner()


def test_gradebook_check_cli(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    policy = tmp_path / "course.yaml"
    policy.write_text('exclude_students:\n  - "^Student, Test$"\n', encoding="utf-8")

    result = runner.invoke(
        app, ["gradebook", "check", str(gradebook), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Included rows: 2" in result.output


def test_gradebook_audit_cli(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    policy = tmp_path / "course.yaml"
    policy.write_text(
        'exclude_students:\n  - "^Student, Test$"\nweights:\n  Homework: 50\n  Tests: 50\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["gradebook", "audit", str(gradebook), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Status: matches" in result.output


def test_assignments_audit_cli(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    policy = tmp_path / "course.yaml"
    policy.write_text("weights:\n  Homework: 40\n  Tests: 60\n", encoding="utf-8")

    result = runner.invoke(
        app, ["assignments", "audit", str(assignments), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Assignments: 2" in result.output


def test_quiz_analysis_cli(tmp_path: Path) -> None:
    quiz = tmp_path / "student-analysis.csv"
    write_quiz_fixture(quiz)

    result = runner.invoke(
        app,
        ["quiz", "analysis", str(quiz), "--answer-term", "which version", "--answer-term", "comp"],
    )

    assert result.exit_code == 0
    assert "Students: 2" in result.output
