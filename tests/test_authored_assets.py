from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.authored_assets import (
    execute_asset_plan,
    prepare_asset_plan,
    public_asset_evidence,
    rewrite_authored_html,
    scan_authored_assets,
    verify_asset_readback,
)
from danvas.source_map import write_source_map_entry

CANVAS_ORIGIN = "https://canvas.example/"


def write_config(root: Path, course_id: int = 101) -> None:
    config = root / ".danvas"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[canvas]\ncourse_id = {course_id}\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )


class FakeFolder(SimpleNamespace):
    def __init__(self, *, files: list[object] | None = None) -> None:
        super().__init__(id=20, full_name="course files/assets")
        self.files = list(files or [])
        self.uploads: list[dict[str, str]] = []

    def get_files(self) -> list[object]:
        return list(self.files)

    def upload(self, source: str, *, on_duplicate: str, content_type: str):
        self.uploads.append(
            {"source": source, "on_duplicate": on_duplicate, "content_type": content_type}
        )
        file_id = 900 + len(self.uploads)
        return True, {
            "id": file_id,
            "display_name": Path(source).name,
            "filename": Path(source).name,
            "folder_id": self.id,
            "size": Path(source).stat().st_size,
            "content_type": content_type,
        }


class FakeCourse:
    id = 101

    def __init__(self, folder: FakeFolder | None = None) -> None:
        self.folder = folder or FakeFolder()
        self.remote: dict[int, object] = {}

    def get_folders(self) -> list[object]:
        return [self.folder]

    def get_file(self, file_id: int) -> object:
        return self.remote[file_id]


class FakeCanvas:
    def __init__(self, course: FakeCourse) -> None:
        self.course = course

    def get_folder(self, folder_id: int) -> FakeFolder:
        assert folder_id == self.course.folder.id
        return self.course.folder


def source_with_assets(root: Path) -> tuple[Path, Path, Path]:
    source = root / "content" / "assignment.md"
    pdf = root / "assets" / "case.pdf"
    image = root / "assets" / "diagram.png"
    source.parent.mkdir(parents=True)
    pdf.parent.mkdir()
    source.write_text("source stays unchanged", encoding="utf-8")
    pdf.write_bytes(b"pdf-data")
    image.write_bytes(b"png-data")
    return source, pdf, image


def test_scan_is_structural_deduplicated_and_preserves_occurrences(tmp_path: Path) -> None:
    source, _pdf, _image = source_with_assets(tmp_path)
    html = (
        '<p><a href="../assets/case.pdf#page=2">Case</a>'
        '<a href="../assets/case.pdf">Again</a>'
        '<img class="wide" alt="Diagram" src="../assets/diagram.png"></p>'
    )

    result = scan_authored_assets(
        html,
        source=source,
        project_root=tmp_path,
        current_course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )

    assert result["blocked"] == []
    assert [row["path"] for row in result["assets"]] == [
        "assets/case.pdf",
        "assets/diagram.png",
    ]
    assert result["assets"][0]["occurrence_count"] == 2
    assert result["assets"][0]["occurrences"][0]["fragment"] == "page=2"


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("/assets/case.pdf", "blocked_root_relative"),
        ("data:text/plain,secret", "unsafe_url_scheme"),
        ("https://user:pass@example.com/file.pdf", "unsafe_url_scheme"),
        ("https://example.com/file.pdf?x-amz-signature=secret", "unsafe_url_scheme"),
        ("../missing.txt", "asset_missing"),
        ("assignment.md", "authored_source_not_uploadable"),
        (
            "/courses/101/files/44/download?verifier=secret",
            "volatile_canvas_file_url",
        ),
        ("../assets/diagram.png 2x", "unsupported_local_attribute"),
    ],
)
def test_scan_blocks_unsafe_or_unresolved_references(
    tmp_path: Path, value: str, reason: str
) -> None:
    source, _pdf, _image = source_with_assets(tmp_path)

    html = (
        f'<img srcset="{value}">'
        if reason == "unsupported_local_attribute"
        else f'<a href="{value}">Target</a>'
    )
    result = scan_authored_assets(
        html,
        source=source,
        project_root=tmp_path,
        current_course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )

    assert result["assets"] == []
    assert result["blocked"][0]["reason"] == reason
    assert "secret" not in str(result)


def test_blocked_plan_does_not_initialize_canvas(tmp_path: Path) -> None:
    write_config(tmp_path)
    source, _pdf, _image = source_with_assets(tmp_path)

    def fail_loader() -> tuple[object, object]:
        raise AssertionError("Canvas must not initialize for a blocked local reference")

    plan = prepare_asset_plan(
        '<a href="../missing.txt">Missing</a>',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=None,
        canvas=None,
        folder=None,
        folder_id=None,
        on_duplicate="error",
        canvas_loader=fail_loader,
    )

    assert plan is not None and plan["status"] == "blocked"
    assert plan["blocked"][0]["reason"] == "asset_missing"


def test_blocked_root_relative_link_is_reported_before_project_requirement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "assignment.md"
    source.write_text("source stays unchanged", encoding="utf-8")

    plan = prepare_asset_plan(
        '<a href="/courses/202/pages/syllabus">Syllabus</a>',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=None,
        canvas=None,
        folder=None,
        folder_id=None,
        on_duplicate="error",
    )

    assert plan is not None and plan["status"] == "blocked"
    assert plan["blocked"][0]["reason"] == "blocked_root_relative"


def test_new_asset_plan_uploads_rewrites_and_records_immediate_identity(tmp_path: Path) -> None:
    write_config(tmp_path)
    source, _pdf, _image = source_with_assets(tmp_path)
    folder = FakeFolder()
    course = FakeCourse(folder)
    canvas = FakeCanvas(course)
    original = '<p><a href="../assets/case.pdf#p2">Case</a></p>'

    plan = prepare_asset_plan(
        original,
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=canvas,
        folder=None,
        folder_id=20,
        on_duplicate="error",
    )

    assert plan is not None and plan["status"] == "planned"
    assert plan["assets"][0]["status"] == "would_upload"
    completed = execute_asset_plan(
        plan,
        folder=folder,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        command="assignments create",
        project_root=tmp_path,
        on_duplicate="error",
    )

    assert completed["status"] == "deployed"
    assert completed["assets"][0]["status"] == "uploaded"
    assert completed["rewritten_html"] == (
        '<p><a href="https://canvas.example/courses/101/files/901?wrap=1#p2">Case</a></p>'
    )
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    entry = source_map["sources"][0]
    assert entry["kind"] == "file"
    assert entry["canvas"] == {
        "course_id": 101,
        "display_name": "case.pdf",
        "folder_id": 20,
        "id": 901,
        "path": "course files/assets/case.pdf",
        "url": "https://canvas.example/courses/101/files/901?wrap=1",
    }
    assert "source_path" not in json.dumps(public_asset_evidence(completed))


def test_same_basename_assets_block_before_upload_under_error_policy(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    first = tmp_path / "assets" / "a" / "logo.png"
    second = tmp_path / "assets" / "b" / "logo.png"
    source.parent.mkdir(parents=True)
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    source.write_text("source stays unchanged", encoding="utf-8")
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    folder = FakeFolder()
    course = FakeCourse(folder)

    plan = prepare_asset_plan(
        '<img src="../assets/a/logo.png"><img src="../assets/b/logo.png">',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=FakeCanvas(course),
        folder=None,
        folder_id=20,
        on_duplicate="error",
    )

    assert plan is not None and plan["status"] == "blocked"
    assert [asset["status"] for asset in plan["assets"]] == ["conflict", "conflict"]
    assert {asset["reason"] for asset in plan["assets"]} == {
        "duplicate_local_destination_name"
    }
    assert folder.uploads == []


def test_same_basename_assets_plan_deterministic_rename_sequence(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "assignment.md"
    first = tmp_path / "assets" / "a" / "logo.png"
    second = tmp_path / "assets" / "b" / "logo.png"
    source.parent.mkdir(parents=True)
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    source.write_text("source stays unchanged", encoding="utf-8")
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    class UpdatingFolder(FakeFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            self.uploads.append(
                {"source": source, "on_duplicate": on_duplicate, "content_type": content_type}
            )
            file_id = 900 + len(self.uploads)
            display_name = "logo.png" if len(self.uploads) == 1 else "logo-1.png"
            record = SimpleNamespace(
                id=file_id,
                display_name=display_name,
                filename=display_name,
                folder_id=self.id,
            )
            self.files.append(record)
            return True, {
                "id": file_id,
                "display_name": display_name,
                "filename": display_name,
                "folder_id": self.id,
                "size": Path(source).stat().st_size,
                "content_type": content_type,
            }

    folder = UpdatingFolder()
    course = FakeCourse(folder)

    plan = prepare_asset_plan(
        '<img src="../assets/a/logo.png"><img src="../assets/b/logo.png">',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=FakeCanvas(course),
        folder=None,
        folder_id=20,
        on_duplicate="rename",
    )

    assert plan is not None and plan["status"] == "planned"
    assert [asset["status"] for asset in plan["assets"]] == [
        "would_upload",
        "would_rename",
    ]
    evidence = public_asset_evidence(plan)
    assert evidence is not None
    assert evidence["deployed_body_status"] == "pending_canvas_file_ids"

    completed = execute_asset_plan(
        plan,
        folder=folder,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        command="assignments update",
        project_root=tmp_path,
        on_duplicate="rename",
    )

    assert completed["status"] == "deployed"
    assert [asset["status"] for asset in completed["assets"]] == ["uploaded", "renamed"]
    assert [asset["canvas"]["id"] for asset in completed["assets"]] == [901, 902]


def test_later_upload_failure_leaves_earlier_file_identity_reusable(tmp_path: Path) -> None:
    write_config(tmp_path)
    source, _pdf, _image = source_with_assets(tmp_path)

    class PartlyFailingFolder(FakeFolder):
        def upload(self, source: str, *, on_duplicate: str, content_type: str):
            if self.uploads:
                self.uploads.append({"source": source})
                return False, {"message": "upload failed"}
            return super().upload(
                source,
                on_duplicate=on_duplicate,
                content_type=content_type,
            )

    folder = PartlyFailingFolder()
    course = FakeCourse(folder)
    plan = prepare_asset_plan(
        '<a href="../assets/case.pdf">Case</a><img src="../assets/diagram.png">',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=FakeCanvas(course),
        folder=None,
        folder_id=20,
        on_duplicate="error",
    )
    assert plan is not None

    completed = execute_asset_plan(
        plan,
        folder=folder,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        command="assignments update",
        project_root=tmp_path,
        on_duplicate="error",
    )

    assert completed["status"] == "failed"
    assert completed["mutation_status"] == "partial"
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text("utf-8"))
    assert len(source_map["sources"]) == 1
    assert source_map["sources"][0]["path"] == "assets/case.pdf"


def test_source_map_failure_stops_plan_with_safe_known_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path)
    source, _pdf, _image = source_with_assets(tmp_path)
    folder = FakeFolder()
    course = FakeCourse(folder)
    plan = prepare_asset_plan(
        '<a href="../assets/case.pdf">Case</a>',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=FakeCanvas(course),
        folder=None,
        folder_id=20,
        on_duplicate="error",
    )
    assert plan is not None
    monkeypatch.setattr(
        "danvas.authored_assets.write_source_map_entry",
        lambda **kwargs: (_ for _ in ()).throw(OSError("/private/secret/path")),
    )

    completed = execute_asset_plan(
        plan,
        folder=folder,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        command="assignments create",
        project_root=tmp_path,
        on_duplicate="error",
    )

    assert completed["status"] == "failed"
    evidence = public_asset_evidence(completed)
    assert evidence is not None
    assert evidence["assets"][0]["canvas"]["id"] == 901
    assert "/private/secret/path" not in json.dumps(evidence)
    assert "Do not retry" in evidence["recovery_guidance"]


def test_local_change_after_plan_stops_before_upload(tmp_path: Path) -> None:
    write_config(tmp_path)
    source, pdf, _image = source_with_assets(tmp_path)
    folder = FakeFolder()
    course = FakeCourse(folder)
    html = '<a href="../assets/case.pdf">Case</a>'
    plan = prepare_asset_plan(
        html,
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=FakeCanvas(course),
        folder=None,
        folder_id=20,
        on_duplicate="error",
    )
    assert plan is not None
    pdf.write_bytes(b"changed-after-plan")

    completed = execute_asset_plan(
        plan,
        folder=folder,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        command="assignments create",
        project_root=tmp_path,
        on_duplicate="error",
    )

    assert completed["status"] == "failed"
    assert completed["mutation_status"] == "not_started"
    assert folder.uploads == []


def test_unchanged_mapped_asset_reuses_without_destination(tmp_path: Path) -> None:
    write_config(tmp_path)
    source, pdf, _image = source_with_assets(tmp_path)
    write_source_map_entry(
        kind="file",
        source=pdf,
        course_id=101,
        canvas={"course_id": 101, "id": 44, "folder_id": 20},
        command="assignments create",
        fields={
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "size": pdf.stat().st_size,
            "content_type": "application/pdf",
            "upload_name": "case.pdf",
        },
        project_root=tmp_path,
    )
    course = FakeCourse()
    course.remote[44] = SimpleNamespace(id=44, folder_id=20)

    plan = prepare_asset_plan(
        '<a href="../assets/case.pdf">Case</a>',
        source=source,
        project_root=tmp_path,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
        course=course,
        canvas=None,
        folder=None,
        folder_id=None,
        on_duplicate="error",
    )

    assert plan is not None and plan["status"] == "would_reuse"
    assert plan["assets"][0]["status"] == "would_reuse"
    assert "/courses/101/files/44?wrap=1" in plan["rewritten_html"]


def test_rewrite_uses_image_preview_and_preserves_authored_attributes(tmp_path: Path) -> None:
    source, _pdf, _image = source_with_assets(tmp_path)
    scan = scan_authored_assets(
        '<img alt="Diagram" class="wide" src="../assets/diagram.png#detail">',
        source=source,
        project_root=tmp_path,
        current_course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )
    scan["assets"][0]["canvas"] = {"id": 55, "course_id": 101}

    rewritten = rewrite_authored_html(
        '<img alt="Diagram" class="wide" src="../assets/diagram.png#detail">',
        scan["assets"],
        101,
        CANVAS_ORIGIN,
    )

    assert rewritten == (
        '<img alt="Diagram" class="wide" src="/courses/101/files/55/preview#detail"/>'
    )


def test_rewrite_positions_include_urls_that_do_not_need_asset_classification(
    tmp_path: Path,
) -> None:
    source, _pdf, _image = source_with_assets(tmp_path)
    html = (
        '<a href="https://example.com/reference">Reference</a>'
        '<a href="../assets/case.pdf">Case</a>'
    )
    scan = scan_authored_assets(
        html,
        source=source,
        project_root=tmp_path,
        current_course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )
    scan["assets"][0]["canvas"] = {"id": 44, "course_id": 101}

    assert scan["assets"][0]["occurrences"][0]["occurrence"] == 2
    assert rewrite_authored_html(html, scan["assets"], 101, CANVAS_ORIGIN) == (
        '<a href="https://example.com/reference">Reference</a>'
        '<a href="https://canvas.example/courses/101/files/44?wrap=1">Case</a>'
    )


def test_verify_readback_checks_identity_count_and_recorded_folder() -> None:
    assets = [
        {
            "canvas": {"course_id": 101, "id": 44, "folder_id": 20},
            "occurrences": [{"tag": "a", "attribute": "href"}],
        }
    ]
    course = FakeCourse()
    course.remote[44] = SimpleNamespace(id=44, folder_id=21)
    expected = '<a href="https://canvas.example/courses/101/files/44?wrap=1">Case</a>'

    result = verify_asset_readback(
        assets,
        '<a href="/courses/101/files/44/download">Case</a>',
        expected_html=expected,
        course=course,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )

    assert result["status"] == "mismatch"
    assert result["files"] == [{"file_id": 44, "status": "folder_mismatch", "folder_id": 21}]


def test_verify_readback_rejects_retained_volatile_query() -> None:
    assets = [
        {
            "canvas": {"course_id": 101, "id": 44, "folder_id": 20},
            "occurrences": [{"tag": "a", "attribute": "href"}],
        }
    ]
    course = FakeCourse()
    course.remote[44] = SimpleNamespace(id=44, folder_id=20)
    expected = '<a href="https://canvas.example/courses/101/files/44?wrap=1">Case</a>'

    result = verify_asset_readback(
        assets,
        '<a href="/courses/101/files/44/download?verifier=ephemeral">Case</a>',
        expected_html=expected,
        course=course,
        course_id=101,
        canvas_origin=CANVAS_ORIGIN,
    )

    assert result["status"] == "mismatch"
    assert result["invalid"][0]["volatile_query_present"] is True
    assert result["invalid"][0]["volatile_query_names"] == ["verifier"]
    assert "ephemeral" not in str(result)
