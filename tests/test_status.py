from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from danvas.cli import app
from danvas.pages import BODY_NORMALIZER_VERSION, load_page_source
from danvas.status import build_status, command_status

runner = CliRunner()

NOW = dt.datetime(2026, 6, 12, 1, 0, tzinfo=dt.UTC)


def build_snapshot() -> dict[str, Any]:
    return {
        "schema_version": 4,
        "generated_at": "2026-06-12T00:00:00Z",
        "course": {"id": 101, "name": "INSY 6600"},
        "assignment_groups": [],
        "assignments": [
            {
                "id": 1,
                "name": "Case Study 1",
                "points_possible": 100,
                "due_at": "2026-06-15T04:59:00Z",
                "published": True,
                "submission_types": ["online_upload"],
            },
            {
                "id": 2,
                "name": "Case Study 2",
                "points_possible": 50,
                "due_at": "",
                "published": True,
                "submission_types": ["online_upload"],
            },
            {
                "id": 3,
                "name": "Reflection Paper",
                "points_possible": 10,
                "due_at": "",
                "published": True,
                "submission_types": ["online_text_entry"],
            },
            {
                "id": 9,
                "name": "Case Discussion",
                "points_possible": 10,
                "due_at": "2026-06-20T04:59:00Z",
                "published": True,
                "submission_types": ["discussion_topic"],
            },
        ],
        "folders": [],
        "files": [
            {
                "id": 300,
                "display_name": "notes.pdf",
                "filename": "notes.pdf",
                "canvas_path": "course files/notes.pdf",
                "folder_full_name": "course files",
                "size": 5,
            },
            {
                "id": 301,
                "display_name": "rename.pdf",
                "filename": "rename.pdf",
                "canvas_path": "course files/rename.pdf",
                "folder_full_name": "course files",
                "size": 99,
            },
            {
                "id": 302,
                "display_name": "missing.pdf",
                "filename": "missing.pdf",
                "canvas_path": "course files/missing.pdf",
                "folder_full_name": "course files",
                "size": 7,
            },
        ],
        "discussions": [
            {
                "id": 400,
                "title": "Case Discussion",
                "assignment_id": 9,
                "published": True,
                "locked": False,
                "message_text": "Discuss the case",
            }
        ],
        "announcements": [
            {
                "id": 401,
                "title": "Welcome",
                "published": True,
                "posted_at": "2026-06-01T12:00:00Z",
                "delayed_post_at": "",
                "message_text": "Hello",
            }
        ],
        "quizzes": [
            {"id": 500, "assignment_id": 98, "title": "Chapter 7 Quiz", "published": True},
            {"id": 501, "assignment_id": 97, "title": "Chapter 8 Quiz", "published": False},
        ],
        "pages": [],
        "group_categories": [
            {
                "id": 700,
                "name": "Case 1 Groups",
                "self_signup": None,
                "group_count": 4,
                "member_count": 16,
                "groups": [],
            }
        ],
    }


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_workspace(root: Path) -> None:
    write(
        root / "content" / "announcements" / "01-welcome.md",
        "---\ntitle: Welcome\npublished: true\n---\n\nHello.\n",
    )
    write(
        root / "content" / "cases" / "case-1-assignment.md",
        "---\ntitle: Case Study 1\npoints_possible: 100\ndue_at: 2026-06-15T04:59:00Z\n"
        "published: true\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "cases" / "case-2-assignment.md",
        "---\ntitle: Case Study 2\npoints_possible: 100\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "cases" / "case-3-assignment.md",
        "---\ntitle: Case Study 3\npoints_possible: 25\n---\n\nSubmit.\n",
    )
    write(
        root / "content" / "discussions" / "case-discussion.md",
        "---\ntitle: Case Discussion\npoints_possible: 10\n---\n\nDiscuss.\n",
    )
    write(root / "content" / "quizzes" / "chap07.md", "Quiz title: Chapter 7 Quiz\n")
    write(root / "content" / "quizzes" / "chap07.zip", "fake zip")
    write(root / "notes.pdf", "12345")
    write(root / "rename.pdf", "x")


def classifications(items: list[dict[str, Any]]) -> dict[str, str]:
    return {item["title"]: item["classification"] for item in items}


def test_build_status_classifies_each_section(tmp_path: Path) -> None:
    build_workspace(tmp_path)

    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    sections = payload["sections"]
    assert classifications(sections["assignments"]) == {
        "Case Study 1": "exact",
        "Case Study 2": "metadata mismatch",
        "Case Study 3": "local-only",
        "Reflection Paper": "Canvas-only",
    }
    assert classifications(sections["announcements"]) == {"Welcome": "exact"}
    assert classifications(sections["discussions"]) == {"Case Discussion": "exact"}
    assert classifications(sections["quizzes"]) == {
        "Chapter 7 Quiz": "exact",
        "Chapter 8 Quiz": "Canvas-only",
    }
    assert classifications(sections["files"]) == {
        "course files/notes.pdf": "exact",
        "course files/rename.pdf": "filename-only match",
        "course files/missing.pdf": "Canvas-only",
    }
    assert payload["snapshot"]["stale"] is False
    assert payload["summary"]["exact"] == 5
    assert payload["group_categories"] == [
        {"name": "Case 1 Groups", "group_count": 4, "member_count": 16}
    ]

    mismatch = next(
        item for item in sections["assignments"] if item["title"] == "Case Study 2"
    )
    assert mismatch["details"] == ["points_possible: local 100 != Canvas 50"]
    assert "next_action" in mismatch
    local_only = next(
        item for item in sections["assignments"] if item["title"] == "Case Study 3"
    )
    assert "assignments create" in local_only["next_action"]
    filename_only = next(
        item for item in sections["files"] if item["title"] == "course files/rename.pdf"
    )
    assert "timestamps" in filename_only["next_action"]
    assert filename_only["canvas_size"] == 99
    assert filename_only["local_matches"][0]["size"] == 1


def test_build_status_excludes_discussion_backed_assignments(tmp_path: Path) -> None:
    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    titles = [item["title"] for item in payload["sections"]["assignments"]]
    assert "Case Discussion" not in titles


def test_build_status_compares_bound_pages_and_keeps_title_matches_unbound(
    tmp_path: Path,
) -> None:
    bound = tmp_path / "content/pages/bound.md"
    write(
        bound,
        "---\ntitle: Bound Page\npage_id: 601\npublished: false\n---\n\nHello.\n",
    )
    unbound = tmp_path / "content/pages/unbound.md"
    write(
        unbound,
        "---\ntitle: Unbound Page\npublished: true\n---\n\nCandidate.\n",
    )
    snapshot = build_snapshot()
    snapshot["pages"] = [
        {
            "page_id": 601,
            "url": "bound-page",
            "title": "Bound Page",
            "published": False,
            "front_page": False,
            "body_sha256": load_page_source(bound).body_sha256,
            "body_hash_status": "available",
            "body_normalizer": BODY_NORMALIZER_VERSION,
        },
        {
            "page_id": 602,
            "url": "unbound-page",
            "title": "Unbound Page",
            "published": True,
            "front_page": False,
            "body_sha256": load_page_source(unbound).body_sha256,
            "body_hash_status": "available",
            "body_normalizer": BODY_NORMALIZER_VERSION,
        },
    ]

    payload = build_status(snapshot, tmp_path, now=NOW)
    page_items = payload["sections"]["pages"]

    assert classifications(page_items) == {
        "Bound Page": "exact",
        "Unbound Page": "probable match, unbound",
    }
    candidate = next(item for item in page_items if item["title"] == "Unbound Page")
    assert candidate["canvas_id"] == 602
    assert "--page-id 602" in candidate["next_action"]


def test_page_title_candidates_require_unique_unbound_local_source(tmp_path: Path) -> None:
    for name in ("one", "two"):
        write(
            tmp_path / f"content/pages/{name}.md",
            "---\ntitle: Duplicate\npublished: false\n---\n\nBody.\n",
        )
    snapshot = build_snapshot()
    snapshot["pages"] = [
        {
            "page_id": 610,
            "url": "duplicate",
            "title": "Duplicate",
            "published": False,
            "front_page": False,
            "body_sha256": "hash",
            "body_hash_status": "available",
            "body_normalizer": BODY_NORMALIZER_VERSION,
        }
    ]

    items = build_status(snapshot, tmp_path, now=NOW)["sections"]["pages"]
    local_items = [item for item in items if item["local_path"]]

    assert len(local_items) == 2
    assert {item["classification"] for item in local_items} == {
        "unsupported comparison"
    }
    assert all("2 unbound local Pages" in item["details"][0] for item in local_items)


def test_page_title_candidate_excludes_canvas_page_claimed_by_stable_identity(
    tmp_path: Path,
) -> None:
    write(
        tmp_path / "content/pages/bound.md",
        "---\ntitle: Shared\npage_id: 611\npublished: false\n---\n\nBody.\n",
    )
    write(
        tmp_path / "content/pages/unbound.md",
        "---\ntitle: Shared\npublished: false\n---\n\nOther.\n",
    )
    snapshot = build_snapshot()
    snapshot["pages"] = [
        {
            "page_id": 611,
            "url": "shared",
            "title": "Shared",
            "published": False,
            "front_page": False,
            "body_sha256": load_page_source(
                tmp_path / "content/pages/bound.md"
            ).body_sha256,
            "body_hash_status": "available",
            "body_normalizer": BODY_NORMALIZER_VERSION,
        }
    ]

    items = build_status(snapshot, tmp_path, now=NOW)["sections"]["pages"]
    unbound = next(item for item in items if item["local_path"].endswith("unbound.md"))

    assert unbound["classification"] == "local-only"
    assert unbound["canvas_id"] is None


def test_build_status_reports_page_body_and_metadata_drift(tmp_path: Path) -> None:
    source = tmp_path / "content/pages/drift.md"
    write(
        source,
        "---\ntitle: Drift\npage_id: 603\npublished: true\n---\n\nLocal.\n",
    )
    snapshot = build_snapshot()
    snapshot["pages"] = [
        {
            "page_id": 603,
            "url": "drift",
            "title": "Drift",
            "published": False,
            "front_page": False,
            "body_sha256": "different",
            "body_hash_status": "available",
            "body_normalizer": BODY_NORMALIZER_VERSION,
        }
    ]

    item = build_status(snapshot, tmp_path, now=NOW)["sections"]["pages"][0]

    assert item["classification"] == "metadata and body mismatch"
    assert "body hash differs" in item["details"]


def test_build_status_requires_current_page_body_normalizer(tmp_path: Path) -> None:
    source = tmp_path / "content/pages/old-normalizer.md"
    write(
        source,
        "---\ntitle: Old Normalizer\npage_id: 604\npublished: false\n---\n\nSame body.\n",
    )
    snapshot = build_snapshot()
    snapshot["pages"] = [
        {
            "page_id": 604,
            "url": "old-normalizer",
            "title": "Old Normalizer",
            "published": False,
            "front_page": False,
            "body_sha256": load_page_source(source).body_sha256,
            "body_hash_status": "available",
            "body_normalizer": "pages-html-v2",
        }
    ]

    item = build_status(snapshot, tmp_path, now=NOW)["sections"]["pages"][0]

    assert item["classification"] == "unsupported comparison"
    assert item["refresh_required"] is True
    assert "does not match" in item["details"][-1]
    assert item["next_action"] == (
        "Run `danvas refresh` to rebuild Page hashes with the current normalizer."
    )


def test_build_status_uses_base_window_and_reports_untracked_overrides(tmp_path: Path) -> None:
    build_workspace(tmp_path)
    snapshot = build_snapshot()
    snapshot["assignments"][0].update(
        {
            "due_at": "2026-06-17T04:59:59Z",
            "lock_at": None,
            "has_overrides": True,
            "all_dates": [
                {
                    "id": None,
                    "title": "Everyone else",
                    "base": True,
                    "due_at": "2026-06-15T04:59:00Z",
                    "unlock_at": None,
                    "lock_at": None,
                    "assignee_count": 0,
                },
                {
                    "id": 900,
                    "title": "Extension",
                    "base": False,
                    "due_at": "2026-06-17T04:59:59Z",
                    "unlock_at": None,
                    "lock_at": None,
                    "assignee_count": 2,
                },
            ],
        }
    )

    payload = build_status(snapshot, tmp_path, now=NOW)

    item = next(
        item for item in payload["sections"]["assignments"] if item["title"] == "Case Study 1"
    )
    assert item["classification"] == "override untracked"
    assert not any("due_at:" in detail for detail in item["details"])
    assert "Canvas has untracked assignment overrides (1)" in item["details"]


def test_build_status_compares_private_override_reference_by_count(tmp_path: Path) -> None:
    build_workspace(tmp_path)
    assignment_source = tmp_path / "content/cases/case-1-assignment.md"
    assignment_source.write_text(
        assignment_source.read_text(encoding="utf-8").replace(
            "published: true",
            "published: true\navailability_overrides_ref: grading/overrides/case1.yaml",
        ),
        encoding="utf-8",
    )
    write(
        tmp_path / "grading/overrides/case1.yaml",
        "assignment_id: 1\noverrides:\n"
        "  - canvas_override_id: 900\n"
        "    title: Extension\n"
        "    due_at: 2026-06-17T04:59:59Z\n"
        "    assignees:\n      canvas_user_ids: [10, 11]\n",
    )
    snapshot = build_snapshot()
    snapshot["assignments"][0].update(
        {
            "has_overrides": True,
            "all_dates": [
                {
                    "id": 900,
                    "title": "Extension",
                    "base": False,
                    "due_at": "2026-06-17T04:59:59Z",
                    "unlock_at": None,
                    "lock_at": None,
                    "assignee_count": 2,
                }
            ],
        }
    )

    payload = build_status(snapshot, tmp_path, now=NOW)
    item = next(
        item for item in payload["sections"]["assignments"] if item["title"] == "Case Study 1"
    )
    assert item["classification"] == "exact"
    assert item["override_status"] == "exact"


def test_build_status_flags_stale_snapshot(tmp_path: Path) -> None:
    snapshot = build_snapshot()
    snapshot["generated_at"] = "2026-06-01T00:00:00Z"

    payload = build_status(snapshot, tmp_path, max_age_hours=24, now=NOW)

    assert payload["snapshot"]["stale"] is True
    assert payload["summary"]["snapshot stale"] == 1


def test_build_status_notes_missing_qti_zip(tmp_path: Path) -> None:
    write(tmp_path / "content" / "quizzes" / "chap07.md", "Quiz title: Chapter 7 Quiz\n")

    payload = build_status(build_snapshot(), tmp_path, now=NOW)

    quiz = next(
        item
        for item in payload["sections"]["quizzes"]
        if item["title"] == "Chapter 7 Quiz"
    )
    assert "no QTI zip found next to source" in quiz["details"]


def test_status_cli_writes_json_and_markdown(
    tmp_path: Path, monkeypatch: Any
) -> None:
    build_workspace(tmp_path)
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["status", "--output", "status.json", "--report-md", "status.md"]
    )

    assert result.exit_code == 0, result.output
    assert "Course status: INSY 6600 (101)" in result.output
    assert "metadata mismatch: Case Study 2" in result.output
    payload = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert payload["summary"]["exact"] == 5
    assert any(
        item.get("next_action")
        for section in payload["sections"].values()
        for item in section
    )
    report = (tmp_path / "status.md").read_text(encoding="utf-8")
    assert "# Course Status Report" in report
    assert "Canvas-only: Chapter 8 Quiz" in report
    assert "Next action:" in report


def test_status_cli_does_not_write_report_run_by_default(
    tmp_path: Path, monkeypatch: Any
) -> None:
    build_workspace(tmp_path)
    write(
        tmp_path / ".danvas" / "config.toml",
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
    )
    snapshot = build_snapshot()
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_status_cli_writes_report_run_when_report_option_is_passed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    build_workspace(tmp_path)
    write(
        tmp_path / ".danvas" / "config.toml",
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
    )
    snapshot = build_snapshot()
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status", "--report-root", ".danvas/reports"])

    assert result.exit_code == 0, result.output
    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    report_dir = report_dirs[0]
    assert report_dir.name.endswith("-status")
    assert (report_dir / "status.json").is_file()
    assert (report_dir / "status.md").is_file()
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "status"
    assert manifest["course_id"] == 101
    assert manifest["snapshot_timestamp"] == snapshot["generated_at"]
    assert manifest["snapshot_path"].endswith(".danvas/course.json")
    assert manifest["snapshot_stale"] is False


def test_status_cli_writes_legacy_outputs_and_report_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    build_workspace(tmp_path)
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "status",
            "--output",
            "status.json",
            "--report-md",
            "status.md",
            "--report-dir",
            "status-report-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "status.json").is_file()
    assert (tmp_path / "status.md").is_file()
    assert (tmp_path / "status-report-run" / "status.json").is_file()
    assert (tmp_path / "status-report-run" / "status.md").is_file()
    assert (tmp_path / "status-report-run" / "manifest.json").is_file()


def test_status_cli_uses_configured_assignment_sources(
    tmp_path: Path, monkeypatch: Any
) -> None:
    write(
        tmp_path / "content" / "assignments" / "01-setup-check.md",
        "---\ntitle: Case Study 1\npoints_possible: 100\n"
        "due_at: 2026-06-15T04:59:00Z\npublished: true\n---\n\nSubmit.\n",
    )
    write(
        tmp_path / "content" / "assignments" / "assignment-notes.md",
        "# Assignment Notes\n\nSupport notes, not Canvas source.\n",
    )
    write(
        tmp_path / ".danvas" / "config.toml",
        "\n".join(
            [
                "[canvas]",
                "course_id = 101",
                "",
                "[sources.assignments]",
                'include = ["content/assignments/*.md"]',
            ]
        ),
    )
    snapshot = build_snapshot()
    snapshot["assignments"] = [snapshot["assignments"][0]]
    snapshot["generated_at"] = (
        dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    )
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "Assignments: exact: 1" in result.output
    assert "Canvas-only: Case Study 1" not in result.output


def test_command_status_requires_current_snapshot_schema(tmp_path: Path) -> None:
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    del snapshot["schema_version"]
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    args = SimpleNamespace(
        project_root=str(tmp_path), max_age_hours=None, output=None, report_md=None
    )

    with pytest.raises(SystemExit, match="predates the current format"):
        command_status(args)


def test_command_status_renders_non_page_sections_for_schema_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / ".danvas" / "config.toml", "[canvas]\ncourse_id = 101\n")
    snapshot = build_snapshot()
    snapshot["schema_version"] = 3
    snapshot.pop("pages")
    write(tmp_path / ".danvas" / "course.json", json.dumps(snapshot))
    args = SimpleNamespace(
        project_root=str(tmp_path),
        max_age_hours=None,
        output=None,
        report_md=None,
        report_root=None,
        report_dir=None,
        report_slug=None,
    )

    command_status(args)

    output = capsys.readouterr().out
    assert "Assignments:" in output
    assert "Pages: unavailable" in output
