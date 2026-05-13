"""Canvas gradebook export parsing and audit helpers."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

TOTAL_VARIANTS = [
    "Unposted Final Score",
    "Final Score",
    "Unposted Current Score",
    "Current Score",
]
GRADE_VARIANTS = [
    "Unposted Final Grade",
    "Final Grade",
    "Unposted Current Grade",
    "Current Grade",
]
GROUP_VARIANTS = [
    "Unposted Final Score",
    "Final Score",
    "Unposted Current Score",
    "Current Score",
]
METADATA_COLUMNS = {
    "Student",
    "ID",
    "SIS User ID",
    "SIS Login ID",
    "Section",
    "Email",
    "Root Account",
}
MISSING_STRINGS = {"", "N/A", "(read only)"}


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in MISSING_STRINGS:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def stats(values: Iterable[float | None]) -> dict[str, float | int | None]:
    nums = sorted(value for value in values if value is not None)
    if not nums:
        return {"count": 0, "mean": None, "min": None, "max": None}
    return {
        "count": len(nums),
        "mean": sum(nums) / len(nums),
        "min": nums[0],
        "max": nums[-1],
    }


class CanvasGradebook:
    def __init__(
        self,
        path: Path,
        headers: list[str],
        points: list[str],
        rows: list[list[str]],
        points_row_index: int,
    ) -> None:
        self.path = path
        self.headers = headers
        self.points = points
        self.rows = rows
        self.points_row_index = points_row_index

    @classmethod
    def read(cls, path: Path, exclude_patterns: list[str] | None = None) -> CanvasGradebook:
        raw_rows = list(csv.reader(path.open(newline="", encoding="utf-8-sig")))
        if len(raw_rows) < 3:
            raise ValueError(f"{path} does not look like a Canvas gradebook export")
        headers = raw_rows[0]
        points_idx = next(
            (
                idx
                for idx, row in enumerate(raw_rows[:8])
                if row and row[0].strip().lower().startswith("points possible")
            ),
            None,
        )
        if points_idx is None:
            raise ValueError(f"Could not find Points Possible row in {path}")
        points = pad_row(raw_rows[points_idx], len(headers))
        compiled = [re.compile(pattern) for pattern in exclude_patterns or []]
        rows = []
        student_idx = headers.index("Student") if "Student" in headers else None
        for row in raw_rows[points_idx + 1 :]:
            if not row:
                continue
            row = pad_row(row, len(headers))
            student = row[student_idx].strip() if student_idx is not None else ""
            if any(pattern.search(student) for pattern in compiled):
                continue
            rows.append(row)
        return cls(path, headers, points, rows, points_idx)

    def choose_final_score_column(self, requested: str | None = None) -> tuple[str, int]:
        candidates = [requested] if requested else []
        candidates += [candidate for candidate in TOTAL_VARIANTS if candidate not in candidates]
        for candidate in candidates:
            if candidate and candidate in self.headers:
                return candidate, self.headers.index(candidate)
        raise ValueError("No Canvas final score column found")

    def choose_final_grade_column(self) -> str | None:
        return next((candidate for candidate in GRADE_VARIANTS if candidate in self.headers), None)

    def discover_groups(self) -> dict[str, dict[str, int]]:
        groups: dict[str, dict[str, int]] = {}
        for idx, header in enumerate(self.headers):
            if header in TOTAL_VARIANTS:
                continue
            for variant in GROUP_VARIANTS:
                suffix = f" {variant}"
                if header.endswith(suffix):
                    group = header[: -len(suffix)]
                    groups.setdefault(group, {})[variant] = idx
                    break
        return groups

    def assignment_columns(self) -> list[int]:
        first_group_col = min(
            [
                idx
                for idx, header in enumerate(self.headers)
                if any(header.endswith(f" {variant}") for variant in GROUP_VARIANTS)
            ]
            or [len(self.headers)]
        )
        out = []
        for idx, header in enumerate(self.headers[:first_group_col]):
            if header in METADATA_COLUMNS:
                continue
            if parse_number(self.points[idx] if idx < len(self.points) else "") is not None:
                out.append(idx)
        return out


def pad_row(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return [*row, *("" for _ in range(width - len(row)))]
    return row[:width]


def load_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Policy file must contain a mapping: {path}")
    return data


def weights_from_policy(policy: dict[str, Any]) -> dict[str, float]:
    raw = policy.get("weights") or policy.get("assignment_groups") or {}
    if isinstance(raw, list):
        raw = {str(item["name"]): item.get("weight") for item in raw if isinstance(item, dict)}
    return {str(name): float(weight) for name, weight in raw.items() if weight is not None}


def check_gradebook(
    gradebook: CanvasGradebook, *, final_score_column: str | None = None
) -> dict[str, Any]:
    final_name, _final_idx = gradebook.choose_final_score_column(final_score_column)
    final_grade = gradebook.choose_final_grade_column()
    assignment_cols = gradebook.assignment_columns()
    groups = gradebook.discover_groups()
    missing = missing_summary(gradebook, assignment_cols)
    variant_summary, variant_diff_rows = score_variant_summary(gradebook)
    return {
        "source": str(gradebook.path),
        "structure": {
            "included_rows": len(gradebook.rows),
            "columns": len(gradebook.headers),
            "points_possible_row_index": gradebook.points_row_index,
            "id_column_present": "ID" in gradebook.headers,
            "student_column_present": "Student" in gradebook.headers,
            "final_score_column": final_name,
            "final_grade_column": final_grade,
        },
        "assignments": {
            "detected_columns": len(assignment_cols),
            "detected_groups": len(groups),
        },
        "missing": missing,
        "score_variants": {
            "variants": variant_summary,
            "rows_with_differences": variant_diff_rows,
        },
    }


def missing_summary(gradebook: CanvasGradebook, assignment_cols: list[int]) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    by_column: dict[str, dict[str, int]] = {}
    for idx in assignment_cols:
        possible = parse_number(gradebook.points[idx] if idx < len(gradebook.points) else "")
        numeric_values = [
            parse_number(row[idx] if idx < len(row) else "") for row in gradebook.rows
        ]
        if possible == 0 and all(value is None for value in numeric_values):
            continue
        counts: Counter[str] = Counter()
        for row in gradebook.rows:
            raw = (row[idx] if idx < len(row) else "").strip()
            if raw == "":
                counts["blank"] += 1
            elif raw == "N/A":
                counts["N/A"] += 1
            elif parse_number(raw) is None:
                counts["nonnumeric"] += 1
        if counts:
            by_column[gradebook.headers[idx]] = dict(counts)
            totals.update(counts)
    return {"totals": dict(totals), "by_column": by_column}


def score_variant_summary(gradebook: CanvasGradebook) -> tuple[dict[str, Any], int]:
    variants = [variant for variant in TOTAL_VARIANTS if variant in gradebook.headers]
    values_by_variant = {
        variant: [parse_number(row[gradebook.headers.index(variant)]) for row in gradebook.rows]
        for variant in variants
    }
    diff_rows = 0
    for row_idx in range(len(gradebook.rows)):
        values = [values_by_variant[variant][row_idx] for variant in variants]
        if len(set(values)) > 1:
            diff_rows += 1
    return {variant: stats(values) for variant, values in values_by_variant.items()}, diff_rows


def audit_gradebook(
    gradebook: CanvasGradebook,
    *,
    policy: dict[str, Any] | None = None,
    assignment_weights: dict[str, float] | None = None,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    policy = policy or {}
    weights = weights_from_policy(policy) or assignment_weights or {}
    final_name, final_idx = gradebook.choose_final_score_column(policy.get("final_score_column"))
    groups = gradebook.discover_groups()
    matched = match_group_columns(groups, weights, final_name)
    reconstruction = reconstruct_scores(
        gradebook,
        final_idx,
        matched,
        weights,
        policy.get("final_score_reconstruction") or {},
        tolerance,
    )
    return {
        "source": str(gradebook.path),
        "final_score_column": final_name,
        "weights": weights,
        "weight_sum": sum(weights.values()),
        "matched_group_columns": {group: gradebook.headers[idx] for group, idx in matched.items()},
        "missing_weight_groups": [group for group in weights if group not in matched],
        "extra_canvas_groups": [group for group in groups if group not in weights],
        "reconstruction": reconstruction,
        "component_summary": {
            group: stats([parse_number(row[idx]) for row in gradebook.rows])
            for group, idx in matched.items()
        },
    }


def match_group_columns(
    groups: dict[str, dict[str, int]],
    weights: dict[str, float],
    final_score_column: str,
) -> dict[str, int]:
    preferred_variant = (
        final_score_column if final_score_column in GROUP_VARIANTS else GROUP_VARIANTS[0]
    )
    matched = {}
    for group in weights:
        cols = groups.get(group)
        if not cols:
            continue
        for variant in [
            preferred_variant,
            *[item for item in GROUP_VARIANTS if item != preferred_variant],
        ]:
            if variant in cols:
                matched[group] = cols[variant]
                break
    return matched


def reconstruct_scores(
    gradebook: CanvasGradebook,
    final_idx: int,
    matched: dict[str, int],
    weights: dict[str, float],
    reconstruction: dict[str, Any],
    tolerance: float,
) -> dict[str, Any]:
    target_idx, base_assignment = reconstruction_target(gradebook, final_idx, reconstruction)
    adjustment_names, adjustment_indices, missing_adjustments = adjustment_columns(
        gradebook,
        reconstruction,
    )
    diffs, skipped = reconstruction_diffs(
        gradebook,
        final_idx,
        target_idx,
        base_assignment,
        matched,
        weights,
        adjustment_indices,
    )
    return reconstruction_summary(
        gradebook,
        target_idx,
        base_assignment,
        adjustment_names,
        missing_adjustments,
        diffs,
        skipped,
        tolerance,
    )


def reconstruction_target(
    gradebook: CanvasGradebook,
    final_idx: int,
    reconstruction: dict[str, Any],
) -> tuple[int, str | None]:
    base_assignment = reconstruction.get("base_assignment")
    if isinstance(base_assignment, str) and base_assignment in gradebook.headers:
        return gradebook.headers.index(base_assignment), base_assignment
    return final_idx, None


def adjustment_columns(
    gradebook: CanvasGradebook,
    reconstruction: dict[str, Any],
) -> tuple[list[str], list[int], list[str]]:
    adjustment_names = [str(name) for name in reconstruction.get("adjustment_assignments") or []]
    adjustment_indices = [
        gradebook.headers.index(name) for name in adjustment_names if name in gradebook.headers
    ]
    missing_adjustments = [name for name in adjustment_names if name not in gradebook.headers]
    return adjustment_names, adjustment_indices, missing_adjustments


def reconstruction_diffs(
    gradebook: CanvasGradebook,
    final_idx: int,
    target_idx: int,
    base_assignment: str | None,
    matched: dict[str, int],
    weights: dict[str, float],
    adjustment_indices: list[int],
) -> tuple[list[float], int]:
    diffs = []
    skipped = 0
    for row in gradebook.rows:
        score = row_base_score(row, target_idx, base_assignment, matched, weights)
        final = parse_number(row[final_idx])
        if score is None or final is None:
            skipped += 1
            continue
        for idx in adjustment_indices:
            score += parse_number(row[idx]) or 0
        diffs.append(score - final)
    return diffs, skipped


def row_base_score(
    row: list[str],
    target_idx: int,
    base_assignment: str | None,
    matched: dict[str, int],
    weights: dict[str, float],
) -> float | None:
    if base_assignment:
        return parse_number(row[target_idx])
    score = 0.0
    for group, idx in matched.items():
        value = parse_number(row[idx])
        if value is None:
            return None
        score += value * weights[group] / 100
    return score


def reconstruction_summary(
    gradebook: CanvasGradebook,
    target_idx: int,
    base_assignment: str | None,
    adjustment_names: list[str],
    missing_adjustments: list[str],
    diffs: list[float],
    skipped: int,
    tolerance: float,
) -> dict[str, Any]:
    abs_diffs = [abs(diff) for diff in diffs]
    rows_over = sum(1 for diff in abs_diffs if diff > tolerance)
    return {
        "target": gradebook.headers[target_idx],
        "posted_method": "base plus adjustments" if base_assignment else "weighted groups",
        "adjustment_assignments": [
            name for name in adjustment_names if name not in missing_adjustments
        ],
        "missing_adjustment_assignments": missing_adjustments,
        "rows_compared": len(diffs),
        "rows_skipped": skipped,
        "mean_abs_diff": sum(abs_diffs) / len(abs_diffs) if abs_diffs else None,
        "max_abs_diff": max(abs_diffs) if abs_diffs else None,
        "rows_over_tolerance": rows_over,
        "tolerance": tolerance,
        "status": "matches" if rows_over == 0 else "differs",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
