from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from danvas.source_lint import command_sources_lint, lint_source


def write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def rule_ids(record: dict[str, Any]) -> set[str]:
    return {item["rule_id"] for item in record["findings"]}


def test_valid_mixed_sources_have_stable_kinds(tmp_path: Path) -> None:
    assignment = write(
        tmp_path / "content/assignments/work.md",
        "---\ntitle: Work\npoints_possible: 10\nsubmission_types: [online_upload]\n"
        "due_at: 2026-07-10T17:00:00-05:00\n---\nComplete the work for 10 points.\n",
    )
    announcement = write(
        tmp_path / "content/announcements/news.md",
        "---\ntitle: News\npublished: false\n---\nHello.\n",
    )
    discussion = write(
        tmp_path / "content/discussions/week.md",
        "---\ntitle: Week\ndiscussion_type: threaded\n---\n## Prompt\nRespond.\n",
    )
    page = write(
        tmp_path / "content/pages/help.md",
        "---\ntitle: Help\npublished: false\n---\n## Start\n[Jump](#start)\n",
    )
    records = [lint_source(path, kind=None, project_root=tmp_path) for path in (assignment, announcement, discussion, page)]
    assert [record["kind"] for record in records] == ["assignment", "announcement", "discussion", "page"]
    assert all(not any(item["severity"] == "error" for item in record["findings"]) for record in records)


def test_common_rules_catch_timezone_points_assets_and_duplicate_h1(tmp_path: Path) -> None:
    source = write(
        tmp_path / "assignment.md",
        "---\ntitle: Work\npoints_possible: 10\ndue_at: 2026-07-10T17:00:00\n"
        "submission_types: [online_upload]\n---\n# Work\nWorth 8 points.\n[File](missing.pdf)\n",
    )
    record = lint_source(source, kind="assignment", project_root=tmp_path)
    assert {"date-timezone", "points-prose-mismatch", "asset-missing", "title-duplicate-h1"} <= rule_ids(record)


def test_page_rules_catch_unsafe_html_and_publication_conflict(tmp_path: Path) -> None:
    source = write(
        tmp_path / "page.html",
        "---\ntitle: Home\npublished: false\nfront_page: true\n---\n<script>alert(1)</script>\n",
    )
    record = lint_source(source, kind="page", project_root=tmp_path)
    assert {"page-front-page-draft", "page-profile"} <= rule_ids(record)


def test_narrow_suppression_requires_reason_and_removes_only_named_rule(tmp_path: Path) -> None:
    source = write(
        tmp_path / "assignment.md",
        "---\ntitle: Work\npoints_possible: 10\nsubmission_types: [online_upload]\n"
        "lint_suppress:\n  title-duplicate-h1: Canvas preview intentionally repeats it\n"
        "---\n# Work\nWorth 8 points.\n",
    )
    record = lint_source(source, kind="assignment", project_root=tmp_path)
    assert "title-duplicate-h1" not in rule_ids(record)
    assert "points-prose-mismatch" in rule_ids(record)
    assert record["suppressed_rules"] == ["title-duplicate-h1"]


def test_json_command_glob_and_warning_strict_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = write(
        tmp_path / "content/assignments/work.md",
        "---\ntitle: Work\npoints_possible: 10\nsubmission_types: [online_upload]\n---\n# Work\n10 points.\n",
    )
    output = tmp_path / "lint.json"
    args = SimpleNamespace(
        paths=["content/assignments/*.md"],
        kind="assignment",
        project_root=str(tmp_path),
        format="json",
        output=str(output),
        fail_on="warning",
    )
    with pytest.raises(SystemExit) as exc:
        command_sources_lint(args)
    assert exc.value.code == 1
    payload = json.loads(output.read_text())
    assert payload["counts"]["warnings"] == 1
    assert payload["sources"][0]["path"] == str(source.resolve())
    assert "Wrote lint results" in capsys.readouterr().out
