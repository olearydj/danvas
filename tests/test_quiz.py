from pathlib import Path

from danvas.quiz import analyze_student_analysis
from tests.fixtures import write_quiz_fixture


def test_quiz_analysis_discovers_question_pairs_and_answer_counts(tmp_path: Path) -> None:
    path = tmp_path / "student-analysis.csv"
    write_quiz_fixture(path)

    payload = analyze_student_analysis(path, answer_terms=["which version", "comp"])

    assert payload["rows"]["students"] == 2
    assert len(payload["questions"]) == 2
    assert payload["score_summary"]["earned"]["mean"] == 1.5
    assert payload["answer_counts"]["which version comp"] == {"Python": 1, "Other": 1}
