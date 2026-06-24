import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.assignments import command_assignments_verify, load_assignment_markdown, resolve_format


def test_load_assignment_markdown_accepts_yaml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: YAML Assignment
points_possible: 10
grading_type: points
submission_types:
  - online_upload
published: false
---

# YAML Assignment

Submit the report.
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert payload["name"] == "YAML Assignment"
    assert payload["points_possible"] == 10
    assert payload["submission_types"] == ["online_upload"]
    assert payload["published"] is False
    assert "<h1>YAML Assignment</h1>" in payload["description"]


def test_load_assignment_markdown_still_accepts_toml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """+++
title = "TOML Assignment"
points_possible = 5
grading_type = "points"
submission_types = ["online_text_entry"]
+++

# TOML Assignment
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert payload["name"] == "TOML Assignment"
    assert payload["submission_types"] == ["online_text_entry"]
    assert payload["published"] is False


def test_resolve_format_infers_from_extension() -> None:
    assert resolve_format(Path("assignments.json"), "auto") == "json"
    assert resolve_format(Path("assignments.csv"), "auto") == "csv"
    assert resolve_format(Path("assignments-md"), "auto") == "markdown"
    assert resolve_format(Path("assignments.md"), "csv") == "csv"


def test_resolve_format_rejects_ambiguous_extension() -> None:
    with pytest.raises(SystemExit, match="Cannot infer assignments export format"):
        resolve_format(Path("assignments.md"), "auto")


def test_load_assignment_markdown_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
- title
---

# Bad Assignment
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="must be a mapping"):
        load_assignment_markdown(source)


def test_command_assignments_verify_matches_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
assignment_id: 10
title: Case 1
points_possible: 100
due_at: 2026-06-20T04:59:00Z
published: true
assignment_group_name: Cases
submission_types:
  - online_text_entry
grading_type: points
group_category_id: 9
---

Submit the case memo.
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"

    class FakeCourse:
        id = 101
        name = "Course"

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            assert assignment_id == 10
            return SimpleNamespace(
                id=10,
                name="Case 1",
                points_possible=100,
                due_at="2026-06-20T04:59:00Z",
                unlock_at="",
                lock_at="",
                published=True,
                assignment_group_id=7,
                submission_types=["online_text_entry"],
                grading_type="points",
                group_category_id=9,
                description="<p>Submit the case memo.</p>",
                html_url="",
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=7, name="Cases")]

    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: FakeCourse()),
    )

    command_assignments_verify(
        SimpleNamespace(
            source=str(source),
            course_id=101,
            assignment_id=None,
            project_root=str(tmp_path),
            no_report=False,
            report_root=None,
            report_dir=str(report_dir),
            report_slug=None,
        )
    )

    report = json.loads((report_dir / "assignments-verify.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report["status"] == "matches"
    assert all(check["matches"] for check in report["checks"])
    assert manifest["command"] == "assignments verify"
    assert manifest["status"] == "success"


def test_command_assignments_verify_mismatch_writes_failed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
assignment_id: 10
title: Case 1
points_possible: 100
published: true
---

Submit the case memo.
""",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"

    class FakeCourse:
        id = 101
        name = "Course"

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            return SimpleNamespace(
                id=assignment_id,
                name="Case 1 revised",
                points_possible=90,
                published=False,
                description="<p>Submit the case memo.</p>",
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: FakeCourse()),
    )

    with pytest.raises(SystemExit) as excinfo:
        command_assignments_verify(
            SimpleNamespace(
                source=str(source),
                course_id=101,
                assignment_id=None,
                project_root=str(tmp_path),
                no_report=False,
                report_root=None,
                report_dir=str(report_dir),
                report_slug=None,
            )
        )

    assert excinfo.value.code == 1
    report = json.loads((report_dir / "assignments-verify.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report["status"] == "mismatch"
    assert {check["field"] for check in report["checks"] if not check["matches"]} >= {
        "title",
        "points_possible",
        "published",
    }
    assert manifest["status"] == "failed"


def test_command_assignments_verify_requires_assignment_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")

    def fail_canvas(args: SimpleNamespace) -> None:
        raise AssertionError("Canvas should not be contacted without an assignment ID.")

    monkeypatch.setattr("danvas.assignments.canvas_from_args", fail_canvas)

    with pytest.raises(SystemExit, match="requires --assignment-id"):
        command_assignments_verify(
            SimpleNamespace(
                source=str(source),
                course_id=101,
                assignment_id=None,
                project_root=str(tmp_path),
                no_report=True,
                report_root=None,
                report_dir=None,
                report_slug=None,
            )
        )
