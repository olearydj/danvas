import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.asset_state import AssetPlan
from danvas.assignments import (
    ASSIGNMENT_FIELD_POLICIES,
    ASSIGNMENT_VERIFY_SUPPORTED_FIELDS,
    command_assignments_create,
    command_assignments_export,
    command_assignments_update,
    command_assignments_upsert,
    command_assignments_verify,
    comparable_field_value,
    load_assignment_markdown,
    prepare_assignment_asset_report_run,
    resolve_format,
    safe_assignment_mutation_failure,
    verify_assignment_file_links,
    verify_check,
)
from danvas.canvas_links import extract_canvas_file_references
from danvas.source_map import write_source_map_entry


def test_allowed_extension_comparison_normalizes_empty_and_case() -> None:
    assert comparable_field_value("allowed_extensions", None) == []
    assert comparable_field_value("allowed_extensions", []) == []
    assert comparable_field_value("allowed_extensions", [".PDF", "docx"]) == ["docx", "pdf"]


def test_every_supported_assignment_field_has_explicit_comparison_policy() -> None:
    assert set(ASSIGNMENT_FIELD_POLICIES) == ASSIGNMENT_VERIFY_SUPPORTED_FIELDS


def test_asset_content_failure_distinguishes_rejection_from_indeterminate() -> None:
    class BadRequest(Exception):
        pass

    rejected = safe_assignment_mutation_failure(BadRequest("raw response"))
    indeterminate = safe_assignment_mutation_failure(TimeoutError("network timeout"))

    assert rejected["status"] == "content_failed"
    assert rejected["content_mutation_status"] == "failed"
    assert indeterminate["status"] == "content_indeterminate"
    assert indeterminate["content_mutation_status"] == "indeterminate"
    assert "raw response" not in str(rejected)


def test_assignment_datetime_comparison_matches_equivalent_offsets() -> None:
    check = verify_check(
        "due_at",
        "2026-09-01T18:00:00-05:00",
        "2026-09-01T23:00:00Z",
    )

    assert check["matches"] is True


def test_assignment_create_rejects_external_source_before_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas/config.toml").write_text(
        '[canvas]\ncourse_id = 101\napi_url = "https://canvas.example.edu/"\n',
        encoding="utf-8",
    )
    source = tmp_path / "external.md"
    source.write_text("---\ntitle: External\n---\n\nBody\n", encoding="utf-8")
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda _args: pytest.fail("Canvas must not be resolved"),
    )

    with pytest.raises(SystemExit, match="Source is outside the danvas project root"):
        command_assignments_create(SimpleNamespace(source=str(source), project_root=str(project)))


def test_assignment_file_verify_ignores_current_course_page_links() -> None:
    links = extract_canvas_file_references(
        '<a href="/courses/101/pages/syllabus">Syllabus</a>',
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    result = verify_assignment_file_links(
        SimpleNamespace(id=101),
        links,
        links,
        canvas_origin="https://canvas.example/",
    )

    assert result["status"] == "matches"


def test_assignment_source_rejects_offset_free_at_value(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        "---\ntitle: Work\ndue_at: 2026-09-01T23:59:00\n---\n\nSubmit.\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="requires Z or an explicit UTC offset"):
        load_assignment_markdown(source)


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


def test_load_assignment_markdown_ignores_private_override_reference(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Test 2
availability_overrides_ref: grading/25-26.Su/test2-overrides.yaml
---

Submit your work.
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert "availability_overrides_ref" not in payload
    assert payload["name"] == "Test 2"


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


def test_assignment_create_plan_shows_visibility_and_notification_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Case 1
published: true
hide_in_gradebook: true
only_visible_to_overrides: true
notify_of_update: true
unlock_at: 2026-09-01T12:00:00Z
lock_at: 2026-09-08T12:00:00Z
---

Submit the case memo.
""",
        encoding="utf-8",
    )

    command_assignments_create(
        SimpleNamespace(source=str(source), course_id=101, dry_run=True)
    )

    output = capsys.readouterr().out
    projection = json.loads(output[output.index("{") :])
    assert projection["published"] is True
    assert projection["hide_in_gradebook"] is True
    assert projection["only_visible_to_overrides"] is True
    assert projection["notify_of_update"] is True
    assert projection["unlock_at"] == "2026-09-01T12:00:00+00:00"
    assert projection["lock_at"] == "2026-09-08T12:00:00+00:00"


def test_command_assignments_create_dry_run_keeps_stable_canvas_file_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        "---\ntitle: Case 1\n---\n\n"
        "[Case file](/courses/101/files/44?wrap=1)\n",
        encoding="utf-8",
    )

    command_assignments_create(
        SimpleNamespace(
            source=str(source),
            course_id=101,
            dry_run=True,
            api_url="https://canvas.example/",
        )
    )

    output = capsys.readouterr().out
    assert "https://canvas.example/courses/101/files/44?wrap=1" in output
    assert '"description"' not in output


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

    command_assignments_create(
        SimpleNamespace(
            source=str(source),
            course_id=101,
            dry_run=False,
            api_url="https://canvas.example/",
        )
    )

    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    entry = source_map["sources"][0]
    assert entry["kind"] == "assignment"
    assert entry["path"] == "content/assignment.md"
    assert entry["canvas"]["id"] == 10
    assert entry["canvas"]["url"] == "https://canvas.example/courses/101/assignments/10"
    assert entry["last_posted"]["command"] == "assignments create"
    assert entry["last_posted"]["fields"]["title"] == "Case 1"
    assert "body_sha256" in entry["last_posted"]


def test_command_assignments_create_deploys_assets_before_content_and_records_both(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    asset = tmp_path / "assets" / "case.pdf"
    source.parent.mkdir()
    asset.parent.mkdir()
    source.write_text(
        "---\ntitle: Asset case\npublished: false\n---\n\n[Case](../assets/case.pdf)\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"case-pdf")
    source_before = (source.read_bytes(), source.stat().st_mtime_ns)
    events: list[str] = []

    class AssetFolder:
        id = 20
        full_name = "course files/assets"

        def get_files(self) -> list[object]:
            return []

        def upload(self, path: str, *, on_duplicate: str, content_type: str):
            events.append("upload")
            assert on_duplicate == "rename"
            assert content_type == "application/pdf"
            course.files[44] = SimpleNamespace(id=44, folder_id=20)
            return True, {
                "id": 44,
                "display_name": "case.pdf",
                "filename": "case.pdf",
                "folder_id": 20,
                "size": Path(path).stat().st_size,
                "content_type": content_type,
            }

    class AssetCourse:
        id = 101
        name = "Course"

        def __init__(self) -> None:
            self.folder = AssetFolder()
            self.files: dict[int, object] = {}
            self.assignment: SimpleNamespace | None = None

        def get_folders(self) -> list[object]:
            return [self.folder]

        def get_file(self, file_id: int) -> object:
            return self.files[file_id]

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

        def create_assignment(self, payload: dict[str, object]) -> SimpleNamespace:
            events.append("create")
            description = str(payload["description"])
            assert "../assets/case.pdf" not in description
            assert "/courses/101/files/44?wrap=1" in description
            self.assignment = SimpleNamespace(
                id=10,
                name=payload["name"],
                published=payload["published"],
                description=description,
                html_url="https://canvas.example/courses/101/assignments/10",
                updated_at="2026-08-12T12:00:00Z",
            )
            return self.assignment

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            assert assignment_id == 10 and self.assignment is not None
            return self.assignment

    course = AssetCourse()
    canvas = SimpleNamespace(
        get_course=lambda course_id: course,
        get_folder=lambda folder_id: course.folder,
    )
    monkeypatch.setattr("danvas.assignments.canvas_from_args", lambda args: canvas)
    monkeypatch.setattr(
        "danvas.assignments.print_mutation_banner",
        lambda operation, details: events.append("banner"),
    )

    command_assignments_create(
        SimpleNamespace(
            source=str(source),
            course_id=101,
            dry_run=False,
            project_root=str(tmp_path),
            asset_folder=None,
            asset_folder_id=20,
            asset_on_duplicate="error",
            no_report=False,
            report_root=None,
            report_dir=str(tmp_path / "report"),
            report_slug=None,
            api_url="https://canvas.example/",
        )
    )

    assert events == ["banner", "upload", "create"]
    assert (source.read_bytes(), source.stat().st_mtime_ns) == source_before
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert [entry["kind"] for entry in source_map["sources"]] == ["assignment", "file"]
    assignment_entry = source_map["sources"][0]
    fields = assignment_entry["last_posted"]["fields"]
    assert fields["assets"][0]["canvas_file_id"] == 44
    assert fields["source_body_sha256"] != fields["deployed_body_sha256"]
    assert assignment_entry["last_posted"]["body_sha256"] == fields["deployed_body_sha256"]
    evidence = json.loads((tmp_path / "report" / "assignment-assets.json").read_text("utf-8"))
    assert evidence["status"] == "created"
    assert evidence["verification_status"] == "matches"
    assert "case-pdf" not in json.dumps(evidence)
    assert "../assets/case.pdf" not in capsys.readouterr().out


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


def linked_assignment_course(*, live_file_id: int = 44) -> object:
    class LinkedCourse:
        id = 101
        name = "Course"

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            return SimpleNamespace(
                id=assignment_id,
                name="Case 1",
                allowed_extensions=["PDF", ".docx"],
                description=(
                    f'<p><a href="/courses/101/files/{live_file_id}/download?verifier=secret-value" '
                    f'data-api-endpoint="/api/v1/courses/101/files/{live_file_id}" '
                    'data-api-returntype="File">Case file</a></p>'
                ),
                html_url="https://canvas.example/courses/101/assignments/10?token=secret-value",
                secure_params="secret-value",
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

        def get_file(self, file_id: int) -> SimpleNamespace:
            if file_id != 44:
                raise ResourceDoesNotExist("missing?verifier=secret-value")
            return SimpleNamespace(
                id=file_id,
                folder_id=7,
                display_name="case.pdf",
                url="https://canvas.example/files/44/download?verifier=secret-value",
            )

        def get_folders(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=7, full_name="course files/cases")]

    return LinkedCourse()


def test_command_assignments_verify_checks_file_ids_and_allowed_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
assignment_id: 10
title: Case 1
allowed_extensions:
  - pdf
  - docx
---

[Case file](/courses/101/files/44?wrap=1)
""",
        encoding="utf-8",
    )
    course = linked_assignment_course()
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )
    report_dir = tmp_path / "report"

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
            api_url="https://canvas.example/",
        )
    )

    report_text = (report_dir / "assignments-verify.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["status"] == "matches"
    assert report["file_links"]["local_file_id_counts"] == {"44": 1}
    assert report["file_links"]["files"][0]["canvas_path"] == "course files/cases/case.pdf"
    assert report["file_links"]["files"][0]["canvas_url"] == (
        "https://canvas.example/courses/101/files/44?wrap=1"
    )
    assert next(check for check in report["checks"] if check["field"] == "allowed_extensions")[
        "matches"
    ]
    assert "secret-value" not in report_text
    assert "secure_params" not in report_text
    assert "verifier" not in report_text


def test_assignment_verify_file_id_drift_is_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        "---\nassignment_id: 10\ntitle: Case 1\n---\n\n"
        "[Case file](/courses/101/files/44?wrap=1)\n",
        encoding="utf-8",
    )
    course = linked_assignment_course(live_file_id=45)
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    with pytest.raises(SystemExit):
        command_assignments_verify(
            SimpleNamespace(
                source=str(source),
                course_id=101,
                assignment_id=None,
                project_root=str(tmp_path),
                no_report=False,
                report_root=None,
                report_dir=str(tmp_path / "report"),
                report_slug=None,
                api_url="https://canvas.example/",
            )
        )

    report = json.loads((tmp_path / "report" / "assignments-verify.json").read_text("utf-8"))
    assert report["status"] == "mismatch"
    assert report["file_links"]["canvas_file_id_counts"] == {"45": 1}


def test_assignment_verify_file_lookup_failure_is_sanitized_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        "---\nassignment_id: 10\ntitle: Case 1\n---\n\n"
        "[Case file](/courses/101/files/44?wrap=1)\n",
        encoding="utf-8",
    )
    course = linked_assignment_course()

    def fail_file_lookup(file_id: int) -> None:
        raise RuntimeError(
            "GET https://canvas.example/files/44?verifier=secret-value failed"
        )

    monkeypatch.setattr(course, "get_file", fail_file_lookup)
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    with pytest.raises(SystemExit):
        command_assignments_verify(
            SimpleNamespace(
                source=str(source),
                course_id=101,
                assignment_id=None,
                project_root=str(tmp_path),
                no_report=False,
                report_root=None,
                report_dir=str(tmp_path / "report"),
                report_slug=None,
                api_url="https://canvas.example/",
            )
        )

    text = (tmp_path / "report" / "assignments-verify.json").read_text("utf-8")
    report = json.loads(text)
    assert report["status"] == "partial"
    assert report["file_links"]["files"][0]["reason"] == "file_lookup_failed"
    assert "secret-value" not in text
    assert "verifier" not in text


def test_assignment_verify_relative_asset_is_a_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
assignment_id: 10
title: Case 1
omit_from_final_grade: true
---

[Case file](case.pdf)
""",
        encoding="utf-8",
    )

    class PartialCourse:
        id = 101
        name = "Course"

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            return SimpleNamespace(
                id=assignment_id,
                name="Case 1",
                description='<p><a href="case.pdf">Case file</a></p>',
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: PartialCourse()),
    )

    with pytest.raises(SystemExit):
        command_assignments_verify(
            SimpleNamespace(
                source=str(source),
                course_id=101,
                assignment_id=None,
                project_root=str(tmp_path),
                no_report=False,
                report_root=None,
                report_dir=str(tmp_path / "report"),
                report_slug=None,
                api_url="https://canvas.example/",
            )
        )

    report = json.loads((tmp_path / "report" / "assignments-verify.json").read_text("utf-8"))
    assert report["status"] == "mismatch"
    assert report["file_links"]["status"] == "partial"
    assert report["assets"]["status"] == "blocked"
    assert any(check["status"] == "unsupported" for check in report["checks"])


def test_assignment_verify_reuses_mapped_asset_and_matches_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    asset = tmp_path / "assets" / "case.pdf"
    source.parent.mkdir()
    asset.parent.mkdir()
    source.write_text(
        "---\nassignment_id: 10\ntitle: Case 1\n---\n\n[Case](../assets/case.pdf)\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"case-pdf")
    write_source_map_entry(
        kind="file",
        source=asset,
        course_id=101,
        canvas={"course_id": 101, "id": 44, "folder_id": 20},
        command="assignments create",
        fields={
            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            "size": asset.stat().st_size,
            "content_type": "application/pdf",
            "upload_name": "case.pdf",
        },
        project_root=tmp_path,
    )

    class Course:
        id = 101
        name = "Course"

        def get_file(self, file_id: int) -> SimpleNamespace:
            assert file_id == 44
            return SimpleNamespace(id=44, folder_id=20)

        def get_assignment(self, assignment_id: int) -> SimpleNamespace:
            return SimpleNamespace(
                id=assignment_id,
                name="Case 1",
                description='<p><a href="/courses/101/files/44?wrap=1">Case</a></p>',
            )

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return []

        def get_folders(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=20, full_name="course files/assets")]

    course = Course()
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_verify(
        SimpleNamespace(
            source=str(source),
            course_id=101,
            assignment_id=None,
            project_root=str(tmp_path),
            no_report=False,
            report_root=None,
            report_dir=str(tmp_path / "report"),
            report_slug=None,
            api_url="https://canvas.example/",
        )
    )

    report = json.loads((tmp_path / "report" / "assignments-verify.json").read_text("utf-8"))
    assert report["status"] == "matches"
    assert report["assets"]["status"] == "would_reuse"
    assert report["assets"]["verification_status"] == "matches"


def test_assignments_full_export_is_sanitized_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assignment = SimpleNamespace(
        id=10,
        name="Case 1",
        assignment_group_id=7,
        points_possible=100,
        due_at="",
        unlock_at="",
        lock_at="",
        published=True,
        html_url="https://canvas.example/courses/101/assignments/10?token=secret-value",
        submission_types=["online_upload"],
        grading_type="points",
        group_category_id=9,
        allowed_extensions=["pdf"],
        description=(
            '<p><a href="/courses/101/files/44/download?verifier=secret-value">Download</a></p>'
        ),
        secure_params="secret-value",
        storage_quota_mb=500,
        assignment_group_id_date="nonsense",
    )

    class ExportCourse:
        id = 101
        name = "Course"

        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=7, name="Cases")]

        def get_assignments(self, **kwargs: object) -> list[SimpleNamespace]:
            return [assignment]

    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: ExportCourse()),
    )
    output = tmp_path / "assignments.json"

    command_assignments_export(
        SimpleNamespace(
            course_id=101,
            output=str(output),
            format="json",
            full=True,
            api_url="https://canvas.example/",
        )
    )

    text = output.read_text(encoding="utf-8")
    row = json.loads(text)[0]
    assert row["file_ids"] == "44"
    assert row["file_urls"] == "https://canvas.example/courses/101/files/44?wrap=1"
    assert row["extended"]["allowed_extensions"] == ["pdf"]
    assert "secret-value" not in text
    assert "secure_params" not in text
    assert "verifier" not in text
    assert "storage_quota_mb_date" not in text
    assert "assignment_group_id_date" not in text

    csv_output = tmp_path / "assignments.csv"
    command_assignments_export(
        SimpleNamespace(
            course_id=101,
            output=str(csv_output),
            format="csv",
            full=True,
            api_url="https://canvas.example/",
        )
    )
    csv_text = csv_output.read_text(encoding="utf-8")
    assert "file_ids" in csv_text
    assert "44" in csv_text
    assert "secret-value" not in csv_text
    assert "verifier" not in csv_text

    markdown_output = tmp_path / "assignments-md"
    command_assignments_export(
        SimpleNamespace(
            course_id=101,
            output=str(markdown_output),
            format="markdown",
            full=True,
            api_url="https://canvas.example/",
        )
    )
    markdown_text = "\n".join(
        path.read_text(encoding="utf-8") for path in markdown_output.iterdir()
    )
    assert "secret-value" not in markdown_text
    assert "verifier" not in markdown_text


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
        "api_url": "https://canvas.example/",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def upsert_args(source: Path, report_dir: Path, **overrides: object) -> SimpleNamespace:
    defaults = vars(update_args(source, report_dir)).copy()
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_asset_report_destination_is_reserved_before_upload(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case 1\n---\n\nBody\n", encoding="utf-8")
    report_dir = tmp_path / "existing-report"
    report_dir.mkdir()
    plan = {"assets": [{"status": "would_upload"}]}

    with pytest.raises(FileExistsError):
        prepare_assignment_asset_report_run(
            update_args(
                source,
                report_dir,
                dry_run=False,
                project_root=str(tmp_path),
            ),
            "assignments update",
            source,
            cast(AssetPlan, plan),
        )

    assert "_report_run" not in plan


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
        self.created_payload: dict[str, object] | None = None

    def get_assignment(self, assignment_id: int) -> FakeAssignment:
        return self.assignments[int(assignment_id)]

    def get_assignments(self) -> list[FakeAssignment]:
        return list(self.assignments.values())

    def get_assignment_groups(self) -> list[SimpleNamespace]:
        return []

    def create_assignment(self, assignment: dict[str, object]) -> FakeAssignment:
        self.created_payload = assignment
        assignment_id = max(self.assignments.keys(), default=9) + 1
        created = FakeAssignment(
            id=assignment_id,
            name=assignment.get("name", ""),
            points_possible=assignment.get("points_possible", ""),
            published=assignment.get("published", ""),
            description=assignment.get("description", ""),
            html_url=f"https://canvas.example/courses/101/assignments/{assignment_id}",
            updated_at="2026-06-24T12:00:00Z",
        )
        self.assignments[assignment_id] = created
        return created


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


def test_command_assignments_update_deploys_asset_with_one_preupload_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    asset = tmp_path / "assets" / "case.pdf"
    source.parent.mkdir()
    asset.parent.mkdir()
    source.write_text(
        "---\nassignment_id: 10\ntitle: Case 1\n---\n\n[Case](../assets/case.pdf)\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"case-pdf")
    events: list[str] = []
    assignment = FakeAssignment(
        id=10,
        name="Case 1",
        description="<p>Old body.</p>",
        html_url="https://canvas.example/courses/101/assignments/10",
        updated_at="2026-08-12T12:00:00Z",
    )

    class Folder:
        id = 20
        full_name = "course files/assets"

        def get_files(self) -> list[object]:
            return []

        def upload(self, path: str, *, on_duplicate: str, content_type: str):
            events.append("upload")
            course.files[45] = SimpleNamespace(id=45, folder_id=20)
            return True, {
                "id": 45,
                "display_name": "case.pdf",
                "filename": "case.pdf",
                "folder_id": 20,
                "size": Path(path).stat().st_size,
                "content_type": content_type,
            }

    class Course(FakeUpdateCourse):
        def __init__(self) -> None:
            super().__init__([assignment])
            self.folder = Folder()
            self.files: dict[int, object] = {}

        def get_folders(self) -> list[object]:
            return [self.folder]

        def get_file(self, file_id: int) -> object:
            return self.files[file_id]

    course = Course()
    original_edit = assignment.edit

    def tracked_edit(**kwargs: object) -> FakeAssignment:
        events.append("update")
        return original_edit(**kwargs)

    monkeypatch.setattr(assignment, "edit", tracked_edit)
    canvas = SimpleNamespace(
        get_course=lambda course_id: course,
        get_folder=lambda folder_id: course.folder,
    )
    monkeypatch.setattr("danvas.assignments.canvas_from_args", lambda args: canvas)
    monkeypatch.setattr(
        "danvas.assignments.print_mutation_banner",
        lambda operation, details: events.append("banner"),
    )

    command_assignments_update(
        update_args(
            source,
            tmp_path / "report",
            dry_run=False,
            project_root=str(tmp_path),
            asset_folder=None,
            asset_folder_id=20,
            asset_on_duplicate="error",
        )
    )

    assert events == ["banner", "upload", "update"]
    assert "/courses/101/files/45?wrap=1" in str(assignment.description)
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["status"] == "updated"
    assert report["assets"]["verification_status"] == "matches"
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert [row["kind"] for row in source_map["sources"]] == ["assignment", "file"]


def test_command_assignments_update_aliases_round_trip_without_phantom_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n'
        '\n[assignment_groups]\nAssignments = 42\n',
        encoding="utf-8",
    )
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 10
title: Case 1
assignment_group: Assignments
canvas_url: https://canvas.example/courses/101/assignments/10
---

Submit the case memo.
""",
        encoding="utf-8",
    )
    assignment = FakeAssignment(
        id=10,
        name="Case 1",
        assignment_group_id=42,
        description="<p>Submit the case memo.</p>",
        html_url="https://canvas.example/courses/101/assignments/10",
    )

    class GroupCourse(FakeUpdateCourse):
        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=42, name="Assignments")]

    course = GroupCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(update_args(source, tmp_path / "report"))

    assert assignment.edits == []
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["status"] == "no_change"
    checks = {check["field"]: check for check in report["diff"]}
    assert checks["assignment_group_name"]["matches"] is True
    assert checks["canvas_url"]["matches"] is True
    assert report["local"]["assignment_group_name"] == "Assignments"
    assert report["local"]["canvas_url"].endswith("/courses/101/assignments/10")


def test_command_assignments_update_aliases_survive_live_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n'
        '\n[assignment_groups]\nAssignments = 42\n',
        encoding="utf-8",
    )
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 10
title: Case 1
points_possible: 100
assignment_group_name: Assignments
html_url: https://canvas.example/courses/101/assignments/10
---

Submit the case memo.
""",
        encoding="utf-8",
    )
    assignment = FakeAssignment(
        id=10,
        name="Case 1",
        points_possible=90,
        assignment_group_id=42,
        description="<p>Submit the case memo.</p>",
        html_url="https://canvas.example/courses/101/assignments/10",
        updated_at="2026-08-11T12:00:00Z",
    )

    class GroupCourse(FakeUpdateCourse):
        def get_assignment_groups(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=42, name="Assignments")]

    course = GroupCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(
        update_args(source, tmp_path / "report", dry_run=False, project_root=str(tmp_path))
    )

    assert assignment.edits[0]["points_possible"] == 100
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert report["status"] == "updated"
    assert report["readback"]["status"] == "matches"
    fields = source_map["sources"][0]["last_posted"]["fields"]
    assert fields["assignment_group_name"] == "Assignments"
    assert fields["canvas_url"] == "[url]"


def test_assignment_update_report_keeps_same_origin_file_links_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        """---
assignment_id: 10
title: Case 1 revised
---

[Case file](https://canvas.example/courses/101/files/44/download)
""",
        encoding="utf-8",
    )
    assignment = FakeAssignment(id=10, name="Case 1", description="<p>Old body.</p>")
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_update(update_args(source, tmp_path / "report"))

    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["update_payload"]["file_links"][0]["status"] == "valid"


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


def test_command_assignments_upsert_dry_run_includes_asset_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    asset = tmp_path / "assets" / "case.pdf"
    source.parent.mkdir()
    asset.parent.mkdir()
    source.write_text(
        "---\ntitle: Case 1\n---\n\n[Case](../assets/case.pdf)\n",
        encoding="utf-8",
    )
    asset.write_bytes(b"case-pdf")

    class Folder:
        id = 20
        full_name = "course files/assets"

        def get_files(self) -> list[object]:
            return []

    class Course(FakeUpdateCourse):
        def __init__(self) -> None:
            super().__init__([])
            self.folder = Folder()

        def get_folders(self) -> list[object]:
            return [self.folder]

    course = Course()
    canvas = SimpleNamespace(
        get_course=lambda course_id: course,
        get_folder=lambda folder_id: course.folder,
    )
    monkeypatch.setattr("danvas.assignments.canvas_from_args", lambda args: canvas)

    command_assignments_upsert(
        upsert_args(
            source,
            tmp_path / "report",
            project_root=str(tmp_path),
            asset_folder=None,
            asset_folder_id=20,
            asset_on_duplicate="error",
        )
    )

    report = json.loads((tmp_path / "report" / "assignments-upsert.json").read_text("utf-8"))
    assert report["planned_action"] == "create"
    assert report["assets"]["status"] == "planned"
    assert report["assets"]["assets"][0]["status"] == "would_upload"


def test_command_assignments_upsert_refuses_non_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "case.md"
    source.write_text("---\ntitle: Case 1\n---\n\nBody\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="requires --apply --confirm"):
        command_assignments_upsert(upsert_args(source, tmp_path / "report", dry_run=False))


def test_command_assignments_upsert_live_confirmed_create_writes_source_map(
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

    command_assignments_upsert(
        upsert_args(
            source,
            tmp_path / "report",
            dry_run=False,
            confirm="create",
            project_root=str(tmp_path),
        )
    )

    assert course.created_payload is not None
    assert course.created_payload["name"] == "Case 1"
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert source_map["sources"][0]["last_posted"]["command"] == "assignments create"


def test_command_assignments_upsert_live_confirmed_update_writes_update_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text(
        "---\nassignment_id: 10\ntitle: Case 1 revised\n---\n\nSubmit the case memo.\n",
        encoding="utf-8",
    )
    assignment = FakeAssignment(id=10, name="Case 1", description="<p>Old body.</p>")
    course = FakeUpdateCourse([assignment])
    monkeypatch.setattr(
        "danvas.assignments.canvas_from_args",
        lambda args: SimpleNamespace(get_course=lambda course_id: course),
    )

    command_assignments_upsert(
        upsert_args(
            source,
            tmp_path / "report",
            dry_run=False,
            confirm="update",
            project_root=str(tmp_path),
        )
    )

    assert assignment.edits
    report = json.loads((tmp_path / "report" / "assignments-update.json").read_text("utf-8"))
    assert report["status"] == "updated"
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert source_map["sources"][0]["last_posted"]["command"] == "assignments update"


def test_command_assignments_upsert_live_refuses_confirm_mismatch(
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

    with pytest.raises(SystemExit, match="refusing --confirm 'update'"):
        command_assignments_upsert(
            upsert_args(
                source,
                tmp_path / "report",
                dry_run=False,
                confirm="update",
                project_root=str(tmp_path),
            )
        )

    assert course.created_payload is None


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
