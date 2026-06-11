"""Canvas Classic Quiz/Survey student-analysis CSV helpers."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from danvas.gradebook import parse_number, stats

BASE_FIELDS = ["name", "id", "sis_id", "section", "section_id", "section_sis_id", "submitted"]
SUMMARY_FIELDS = ["n correct", "n incorrect", "score"]


def clean_question(header: str) -> tuple[str | None, str]:
    text = str(header).strip()
    match = re.match(r"^(\d+):\s*(.*)$", text, flags=re.S)
    if match:
        return match.group(1), re.sub(r"\s+", " ", match.group(2)).strip()
    return None, re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class QuestionPair:
    question_index: int
    score_index: int
    question_id: str | None
    question_text: str
    points_possible: float


class StudentAnalysisReport:
    def __init__(self, path: Path):
        self.path = path
        with path.open(newline="", encoding="utf-8-sig") as handle:
            self.rows = list(csv.reader(handle))
        if not self.rows:
            raise ValueError(f"Empty report: {path}")
        self.headers = self.rows[0]
        self.data_rows = self.rows[1:]
        self.header_index = {header: idx for idx, header in enumerate(self.headers)}
        self.question_pairs = self._discover_question_pairs()

    def _discover_question_pairs(self) -> list[QuestionPair]:
        pairs = []
        stop = len(self.headers)
        for field in SUMMARY_FIELDS:
            if field in self.header_index:
                stop = min(stop, self.header_index[field])
        submitted_idx = self.header_index.get("submitted")
        idx = submitted_idx + 1 if submitted_idx is not None else len(BASE_FIELDS)
        while idx + 1 < stop:
            points_possible = parse_number(self.headers[idx + 1])
            if points_possible is not None:
                qid, qtext = clean_question(self.headers[idx])
                pairs.append(QuestionPair(idx, idx + 1, qid, qtext, points_possible))
                idx += 2
            else:
                idx += 1
        return pairs

    def iter_rows(self) -> Iterable[list[str]]:
        for row in self.data_rows:
            if len(row) < len(self.headers):
                row = [*row, *("" for _ in range(len(self.headers) - len(row)))]
            yield row[: len(self.headers)]

    def base_value(self, row: list[str], field: str) -> str:
        idx = self.header_index.get(field)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    def answer_for(
        self, row: list[str], include: list[str], exclude: list[str] | None = None
    ) -> str:
        include_l = [term.lower() for term in include]
        exclude_l = [term.lower() for term in (exclude or [])]
        for pair in self.question_pairs:
            text_l = pair.question_text.lower()
            if all(term in text_l for term in include_l) and not any(
                term in text_l for term in exclude_l
            ):
                return row[pair.question_index].strip() if pair.question_index < len(row) else ""
        return ""

    def scored_points(self, row: list[str]) -> tuple[float, float, int]:
        earned = 0.0
        possible = 0.0
        count = 0
        for pair in self.question_pairs:
            if pair.points_possible <= 0 or pair.score_index >= len(row):
                continue
            score = parse_number(row[pair.score_index].strip())
            if score is None:
                continue
            earned += score
            possible += pair.points_possible
            count += 1
        return earned, possible, count


def analyze_student_analysis(path: Path, answer_terms: list[str] | None = None) -> dict[str, Any]:
    report = StudentAnalysisReport(path)
    rows = list(report.iter_rows())
    submitted = [row for row in rows if report.base_value(row, "submitted")]
    scores = [report.scored_points(row) for row in rows]
    earned = [score[0] for score in scores if score[2] > 0]
    possible = [score[1] for score in scores if score[2] > 0]
    payload: dict[str, Any] = {
        "source": str(path),
        "rows": {
            "students": len(rows),
            "submitted": len(submitted),
            "missing_submissions": len(rows) - len(submitted),
        },
        "questions": [
            {
                "question_id": pair.question_id,
                "question_text": pair.question_text,
                "points_possible": pair.points_possible,
            }
            for pair in report.question_pairs
        ],
        "score_summary": {
            "earned": stats(earned),
            "possible_max": max(possible) if possible else None,
        },
    }
    if answer_terms:
        counts: dict[str, int] = {}
        for row in rows:
            answer = report.answer_for(row, answer_terms).strip() or "blank"
            counts[answer] = counts.get(answer, 0) + 1
        payload["answer_counts"] = {" ".join(answer_terms): counts}
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
