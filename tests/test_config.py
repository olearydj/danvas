import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from canvasapi.exceptions import Forbidden, InvalidAccessToken, RateLimitExceeded

from danvas import config
from danvas.assignments import command_assignments_create
from danvas.cli import args_for


class FakeCourse:
    id = 1742717
    name = "INSY 6600"
    course_code = "INSY6600"

    def get_assignment_groups(self):
        return [
            SimpleNamespace(id=20, name="Case Studies", group_weight=25),
            SimpleNamespace(id=10, name="Quizzes", group_weight=15),
        ]

    def get_assignments(self, include=None):
        return [
            SimpleNamespace(
                id=100,
                name="Case Study 1",
                assignment_group_id=20,
                points_possible=100,
                due_at="2026-06-15T04:59:00Z",
                unlock_at="",
                lock_at="2026-06-15T04:59:59Z",
                published=True,
                html_url="https://canvas.test/assignments/100",
                submission_types=["online_upload"],
                description="<p>Submit files.</p>",
                all_dates=[
                    {
                        "id": None,
                        "title": "Everyone else",
                        "base": True,
                        "due_at": "2026-06-15T04:59:00Z",
                        "unlock_at": None,
                        "lock_at": "2026-06-15T04:59:59Z",
                    },
                    {
                        "id": 900,
                        "title": "Extension",
                        "base": False,
                        "due_at": "2026-06-17T04:59:59Z",
                        "student_ids": [10, 11],
                    },
                ],
                overrides=[
                    {
                        "id": 900,
                        "title": "Extension",
                        "due_at": "2026-06-17T04:59:59Z",
                        "student_ids": [10, 11],
                    }
                ],
            )
        ]

    def get_folders(self):
        return [
            SimpleNamespace(id=1, name="course files", full_name="course files"),
            SimpleNamespace(id=2, name="Case Studies", full_name="course files/Case Studies"),
        ]

    def get_files(self):
        return [
            SimpleNamespace(
                id=300,
                display_name="case1.pdf",
                filename="case1.pdf",
                folder_id=2,
                size=1234,
                content_type="application/pdf",
                created_at="2026-06-01T00:00:00Z",
                updated_at="2026-06-02T00:00:00Z",
                url="https://canvas.test/files/300/download?verifier=secret-token",
            )
        ]

    def get_discussion_topics(self, **kwargs):
        if kwargs.get("only_announcements"):
            return [
                SimpleNamespace(
                    id=401,
                    title="Welcome",
                    html_url="https://canvas.test/announcements/401",
                    posted_at="2026-06-01T12:00:00Z",
                    message="<p>Hello class</p>",
                    published=True,
                )
            ]
        return [
            SimpleNamespace(
                id=402,
                title="Case Discussion",
                html_url="https://canvas.test/discussion_topics/402",
                assignment_id=99,
                published=True,
                locked=False,
                message="<p>Discuss the case</p>",
            )
        ]

    def get_quizzes(self):
        return [
            SimpleNamespace(
                id=500,
                assignment_id=98,
                title="Chapter 7 Quiz",
                description="<p>Covers chapter 7</p>",
                quiz_type="assignment",
                points_possible=20,
                question_count=10,
                due_at="2026-06-20T04:59:00Z",
                unlock_at="",
                lock_at="",
                published=True,
                time_limit=30,
                allowed_attempts=2,
                html_url="https://canvas.test/quizzes/500",
            )
        ]

    def get_group_categories(self):
        category = SimpleNamespace(id=700, name="Case 1 Groups", self_signup=None)
        category.get_groups = lambda: [
            SimpleNamespace(id=701, name="Group A", members_count=4),
            SimpleNamespace(id=702, name="Group B", members_count=4),
        ]
        return [category]

    def get_pages(self):
        return [
            SimpleNamespace(
                page_id=601,
                url="resources",
                title="Resources",
                published=True,
                front_page=False,
                editing_roles="teachers",
                updated_at="2026-06-10T00:00:00Z",
                body="",
            ),
            SimpleNamespace(
                page_id=602,
                url="external",
                title="External",
                published=False,
                front_page=False,
                updated_at="2026-06-11T00:00:00Z",
                body='<p><a href="https://cdn.test/item?X-Amz-Signature=secret-token">X</a></p>',
            ),
        ]

    def get_page(self, url):
        assert url == "resources"
        return SimpleNamespace(
            page_id=601,
            url="resources",
            html_url="https://canvas.test/courses/1742717/pages/resources",
            title="Resources",
            published=True,
            front_page=False,
            editing_roles="teachers",
            updated_at="2026-06-10T00:00:00Z",
            body=(
                '<p><a href="https://canvas.test/courses/1742717/files/300/download'
                '?verifier=secret-token">File</a></p>'
            ),
        )


def test_write_project_config_and_snapshot(tmp_path: Path) -> None:
    snapshot = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    config_path = tmp_path / ".danvas" / "config.toml"
    snapshot_path = tmp_path / ".danvas" / "course.json"

    config.write_project_config(
        config_path,
        course_snapshot=snapshot,
        api_url="https://auburn.instructure.com/",
        timezone="America/Chicago",
    )
    config.write_course_snapshot(snapshot_path, snapshot)

    text = config_path.read_text(encoding="utf-8")
    assert "[canvas]" in text
    assert 'course_name = "INSY 6600"' in text
    assert '"Case Studies" = 20' in text
    assert config.resolve_course_id(None, start=tmp_path) == 1742717
    assert config.resolve_assignment_group_id("Case Studies", start=tmp_path) == 20

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["course"]["id"] == 1742717
    assert payload["assignments"][0]["assignment_group_name"] == "Case Studies"
    assert payload["assignments"][0]["has_overrides"] is True
    assert payload["assignments"][0]["all_dates"][1]["assignee_count"] == 2
    assert payload["folders"][1]["full_name"] == "course files/Case Studies"


def test_write_project_config_records_profile_and_omits_unknown_timezone(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / ".danvas" / "config.toml"

    config.write_project_config(
        config_path,
        course_snapshot={
            "course": {"id": 1, "name": "Course"},
            "assignment_groups": [],
        },
        api_url="https://canvas.example/",
        timezone=None,
        profile="institution-a",
    )

    text = config_path.read_text(encoding="utf-8")
    assert 'profile = "institution-a"' in text
    assert "timezone" not in text


def test_init_timezone_prefers_explicit_then_canvas_then_profile() -> None:
    course = SimpleNamespace(time_zone="Central Time (US & Canada)")

    assert (
        config.resolve_init_timezone(
            SimpleNamespace(timezone="America/New_York", profile_timezone="America/Denver"),
            course,
        )
        == "America/New_York"
    )
    assert (
        config.resolve_init_timezone(
            SimpleNamespace(timezone=None, profile_timezone="America/Denver"), course
        )
        == "America/Chicago"
    )
    assert (
        config.resolve_init_timezone(
            SimpleNamespace(timezone=None, profile_timezone="America/Denver"),
            SimpleNamespace(time_zone="Unknown Canvas Zone"),
        )
        == "America/Denver"
    )


def test_init_timezone_leaves_unknown_unconfigured(capsys) -> None:
    timezone = config.resolve_init_timezone(
        SimpleNamespace(timezone=None, profile_timezone=None),
        SimpleNamespace(time_zone="Unknown Canvas Zone"),
    )

    assert timezone is None
    error = capsys.readouterr().err
    assert "will not guess" in error
    assert "Date-only assignment metadata is unavailable" in error


def test_build_course_snapshot_includes_expanded_sections() -> None:
    snapshot = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")

    assert snapshot["schema_version"] == config.SNAPSHOT_SCHEMA_VERSION

    file_record = snapshot["files"][0]
    assert file_record["display_name"] == "case1.pdf"
    assert file_record["folder_full_name"] == "course files/Case Studies"
    assert file_record["size"] == 1234

    discussion = snapshot["discussions"][0]
    assert discussion["title"] == "Case Discussion"
    assert discussion["assignment_id"] == 99
    assert discussion["message_text"] == "Discuss the case"

    announcement = snapshot["announcements"][0]
    assert announcement["title"] == "Welcome"
    assert announcement["message_text"] == "Hello class"

    quiz = snapshot["quizzes"][0]
    assert quiz["title"] == "Chapter 7 Quiz"
    assert quiz["assignment_id"] == 98
    assert quiz["points_possible"] == 20
    assert quiz["time_limit"] == 30

    category = snapshot["group_categories"][0]
    assert category["name"] == "Case 1 Groups"
    assert category["group_count"] == 2
    assert category["member_count"] == 8
    assert [group["name"] for group in category["groups"]] == ["Group A", "Group B"]

    external, resources = snapshot["pages"]
    assert resources["url"] == "resources"
    assert resources["body_hash_status"] == "available"
    assert resources["body_sha256"]
    assert external["body_hash_status"] == "blocked_volatile_url"
    assert external["body_sha256"] is None
    assert external["volatile_url_count"] == 1


def test_build_course_snapshot_contains_no_secrets_or_member_lists() -> None:
    snapshot = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    text = json.dumps(snapshot)

    assert "verifier" not in text
    assert "secret-token" not in text
    for category in snapshot["group_categories"]:
        for group in category["groups"]:
            assert set(group) == {"id", "name", "members_count"}
    assert "student_ids" not in json.dumps(snapshot["assignments"][0])


def test_build_course_snapshot_marks_optional_forbidden_collection_unavailable() -> None:
    class ForbiddenCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            raise Forbidden("secret response https://canvas.test/?verifier=sentinel")

    snapshot = config.build_course_snapshot(
        ForbiddenCategoriesCourse(), canvas_origin="https://canvas.test/"
    )

    assert snapshot["schema_version"] == 5
    assert snapshot["snapshot_status"] == "partial"
    assert snapshot["assignments"]
    assert snapshot["group_categories"] == []
    assert snapshot["collections"]["group_categories"] == {
        "status": "unavailable",
        "authoritative": False,
        "item_count": 0,
        "reason": "forbidden",
        "error_type": "Forbidden",
    }
    serialized = json.dumps(snapshot)
    assert "sentinel" not in serialized
    assert "verifier" not in serialized


def test_build_course_snapshot_retains_nested_group_category_partial_state() -> None:
    class NestedForbiddenCourse(FakeCourse):
        def get_group_categories(self):
            category = SimpleNamespace(id=700, name="Case 1 Groups", self_signup=None)

            def forbidden_groups():
                raise Forbidden("private nested response")

            category.get_groups = forbidden_groups
            return [category]

    snapshot = config.build_course_snapshot(NestedForbiddenCourse())

    metadata = snapshot["collections"]["group_categories"]
    assert metadata["status"] == "partial"
    assert metadata["authoritative"] is False
    assert metadata["reason"] == "nested_collection_unavailable"
    category = snapshot["group_categories"][0]
    assert category["groups_status"] == "unavailable"
    assert category["groups_reason"] == "forbidden"
    assert category["group_count"] is None
    assert category["member_count"] is None
    assert category["groups"] == []


def test_build_course_snapshot_distinguishes_available_empty_group_categories() -> None:
    class EmptyCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            return []

    snapshot = config.build_course_snapshot(EmptyCategoriesCourse())

    assert snapshot["group_categories"] == []
    assert snapshot["collections"]["group_categories"] == {
        "status": "available",
        "authoritative": True,
        "item_count": 0,
    }
    assert snapshot["snapshot_status"] == "complete"


def test_build_course_snapshot_classifies_rate_limit_before_forbidden() -> None:
    class RateLimitedCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            raise RateLimitExceeded("secret rate-limit response")

    snapshot = config.build_course_snapshot(RateLimitedCategoriesCourse())

    metadata = snapshot["collections"]["group_categories"]
    assert metadata["status"] == "failed"
    assert metadata["reason"] == "rate_limited"
    assert metadata["error_type"] == "RateLimitExceeded"


def test_invalid_token_is_fatal_in_optional_collection_and_stops_later_calls() -> None:
    class InvalidTokenCourse(FakeCourse):
        group_categories_called = False

        def get_pages(self):
            raise InvalidAccessToken("token=secret-value")

        def get_group_categories(self):
            self.group_categories_called = True
            return super().get_group_categories()

    course = InvalidTokenCourse()

    with pytest.raises(SystemExit, match="access token is invalid") as exc_info:
        config.build_course_snapshot(course)

    assert "secret-value" not in str(exc_info.value)
    assert course.group_categories_called is False


def test_invalid_token_is_fatal_at_nested_collection_boundary() -> None:
    class NestedInvalidTokenCourse(FakeCourse):
        def get_group_categories(self):
            category = SimpleNamespace(id=700, name="Case 1 Groups", self_signup=None)

            def invalid_groups():
                raise InvalidAccessToken("access_token=secret-value")

            category.get_groups = invalid_groups
            return [category]

    with pytest.raises(SystemExit, match="access token is invalid") as exc_info:
        config.build_course_snapshot(NestedInvalidTokenCourse())

    assert "secret-value" not in str(exc_info.value)


def test_invalid_token_preserves_existing_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()
    snapshot_path = tmp_path / ".danvas" / "course.json"
    previous = b'{"sentinel": "previous snapshot"}\n'
    snapshot_path.write_bytes(previous)

    class InvalidTokenCourse(FakeCourse):
        def get_pages(self):
            raise InvalidAccessToken("access_token=secret-value")

    class FakeCanvas:
        def get_course(self, course_id: int):
            return InvalidTokenCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())

    with pytest.raises(SystemExit, match="access token is invalid"):
        config.command_refresh(
            SimpleNamespace(project_root=str(tmp_path), course_id=1742717, diff=False)
        )

    assert snapshot_path.read_bytes() == previous


def test_folder_failure_blocks_files_without_calling_file_endpoint() -> None:
    class ForbiddenFoldersCourse(FakeCourse):
        files_called = False

        def get_folders(self):
            raise Forbidden("private folder response")

        def get_files(self):
            self.files_called = True
            return super().get_files()

    course = ForbiddenFoldersCourse()
    snapshot = config.build_course_snapshot(course)

    assert course.files_called is False
    assert snapshot["collections"]["folders"]["status"] == "unavailable"
    assert snapshot["collections"]["files"] == {
        "status": "unavailable",
        "authoritative": False,
        "item_count": 0,
        "reason": "dependency_unavailable",
        "error_type": "Forbidden",
        "dependency": "folders",
    }


def test_required_collection_failure_is_bounded_and_not_swallowed() -> None:
    class ForbiddenAssignmentsCourse(FakeCourse):
        def get_assignments(self, include=None):
            raise Forbidden("secret response body")

    with pytest.raises(SystemExit, match="assignments.*unavailable.*forbidden") as exc_info:
        config.build_course_snapshot(ForbiddenAssignmentsCourse())

    assert "secret response body" not in str(exc_info.value)


def test_required_collection_failure_leaves_previous_snapshot_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()
    snapshot_path = tmp_path / ".danvas" / "course.json"
    previous = b'{"sentinel": "previous snapshot"}\n'
    snapshot_path.write_bytes(previous)

    class ForbiddenAssignmentsCourse(FakeCourse):
        def get_assignments(self, include=None):
            raise Forbidden("secret response body")

    class FakeCanvas:
        def get_course(self, course_id: int):
            return ForbiddenAssignmentsCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(project_root=str(tmp_path), course_id=1742717, diff=False)

    with pytest.raises(SystemExit, match="assignments.*unavailable"):
        config.command_refresh(args)

    assert snapshot_path.read_bytes() == previous


def test_command_refresh_writes_partial_snapshot_with_bounded_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".danvas").mkdir()

    class ForbiddenCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            raise Forbidden("secret response https://canvas.test/?verifier=sentinel")

    class FakeCanvas:
        def get_course(self, course_id: int):
            return ForbiddenCategoriesCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(project_root=str(tmp_path), course_id=1742717, diff=False)

    config.command_refresh(args)

    captured = capsys.readouterr()
    assert "group_categories is unavailable (forbidden)" in captured.err
    assert "group_categories is unavailable" not in captured.out
    assert "sentinel" not in captured.err
    assert "verifier" not in captured.err
    snapshot = json.loads(
        (tmp_path / ".danvas" / "course.json").read_text(encoding="utf-8")
    )
    assert snapshot["snapshot_status"] == "partial"
    assert snapshot["collections"]["group_categories"]["authoritative"] is False


def test_refresh_require_complete_preserves_previous_snapshot_and_skips_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".danvas").mkdir()
    snapshot_path = tmp_path / ".danvas" / "course.json"
    previous = b'{"sentinel": "previous snapshot"}\n'
    snapshot_path.write_bytes(previous)

    class ForbiddenCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            raise Forbidden("private response")

    class FakeCanvas:
        def get_course(self, course_id: int):
            return ForbiddenCategoriesCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        project_root=str(tmp_path),
        course_id=1742717,
        diff=True,
        require_complete=True,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        config.command_refresh(args)

    assert exc_info.value.code == config.PARTIAL_SNAPSHOT_EXIT_CODE
    assert snapshot_path.read_bytes() == previous
    assert not (tmp_path / "report").exists()
    assert "prevents refresh state from being written" in capsys.readouterr().err


def test_complete_refresh_succeeds_with_require_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".danvas").mkdir()

    class FakeCanvas:
        def get_course(self, course_id: int):
            return FakeCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    config.command_refresh(
        SimpleNamespace(
            project_root=str(tmp_path),
            course_id=1742717,
            diff=False,
            require_complete=True,
        )
    )

    snapshot = json.loads(
        (tmp_path / ".danvas" / "course.json").read_text(encoding="utf-8")
    )
    assert snapshot["snapshot_status"] == "complete"


def test_init_require_complete_writes_no_project_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ForbiddenCategoriesCourse(FakeCourse):
        def get_group_categories(self):
            raise Forbidden("private response")

    class FakeCanvas:
        def get_course(self, course_id: int):
            return ForbiddenCategoriesCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(
        project_root=str(tmp_path),
        course_id=1742717,
        force=False,
        require_complete=True,
        api_url="https://canvas.test/",
        timezone="America/Chicago",
    )

    with pytest.raises(SystemExit) as exc_info:
        config.command_init(args)

    assert exc_info.value.code == config.PARTIAL_SNAPSHOT_EXIT_CODE
    assert not (tmp_path / ".danvas").exists()


def test_init_records_profile_and_canvas_metadata_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ZonedCourse(FakeCourse):
        time_zone = "Central Time (US & Canada)"

    class FakeCanvas:
        def get_course(self, course_id: int):
            assert course_id == 1742717
            return ZonedCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())

    config.command_init(
        SimpleNamespace(
            project_root=str(tmp_path),
            course_id=1742717,
            force=False,
            require_complete=True,
            api_url="https://canvas.example/",
            profile="institution-a",
            profile_timezone="America/New_York",
            timezone=None,
        )
    )

    project_config = (tmp_path / ".danvas" / "config.toml").read_text(encoding="utf-8")
    assert 'profile = "institution-a"' in project_config
    assert 'api_url = "https://canvas.example/"' in project_config
    assert 'timezone = "America/Chicago"' in project_config


def test_diff_snapshots_reports_added_removed_changed() -> None:
    old = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    new = json.loads(json.dumps(old))
    new["assignments"][0]["points_possible"] = 50
    new["quizzes"] = []
    new["files"].append({"id": 301, "display_name": "extra.pdf", "size": 10})

    report = config.diff_snapshots(old, new)

    assert report is not None
    sections = report["sections"]
    assert sections["files"]["added"] == ["extra.pdf"]
    assert sections["quizzes"]["removed"] == ["Chapter 7 Quiz"]
    changed = sections["assignments"]["changed"]
    assert changed[0]["label"] == "Case Study 1"
    assert changed[0]["changes"] == ["points_possible: 100 -> 50"]
    assert "announcements" not in sections


def test_diff_snapshots_skips_non_authoritative_section_without_false_removals() -> None:
    old = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    new = json.loads(json.dumps(old))
    new["snapshot_status"] = "partial"
    new["group_categories"] = []
    new["collections"]["group_categories"] = {
        "status": "unavailable",
        "authoritative": False,
        "item_count": 0,
        "reason": "forbidden",
        "error_type": "Forbidden",
    }
    new["assignments"][0]["points_possible"] = 50

    report = config.diff_snapshots(old, new)

    assert report is not None
    assert report["comparison_status"] == "partial"
    categories = report["sections"]["group_categories"]
    assert categories["comparison_status"] == "unavailable"
    assert categories["old_status"] == "available"
    assert categories["new_status"] == "unavailable"
    assert categories["new_reason"] == "forbidden"
    assert categories["added"] == []
    assert categories["removed"] == []
    assert categories["changed"] == []
    assert report["sections"]["assignments"]["changed"]


def test_diff_snapshots_marks_restored_section_without_historical_change_claims() -> None:
    new = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    old = json.loads(json.dumps(new))
    old["snapshot_status"] = "partial"
    old["group_categories"] = []
    old["collections"]["group_categories"] = {
        "status": "failed",
        "authoritative": False,
        "item_count": 0,
        "reason": "rate_limited",
        "error_type": "RateLimitExceeded",
    }

    report = config.diff_snapshots(old, new)

    assert report is not None
    categories = report["sections"]["group_categories"]
    assert categories["comparison_status"] == "restored"
    assert categories["added"] == []
    assert categories["removed"] == []
    assert categories["changed"] == []
    rendered = "\n".join(config.render_snapshot_diff(report))
    assert "comparison restored" in rendered
    assert "no change claims" in rendered


def test_refresh_diff_report_is_partial_when_a_section_is_not_authoritative(
    tmp_path: Path,
) -> None:
    old = config.build_course_snapshot(FakeCourse())
    new = json.loads(json.dumps(old))
    new["snapshot_status"] = "partial"
    new["collections"]["group_categories"] = {
        "status": "unavailable",
        "authoritative": False,
        "item_count": 0,
        "reason": "forbidden",
        "error_type": "Forbidden",
    }

    report = config.build_refresh_diff_report(
        old, new, tmp_path / ".danvas" / "course.json"
    )

    assert report["status"] == "partial"
    assert "not compared" in report["message"]
    markdown = config.render_refresh_diff_markdown(report)
    assert "Comparison: `unavailable`" in markdown
    assert "New collection: `unavailable` (`forbidden`)" in markdown


def test_diff_snapshots_tracks_pages_by_page_id() -> None:
    old = {
        "schema_version": 4,
        "generated_at": "2026-07-01T00:00:00Z",
        "pages": [
            {
                "page_id": 1,
                "title": "Changed",
                "published": False,
                "body_sha256": "old",
                "body_normalizer": config.BODY_NORMALIZER_VERSION,
            },
            {
                "page_id": 2,
                "title": "Removed",
                "published": False,
                "body_sha256": "same",
                "body_normalizer": config.BODY_NORMALIZER_VERSION,
            },
        ],
    }
    new = {
        "schema_version": 4,
        "generated_at": "2026-07-02T00:00:00Z",
        "pages": [
            {
                "page_id": 1,
                "title": "Changed",
                "published": True,
                "body_sha256": "new",
                "body_normalizer": config.BODY_NORMALIZER_VERSION,
            },
            {
                "page_id": 3,
                "title": "Added",
                "published": False,
                "body_sha256": "same",
                "body_normalizer": config.BODY_NORMALIZER_VERSION,
            },
        ],
    }

    report = config.diff_snapshots(old, new)

    assert report is not None
    pages = report["sections"]["pages"]
    assert pages["added"] == ["Added"]
    assert pages["removed"] == ["Removed"]
    assert pages["changed"] == [
        {
            "label": "Changed",
            "changes": ["published: False -> True", "body_sha256: 'old' -> 'new'"],
        }
    ]


def test_diff_snapshots_does_not_compare_page_hashes_across_normalizers() -> None:
    old = {
        "schema_version": 4,
        "generated_at": "2026-07-01T00:00:00Z",
        "pages": [
            {
                "page_id": 1,
                "title": "Page",
                "body_sha256": "old",
                "body_normalizer": "pages-html-v3",
            }
        ],
    }
    new = {
        "schema_version": 4,
        "generated_at": "2026-07-02T00:00:00Z",
        "pages": [
            {
                "page_id": 1,
                "title": "Page",
                "body_sha256": "new",
                "body_normalizer": config.BODY_NORMALIZER_VERSION,
            }
        ],
    }

    report = config.diff_snapshots(old, new)

    assert report is not None
    changes = report["sections"]["pages"]["changed"][0]["changes"]
    assert changes == [
        "body_sha256: comparison unavailable (normalizer mismatch; refresh required)"
    ]
    assert "old" not in changes[0]
    assert "new" not in changes[0]


def test_diff_snapshots_refuses_schema_mismatch() -> None:
    old = {"schema_version": 1, "generated_at": "2026-06-01T00:00:00Z"}
    new = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")

    assert config.diff_snapshots(old, new) is None
    assert "diff unavailable" in config.render_snapshot_diff(None)[0]


def test_build_refresh_diff_report_handles_schema_mismatch(tmp_path: Path) -> None:
    old = {"schema_version": 1, "generated_at": "2026-06-01T00:00:00Z"}
    new = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")

    report = config.build_refresh_diff_report(old, new, tmp_path / ".danvas" / "course.json")

    assert report["status"] == "schema_changed"
    assert report["schema_compatible"] is False
    assert report["old_schema_version"] == 1
    assert report["new_schema_version"] == config.SNAPSHOT_SCHEMA_VERSION
    assert "diff unavailable" in report["message"]


def test_build_refresh_diff_report_handles_missing_previous_snapshot(tmp_path: Path) -> None:
    new = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")

    report = config.build_refresh_diff_report(None, new, tmp_path / ".danvas" / "course.json")

    assert report["status"] == "no_previous_snapshot"
    assert report["old_generated_at"] is None
    assert report["new_generated_at"] == new["generated_at"]
    assert report["sections"] == {}


def test_command_refresh_with_diff_prints_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".danvas").mkdir()
    old = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    old["assignments"][0]["points_possible"] = 50
    config.write_course_snapshot(tmp_path / ".danvas" / "course.json", old)

    class FakeCanvas:
        def get_course(self, course_id: int) -> FakeCourse:
            return FakeCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    args = SimpleNamespace(project_root=str(tmp_path), course_id=1742717, diff=True)

    config.command_refresh(args)

    out = capsys.readouterr().out
    assert "Snapshot diff:" in out
    assert "changed: Case Study 1 (points_possible: 50 -> 100)" in out
    assert "Wrote" in out


def test_command_refresh_with_diff_writes_report_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".danvas").mkdir()
    old = config.build_course_snapshot(FakeCourse(), canvas_origin="https://canvas.test/")
    old["assignments"][0]["points_possible"] = 50
    config.write_course_snapshot(tmp_path / ".danvas" / "course.json", old)

    class FakeCanvas:
        def get_course(self, course_id: int) -> FakeCourse:
            return FakeCourse()

    monkeypatch.setattr("danvas.config.canvas_from_args", lambda args: FakeCanvas())
    report_dir = tmp_path / "refresh-report"
    args = SimpleNamespace(
        project_root=str(tmp_path),
        course_id=1742717,
        diff=True,
        report_root=None,
        report_dir=str(report_dir),
        report_slug=None,
    )

    config.command_refresh(args)

    out = capsys.readouterr().out
    assert "Report directory:" in out
    payload = json.loads((report_dir / "refresh-diff.json").read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["schema_compatible"] is True
    assert payload["sections"]["assignments"]["changed"][0]["label"] == "Case Study 1"
    markdown = (report_dir / "refresh-diff.md").read_text(encoding="utf-8")
    assert "# Refresh Diff Report" in markdown
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "refresh --diff"
    assert manifest["course_id"] == 1742717
    assert manifest["snapshot_timestamp"] == payload["new_generated_at"]
    assert manifest["files"] == ["refresh-diff.json", "refresh-diff.md"]


def test_command_refresh_report_requires_diff(tmp_path: Path) -> None:
    args = SimpleNamespace(
        project_root=str(tmp_path),
        course_id=1742717,
        diff=False,
        report_root=None,
        report_dir=str(tmp_path / "report"),
        report_slug=None,
    )

    with pytest.raises(SystemExit, match="requires --diff"):
        config.command_refresh(args)


def test_toml_key_quotes_names_that_are_not_bare_keys() -> None:
    assert config.toml_key("CaseStudies") == "CaseStudies"
    assert config.toml_key("case-studies_1") == "case-studies_1"
    assert config.toml_key("Case Studies") == '"Case Studies"'
    assert config.toml_key("Présentations") == '"Présentations"'


def test_write_project_config_round_trips_non_ascii_group_names(tmp_path: Path) -> None:
    import tomllib

    config_path = tmp_path / ".danvas" / "config.toml"
    config.write_project_config(
        config_path,
        course_snapshot={
            "course": {"id": 1, "name": "INSY 6600"},
            "assignment_groups": [{"id": 5, "name": "Présentations"}],
        },
        api_url="https://canvas.example/",
        timezone="America/Chicago",
    )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["assignment_groups"]["Présentations"] == 5


def test_maybe_ignore_course_snapshot_appends_without_blank_lines(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("existing\n", encoding="utf-8")

    config.maybe_ignore_course_snapshot(tmp_path)
    config.maybe_ignore_course_snapshot(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == "existing\n.danvas/course.json\n"


def test_maybe_ignore_course_snapshot_adds_missing_trailing_newline(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("existing", encoding="utf-8")

    config.maybe_ignore_course_snapshot(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == "existing\n.danvas/course.json\n"


def test_maybe_ignore_reports_appends_once(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("existing\n", encoding="utf-8")

    config.maybe_ignore_reports(tmp_path)
    config.maybe_ignore_reports(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == "existing\n.danvas/reports/\n"


def test_maybe_ignore_private_artifacts_appends_once(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("existing\n", encoding="utf-8")

    config.maybe_ignore_private_artifacts(tmp_path)
    config.maybe_ignore_private_artifacts(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == "existing\n.danvas/private/\n"


def test_assignment_group_name_resolves_in_dry_run(tmp_path: Path, capsys) -> None:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        """
[canvas]
course_id = 1742717

[assignment_groups]
"Case Studies" = 20
""",
        encoding="utf-8",
    )
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Case Study 1
assignment_group_name: Case Studies
points_possible: 100
---

# Case Study 1
""",
        encoding="utf-8",
    )

    command_assignments_create(
        SimpleNamespace(source=str(source), dry_run=True, course_id=1742717)
    )

    out = capsys.readouterr().out
    assert '"assignment_group_id": 20' in out
    assert "assignment_group_name" not in out


def test_args_for_resolves_course_id_from_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "course"
    other = tmp_path / "other"
    (project / ".danvas").mkdir(parents=True)
    other.mkdir()
    (project / ".danvas" / "config.toml").write_text(
        """
[canvas]
api_url = "https://canvas.example/"
course_id = 1742717
""",
        encoding="utf-8",
    )
    source = project / "assignment.md"
    source.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
    monkeypatch.chdir(other)

    args = args_for(course_id=None, source=str(source), api_url=None)

    assert args.course_id == 1742717
    assert args.api_url == "https://canvas.example/"


def test_assignment_group_name_conflicts_with_id(tmp_path: Path) -> None:
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        """
[canvas]
course_id = 1742717

[assignment_groups]
"Case Studies" = 20
""",
        encoding="utf-8",
    )
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: Case Study 1
assignment_group_id: 20
assignment_group_name: Case Studies
---

# Case Study 1
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Use either assignment_group_id"):
        command_assignments_create(
            SimpleNamespace(source=str(source), dry_run=True, course_id=1742717)
        )
