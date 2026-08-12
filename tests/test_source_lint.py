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


def test_page_date_only_passes_but_discussion_date_only_fails_timezone_lint(
    tmp_path: Path,
) -> None:
    discussion = write(
        tmp_path / "content/discussions/week.md",
        "---\ntitle: Week\ndiscussion_type: threaded\ndue_at: 2026-09-30\n"
        "lock_at: 2026-10-01\n---\nDiscuss.\n",
    )
    page = write(
        tmp_path / "content/pages/help.md",
        "---\ntitle: Help\npublished: false\npublish_at: 2026-09-30\n---\nHelp.\n",
    )

    discussion_record = lint_source(discussion, kind=None, project_root=tmp_path)
    page_record = lint_source(page, kind=None, project_root=tmp_path)

    assert "date-timezone" in rule_ids(discussion_record)
    assert "date-timezone" not in rule_ids(page_record)


def test_naive_timestamps_still_receive_ordering_lint(tmp_path: Path) -> None:
    source = write(
        tmp_path / "assignment.md",
        "---\ntitle: Work\nunlock_at: 2026-07-12T17:00:00\n"
        "due_at: 2026-07-10T17:00:00\n---\nComplete the work.\n",
    )

    record = lint_source(source, kind="assignment", project_root=tmp_path)

    assert "date-timezone" in rule_ids(record)
    assert "date-order" in rule_ids(record)


def test_mixed_timezone_ordering_lints_only_beyond_offset_uncertainty(
    tmp_path: Path,
) -> None:
    clear_violation = write(
        tmp_path / "clear.md",
        "---\ntitle: Clear\nunlock_at: 2026-07-13T17:00:00\n"
        "due_at: 2026-07-10T17:00:00Z\n---\nComplete the work.\n",
    )
    uncertain = write(
        tmp_path / "uncertain.md",
        "---\ntitle: Uncertain\nunlock_at: 2026-07-11T01:00:00\n"
        "due_at: 2026-07-10T17:00:00Z\n---\nComplete the work.\n",
    )

    clear_record = lint_source(clear_violation, kind="assignment", project_root=tmp_path)
    uncertain_record = lint_source(uncertain, kind="assignment", project_root=tmp_path)

    assert "date-order" in rule_ids(clear_record)
    assert "written wall-clock values" in next(
        item["message"] for item in clear_record["findings"] if item["rule_id"] == "date-order"
    )
    assert "date-order" not in rule_ids(uncertain_record)


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
