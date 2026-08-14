"""Canvas gradebook export parsing and audit helpers."""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

SCORE_ROLES = (
    "unposted_final_score",
    "final_score",
    "unposted_current_score",
    "current_score",
)
GRADE_ROLES = (
    "unposted_final_grade",
    "final_grade",
    "unposted_current_grade",
    "current_grade",
)
METADATA_ROLES = (
    "student",
    "id",
    "sis_user_id",
    "sis_login_id",
    "section",
    "email",
    "root_account",
)
BUILTIN_HEADING_ROLES = {
    "student": "Student",
    "id": "ID",
    "sis_user_id": "SIS User ID",
    "sis_login_id": "SIS Login ID",
    "section": "Section",
    "email": "Email",
    "root_account": "Root Account",
    "points_possible": "Points Possible",
    "unposted_final_score": "Unposted Final Score",
    "final_score": "Final Score",
    "unposted_current_score": "Unposted Current Score",
    "current_score": "Current Score",
    "unposted_final_grade": "Unposted Final Grade",
    "final_grade": "Final Grade",
    "unposted_current_grade": "Unposted Current Grade",
    "current_grade": "Current Grade",
}
TOTAL_VARIANTS = [BUILTIN_HEADING_ROLES[role] for role in SCORE_ROLES]
GRADE_VARIANTS = [BUILTIN_HEADING_ROLES[role] for role in GRADE_ROLES]
GROUP_VARIANTS = list(TOTAL_VARIANTS)
METADATA_COLUMNS = {BUILTIN_HEADING_ROLES[role] for role in METADATA_ROLES}
GRADEBOOK_HEADING_ROLES = (*METADATA_ROLES, "points_possible", *SCORE_ROLES, *GRADE_ROLES)
MISSING_STRINGS = {"", "N/A", "(read only)"}
OBSERVED_HEADING_LIMIT = 12


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
        heading_aliases: dict[str, tuple[str, ...]] | None = None,
        role_headers: dict[str, str | None] | None = None,
    ) -> None:
        self.path = path
        self.headers = headers
        self.points = points
        self.rows = rows
        self.points_row_index = points_row_index
        self.heading_aliases = heading_aliases or resolve_gradebook_heading_aliases(None)
        self.role_headers = role_headers or resolve_observed_role_headers(
            headers, self.heading_aliases
        )

    @classmethod
    def read(
        cls,
        path: Path,
        exclude_patterns: list[str] | None = None,
        heading_aliases: Any = None,
    ) -> CanvasGradebook:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            raw_rows = list(csv.reader(handle))
        if len(raw_rows) < 3:
            raise ValueError(f"{path} does not look like a Canvas gradebook export")
        headers = raw_rows[0]
        aliases = resolve_gradebook_heading_aliases(heading_aliases)
        role_headers = resolve_observed_role_headers(headers, aliases)
        points_rows = [
            idx
            for idx, row in enumerate(raw_rows[:8])
            if row and row[0].strip() in aliases["points_possible"]
        ]
        if len(points_rows) > 1:
            raise ValueError(
                gradebook_role_error(
                    "points_possible", aliases, headers, problem="ambiguous points rows"
                )
            )
        if not points_rows:
            raise ValueError(
                gradebook_role_error(
                    "points_possible", aliases, headers, problem="missing points row"
                )
            )
        points_idx = points_rows[0]
        points = pad_row(raw_rows[points_idx], len(headers))
        compiled = [re.compile(pattern) for pattern in exclude_patterns or []]
        rows = []
        student_header = role_headers["student"]
        student_idx = headers.index(student_header) if student_header is not None else None
        for row in raw_rows[points_idx + 1 :]:
            if not row:
                continue
            row = pad_row(row, len(headers))
            student = row[student_idx].strip() if student_idx is not None else ""
            if any(pattern.search(student) for pattern in compiled):
                continue
            rows.append(row)
        return cls(
            path,
            headers,
            points,
            rows,
            points_idx,
            heading_aliases=aliases,
            role_headers=role_headers,
        )

    def choose_final_score_column(self, requested: str | None = None) -> tuple[str, int]:
        if requested:
            requested_matches = [header for header in self.headers if header.strip() == requested.strip()]
            if len(requested_matches) == 1:
                observed = requested_matches[0]
                return observed, self.headers.index(observed)
            if len(requested_matches) > 1:
                raise ValueError(
                    f"Requested final score heading is ambiguous: {requested!r}. "
                    f"Observed headings: {bounded_observed_headings(self.headers)}"
                )
        for role in SCORE_ROLES:
            observed = self.role_headers[role]
            if observed is not None:
                return observed, self.headers.index(observed)
        aliases = [alias for role in SCORE_ROLES for alias in self.heading_aliases[role]]
        raise ValueError(
            "Missing canonical gradebook role 'final score'. "
            f"Configured aliases: {aliases!r}. "
            f"Observed headings: {bounded_observed_headings(self.headers)}"
        )

    def choose_final_grade_column(self) -> str | None:
        return next(
            (self.role_headers[role] for role in GRADE_ROLES if self.role_headers[role]),
            None,
        )

    def discover_groups(self) -> dict[str, dict[str, int]]:
        groups: dict[str, dict[str, int]] = {}
        for idx, header in enumerate(self.headers):
            if header in {self.role_headers[role] for role in SCORE_ROLES}:
                continue
            normalized_header = header.strip()
            for role, variant in self.group_score_suffixes():
                suffix = f" {variant}"
                if normalized_header.endswith(suffix):
                    group = normalized_header[: -len(suffix)]
                    groups.setdefault(group, {})[role] = idx
                    break
        return groups

    def group_score_suffixes(self) -> list[tuple[str, str]]:
        suffixes = [
            (role, alias)
            for role in SCORE_ROLES
            for alias in self.heading_aliases[role]
        ]
        return sorted(suffixes, key=lambda item: len(item[1]), reverse=True)

    def assignment_columns(self) -> list[int]:
        first_group_col = min(
            [
                idx
                for idx, header in enumerate(self.headers)
                if any(
                    header.endswith(f" {variant}")
                    for _role, variant in self.group_score_suffixes()
                )
            ]
            or [len(self.headers)]
        )
        out = []
        for idx, header in enumerate(self.headers[:first_group_col]):
            metadata_headers = {self.role_headers[role] for role in METADATA_ROLES}
            if header in metadata_headers:
                continue
            if parse_number(self.points[idx] if idx < len(self.points) else "") is not None:
                out.append(idx)
        return out


def pad_row(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return [*row, *("" for _ in range(width - len(row)))]
    return row[:width]


def resolve_gradebook_heading_aliases(value: Any) -> dict[str, tuple[str, ...]]:
    if value is None:
        raw: dict[str, Any] = {}
    elif isinstance(value, dict):
        raw = value
    else:
        raise ValueError("gradebook_heading_aliases must be a mapping")
    unknown = sorted(set(raw) - set(GRADEBOOK_HEADING_ROLES))
    if unknown:
        raise ValueError(f"Unknown gradebook heading role: gradebook_heading_aliases.{unknown[0]}")

    resolved: dict[str, tuple[str, ...]] = {}
    for role in GRADEBOOK_HEADING_ROLES:
        configured = raw.get(role, [])
        if isinstance(configured, str):
            configured_values = [configured]
        elif isinstance(configured, list) and all(isinstance(item, str) for item in configured):
            configured_values = configured
        else:
            raise ValueError(f"gradebook_heading_aliases.{role} must be a string or list of strings")
        aliases = [BUILTIN_HEADING_ROLES[role], *configured_values]
        normalized = []
        for alias in aliases:
            stripped = alias.strip()
            if not stripped:
                raise ValueError(f"gradebook_heading_aliases.{role} contains an empty alias")
            if stripped not in normalized:
                normalized.append(stripped)
        resolved[role] = tuple(normalized)

    owners: dict[str, list[str]] = {}
    for role, aliases in resolved.items():
        for alias in aliases:
            owners.setdefault(alias, []).append(role)
    conflicts = [(alias, roles) for alias, roles in owners.items() if len(roles) > 1]
    if conflicts:
        alias, roles = sorted(conflicts)[0]
        raise ValueError(
            f"Gradebook heading alias {alias!r} maps to multiple canonical roles: "
            f"{', '.join(roles)}"
        )
    return resolved


def resolve_observed_role_headers(
    headers: list[str], aliases: dict[str, tuple[str, ...]]
) -> dict[str, str | None]:
    resolved: dict[str, str | None] = {}
    for role in GRADEBOOK_HEADING_ROLES:
        matches = [header for header in headers if header.strip() in aliases[role]]
        if len(matches) > 1:
            raise ValueError(gradebook_role_error(role, aliases, headers, problem="ambiguous"))
        resolved[role] = matches[0] if matches else None
    return resolved


def gradebook_role_error(
    role: str,
    aliases: dict[str, tuple[str, ...]],
    headers: list[str],
    *,
    problem: str,
) -> str:
    return (
        f"Gradebook role {role!r} is {problem}. "
        f"Configured aliases: {list(aliases[role])!r}. "
        f"Observed headings: {bounded_observed_headings(headers)}"
    )


def bounded_observed_headings(headers: list[str]) -> str:
    observed = [header.strip() for header in headers[:OBSERVED_HEADING_LIMIT]]
    suffix = f" (+{len(headers) - OBSERVED_HEADING_LIMIT} more)" if len(headers) > len(observed) else ""
    return f"{observed!r}{suffix}"


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
            "id_column_present": gradebook.role_headers["id"] is not None,
            "student_column_present": gradebook.role_headers["student"] is not None,
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
    variants: list[str] = []
    for role in SCORE_ROLES:
        observed = gradebook.role_headers[role]
        if observed is not None:
            variants.append(observed)
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
    final_role = next(
        (role for role in SCORE_ROLES if gradebook.role_headers[role] == final_name),
        SCORE_ROLES[0],
    )
    matched = match_group_columns(groups, weights, final_role)
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
    preferred_role: str,
) -> dict[str, int]:
    if preferred_role not in SCORE_ROLES:
        preferred_role = SCORE_ROLES[0]
    matched = {}
    for group in weights:
        cols = groups.get(group)
        if not cols:
            continue
        for role in [preferred_role, *[item for item in SCORE_ROLES if item != preferred_role]]:
            if role in cols:
                matched[group] = cols[role]
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
