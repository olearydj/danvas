import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from danvas.assignments import (
    command_assignments_create,
    command_assignments_update,
    command_assignments_upsert,
    command_assignments_verify,
    load_assignment_markdown,
    resolve_format,
)


def write_config(root: Path, timezone: str = "America/Chicago") -> None:
    config_dir = root / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        f'[canvas]\ncourse_id = 101\ntimezone = "{timezone}"\n',
        encoding="utf-8",
    )


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


def test_load_assignment_markdown_expands_date_only_fields_with_course_timezone(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    source.parent.mkdir()
    source.write_text(
        """---
title: Date Assignment
due_date: 2026-05-29
unlock_date: 2026-05-20
lock_date: 2026-05-30
---

Submit the report.
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert payload["due_at"] == "2026-05-29T23:59:00-05:00"
    assert payload["unlock_at"] == "2026-05-20T00:00:00-05:00"
    assert payload["lock_at"] == "2026-05-30T23:59:00-05:00"
    assert "due_date" not in payload
    assert "unlock_date" not in payload
    assert "lock_date" not in payload


def test_load_assignment_markdown_rejects_date_alias_conflict(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Date Assignment
due_date: 2026-05-29
due_at: 2026-05-29T23:59:00-05:00
---

Submit the report.
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Use either due_date or due_at"):
        load_assignment_markdown(source)


def test_load_assignment_markdown_requires_timezone_for_date_only(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Date Assignment
due_date: 2026-05-29
---

Submit the report.
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="requires \\[canvas\\]\\.timezone"):
        load_assignment_markdown(source)


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


def test_command_assignments_create_dry_run_does_not_write_source_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")

    def fail_canvas(args: SimpleNamespace) -> None:
        raise AssertionError("Canvas should not be contacted during create dry-run.")

    monkeypatch.setattr("danvas.assignments.canvas_from_args", fail_canvas)

    command_assignments_create(SimpleNamespace(source=str(source), course_id=101, dry_run=True))

    assert not (tmp_path / ".danvas" / "source-map.json").exists()


def test_command_assignments_create_live_reads_back_and_writes_source_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    source.parent.mkdir()
    source.write_text(
        """---
title: Case 1
points_possible: 100
published: false
---

Submit the case memo.
""",
        encoding="utf-8",
    )

    created = SimpleNamespace(
        id=10,
        name="Case 1",
        points_possible=100,
        published=False,
        description="<p>Submit the case memo.</p>",
        html_url="https://canvas.example/courses/101/assignments/10",
        updated_at="2026-06-24T12:00:00Z",
    )

    class FakeCourse:
        id = 101
        name = "Course"

        def create_assignment(self, assignment: dict[str, object]) -> SimpleNamespace:
            assert assignment["name"] == "Case 1"
            return created

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            assert assignment_id == 10
            return created

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: FakeCourse()),
    )

    command_assignments_create(SimpleNamespace(source=str(source), course_id=101, dry_run=False))

    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    entry = source_map["sources"][0]
    assert entry["kind"] == "assignment"
    assert entry["path"] == "content/assignment.md"
    assert entry["canvas"]["id"] == 10
    assert entry["canvas"]["url"] == "https://canvas.example/courses/101/assignments/10"
    assert entry["last_posted"]["command"] == "assignments create"
    assert entry["last_posted"]["fields"]["title"] == "Case 1"
    assert "body_sha256" in entry["last_posted"]


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


def test_command_assignments_verify_matches_date_only_due_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
assignment_id: 10
title: Case 1
due_date: 2026-05-29
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
                name="Case 1",
                due_at="2026-05-29T23:59:00-05:00",
                description="<p>Submit the case memo.</p>",
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

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
    assert report["status"] == "matches"
    assert any(check["field"] == "due_at" and check["matches"] for check in report["checks"])


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


def update_args(source: Path, report_dir: Path, **overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "source": str(source),
        "course_id": 101,
        "assignment_id": None,
        "match_title": False,
        "dry_run": True,
        "project_root": str(
            source.parent.parent if source.parent.name == "content" else source.parent
        ),
        "no_report": False,
        "report_root": None,
        "report_dir": str(report_dir),
        "report_slug": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def upsert_args(source: Path, report_dir: Path, **overrides: object) -> SimpleNamespace:
    defaults = vars(update_args(source, report_dir)).copy()
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeAssignment:
    def __init__(self, **attrs: object) -> None:
        self.id = int(cast(Any, attrs.get("id", 0)) or 0)
        self.__dict__.update(attrs)
        self.edits: list[dict[str, object]] = []

    def edit(self, **kwargs: object) -> "FakeAssignment":
        assignment = cast(dict[str, object], kwargs["assignment"])
        assert isinstance(assignment, dict)
        self.edits.append(assignment)
        if "name" in assignment:
            self.name = assignment["name"]
        if "description" in assignment:
            self.description = assignment["description"]
        for key, value in assignment.items():
            if key not in {"name", "description"}:
                setattr(self, key, value)
        return self


class FakeUpdateCourse:
    id = 101
    name = "Course"

    def __init__(self, assignments: list[FakeAssignment]) -> None:
        self.assignments = {int(assignment.id): assignment for assignment in assignments}

    def get_assignment(self, assignment_id: int) -> FakeAssignment:
        return self.assignments[int(assignment_id)]

    def get_assignments(self) -> list[FakeAssignment]:
        return list(self.assignments.values())

    def get_assignment_groups(self) -> list[SimpleNamespace]:
        return []


def test_command_assignments_update_dry_run_writes_diff_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 10
title: Case 1 revised
points_possible: 100
published: true
---

Submit the revised case memo.
""",
        encoding="utf-8",
    )
    assignment = FakeAssignment(
        id=10,
        name="Case 1",
        points_possible=90,
        published=True,
        description="<p>Submit the case memo.</p>",
    )
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(update_args(source, tmp_path / "report"))

    assert assignment.edits == []
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text("utf-8"))
    assert report["status"] == "would_update"
    assert report["dry_run"] is True
    assert report["id_resolution"]["source"] == "frontmatter"
    changed = {check["field"] for check in report["diff"] if not check["matches"]}
    assert {"title", "points_possible", "body_text"} <= changed
    assert manifest["command"] == "assignments update"
    assert manifest["status"] == "success"
    assert not (tmp_path / ".danvas" / "source-map.json").exists()


def test_command_assignments_update_live_edits_and_writes_source_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 10
title: Case 1 revised
points_possible: 100
published: true
---

Submit the revised case memo.
""",
        encoding="utf-8",
    )
    assignment = FakeAssignment(
        id=10,
        name="Case 1",
        points_possible=90,
        published=True,
        description="<p>Submit the case memo.</p>",
        html_url="https://canvas.example/courses/101/assignments/10",
        updated_at="2026-06-24T12:00:00Z",
    )
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(
        update_args(source, tmp_path / "report", dry_run=False, project_root=str(tmp_path))
    )

    assert assignment.edits
    assert assignment.edits[0]["name"] == "Case 1 revised"
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert report["status"] == "updated"
    assert report["readback"]["status"] == "matches"
    assert source_map["sources"][0]["kind"] == "assignment"
    assert source_map["sources"][0]["path"] == "content/case.md"
    assert source_map["sources"][0]["canvas"]["id"] == 10
    assert source_map["sources"][0]["last_posted"]["command"] == "assignments update"


def test_command_assignments_update_uses_source_map_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")
    (tmp_path / ".danvas" / "source-map.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course_id": 101,
                "generated_at": "2026-06-24T12:00:00-05:00",
                "sources": [
                    {
                        "kind": "assignment",
                        "path": "content/case.md",
                        "canvas": {"id": 10},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assignment = FakeAssignment(id=10, name="Case 1", description="<p>Old body.</p>")
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(update_args(source, tmp_path / "report", project_root=str(tmp_path)))

    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["id_resolution"]["source"] == "source_map"
    assert report["assignment_id"] == 10


def test_command_assignments_update_requires_id_or_match_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")
    course = FakeUpdateCourse([])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    with pytest.raises(SystemExit) as excinfo:
        command_assignments_update(update_args(source, tmp_path / "report"))

    assert excinfo.value.code == 1
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["status"] == "lookup_failed"
    assert report["lookup"]["status"] == "missing_id"


def test_command_assignments_update_refuses_ambiguous_title_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")
    course = FakeUpdateCourse(
        [
            FakeAssignment(id=10, name="Case 1", description=""),
            FakeAssignment(id=11, name="Case 1", description=""),
        ]
    )
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    with pytest.raises(SystemExit) as excinfo:
        command_assignments_update(
            update_args(source, tmp_path / "report", match_title=True, project_root=str(tmp_path))
        )

    assert excinfo.value.code == 1
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["lookup"]["status"] == "ambiguous"


def test_command_assignments_upsert_plans_update_by_source_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")
    (tmp_path / ".danvas" / "source-map.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "course_id": 101,
                "generated_at": "2026-06-24T12:00:00-05:00",
                "sources": [
                    {
                        "kind": "assignment",
                        "path": "content/case.md",
                        "canvas": {"id": 10},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assignment = FakeAssignment(id=10, name="Case 1", description="<p>Old body.</p>")
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_upsert(upsert_args(source, tmp_path / "report", project_root=str(tmp_path)))

    report = json.loads((tmp_path / "report" / "assignments-upsert.json").read_text("utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text("utf-8"))
    assert report["status"] == "would_update"
    assert report["planned_action"] == "update"
    assert report["id_resolution"]["source"] == "source_map"
    assert report["assignment_id"] == 10
    assert manifest["command"] == "assignments upsert"
    assert manifest["status"] == "success"
    assert assignment.edits == []


def test_command_assignments_upsert_plans_create_without_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        "---\ntitle: Case 1\npoints_possible: 100\n---\n\nSubmit the case memo.\n",
        encoding="utf-8",
    )
    course = FakeUpdateCourse([])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_upsert(upsert_args(source, tmp_path / "report"))

    report = json.loads((tmp_path / "report" / "assignments-upsert.json").read_text("utf-8"))
    assert report["status"] == "would_create"
    assert report["planned_action"] == "create"
    assert report["create_payload"]["name"] == "Case 1"
    assert report["lookup"]["status"] == "would_create"


def test_command_assignments_upsert_refuses_non_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "case.md"
    source.write_text("---\ntitle: Case 1\n---\n\nBody\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="supports --dry-run only"):
        command_assignments_upsert(upsert_args(source, tmp_path / "report", dry_run=False))


def test_command_assignments_upsert_refuses_ambiguous_title_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nSubmit the case memo.\n", encoding="utf-8")
    course = FakeUpdateCourse(
        [
            FakeAssignment(id=10, name="Case 1", description=""),
            FakeAssignment(id=11, name="Case 1", description=""),
        ]
    )
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    with pytest.raises(SystemExit) as excinfo:
        command_assignments_upsert(
            upsert_args(source, tmp_path / "report", match_title=True, project_root=str(tmp_path))
        )

    assert excinfo.value.code == 1
    report = json.loads((tmp_path / "report" / "assignments-upsert.json").read_text("utf-8"))
    manifest = json.loads((tmp_path / "report" / "manifest.json").read_text("utf-8"))
    assert report["status"] == "error"
    assert report["planned_action"] == "none"
    assert report["lookup"]["status"] == "ambiguous"
    assert manifest["status"] == "failed"
