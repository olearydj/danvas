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


def test_quiz_analysis_locates_questions_after_submitted_column(tmp_path: Path) -> None:
    path = tmp_path / "student-analysis.csv"
    path.write_text(
        "name,id,sis_id,section,section_id,submitted,124: Knowledge,2,n correct,n incorrect,score\n"
        "Doe Jane,10,,,1,2026-01-01,A,2,1,0,2\n",
        encoding="utf-8",
    )

    payload = analyze_student_analysis(path)

    assert [question["question_text"] for question in payload["questions"]] == ["Knowledge"]
    assert payload["score_summary"]["possible_max"] == 2
