from __future__ import annotations

from pathlib import Path

from danvas.sources import scan_sources


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_workspace(root: Path) -> None:
    write(
        root / "content" / "announcements" / "01-welcome.md",
        "---\ntitle: Welcome\npublished: true\n---\n\nHello.\n",
    )
    write(
        root / "content" / "discussions" / "case-discussion.md",
        "---\ntitle: Case Discussion\npoints_possible: 10\n---\n\nDiscuss.\n",
    )
    write(
        root / "content" / "quizzes" / "chap07.md",
        "Quiz title: Chapter 7 Quiz\n\n1. A question.\na) yes\nb) no\n",
    )
    write(root / "content" / "quizzes" / "chap07.zip", "fake zip")
    write(
        root / "content" / "cases" / "case-1-assignment.md",
        "---\ntitle: Case Study 1\npoints_possible: 100\ndue_at: 2026-06-15T04:59:00Z\n"
        "published: true\n---\n\nSubmit.\n",
    )
    write(root / "content" / "cases" / "case-1-notes.md", "no front matter, wrong pattern\n")


def test_scan_sources_discovers_conventional_sources(tmp_path: Path) -> None:
    build_workspace(tmp_path)

    records = scan_sources(tmp_path)

    by_kind = {record["kind"]: record for record in records}
    assert set(by_kind) == {"announcement", "discussion", "quiz", "assignment"}
    assert len(records) == 4

    announcement = by_kind["announcement"]
    assert announcement["title"] == "Welcome"
    assert announcement["metadata"] == {"published": True}

    assignment = by_kind["assignment"]
    assert assignment["path"] == "content/cases/case-1-assignment.md"
    assert assignment["metadata"]["points_possible"] == 100
    assert assignment["metadata"]["due_at"] == "2026-06-15T04:59:00+00:00"

    quiz = by_kind["quiz"]
    assert quiz["title"] == "Chapter 7 Quiz"
    assert quiz["artifacts"]["qti_zip"] == "content/quizzes/chap07.zip"


def test_scan_sources_records_parse_errors_without_raising(tmp_path: Path) -> None:
    write(tmp_path / "content" / "announcements" / "bad.md", "no front matter here\n")

    records = scan_sources(tmp_path)

    assert len(records) == 1
    assert "front matter" in records[0]["error"]
    assert records[0]["title"] == ""


def test_scan_sources_reports_missing_qti_zip(tmp_path: Path) -> None:
    write(tmp_path / "content" / "quizzes" / "chap08.md", "Quiz Title: Chapter 8 Quiz\n")

    records = scan_sources(tmp_path)

    assert records[0]["title"] == "Chapter 8 Quiz"
    assert records[0]["artifacts"]["qti_zip"] == ""


def test_scan_sources_handles_missing_content_dirs(tmp_path: Path) -> None:
    assert scan_sources(tmp_path) == []


def test_scan_sources_skips_readme_files(tmp_path: Path) -> None:
    write(tmp_path / "content" / "discussions" / "README.md", "notes about this folder\n")
    write(
        tmp_path / "content" / "discussions" / "case-discussion.md",
        "---\ntitle: Case Discussion\n---\n\nDiscuss.\n",
    )

    records = scan_sources(tmp_path)

    assert [record["path"] for record in records] == [
        "content/discussions/case-discussion.md"
    ]
