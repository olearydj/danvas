import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_write_project_config_and_snapshot(tmp_path: Path) -> None:
    snapshot = config.build_course_snapshot(FakeCourse())
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
    assert payload["folders"][1]["full_name"] == "course files/Case Studies"


def test_build_course_snapshot_includes_expanded_sections() -> None:
    snapshot = config.build_course_snapshot(FakeCourse())

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


def test_build_course_snapshot_contains_no_secrets_or_member_lists() -> None:
    snapshot = config.build_course_snapshot(FakeCourse())
    text = json.dumps(snapshot)

    assert "verifier" not in text
    assert "secret-token" not in text
    for category in snapshot["group_categories"]:
        for group in category["groups"]:
            assert set(group) == {"id", "name", "members_count"}


def test_diff_snapshots_reports_added_removed_changed() -> None:
    old = config.build_course_snapshot(FakeCourse())
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


def test_diff_snapshots_refuses_schema_mismatch() -> None:
    old = {"schema_version": 1, "generated_at": "2026-06-01T00:00:00Z"}
    new = config.build_course_snapshot(FakeCourse())

    assert config.diff_snapshots(old, new) is None
    assert "diff unavailable" in config.render_snapshot_diff(None)[0]


def test_build_refresh_diff_report_handles_schema_mismatch(tmp_path: Path) -> None:
    old = {"schema_version": 1, "generated_at": "2026-06-01T00:00:00Z"}
    new = config.build_course_snapshot(FakeCourse())

    report = config.build_refresh_diff_report(old, new, tmp_path / ".danvas" / "course.json")

    assert report["status"] == "schema_changed"
    assert report["schema_compatible"] is False
    assert report["old_schema_version"] == 1
    assert report["new_schema_version"] == config.SNAPSHOT_SCHEMA_VERSION
    assert "diff unavailable" in report["message"]


def test_build_refresh_diff_report_handles_missing_previous_snapshot(tmp_path: Path) -> None:
    new = config.build_course_snapshot(FakeCourse())

    report = config.build_refresh_diff_report(None, new, tmp_path / ".danvas" / "course.json")

    assert report["status"] == "no_previous_snapshot"
    assert report["old_generated_at"] is None
    assert report["new_generated_at"] == new["generated_at"]
    assert report["sections"] == {}


def test_command_refresh_with_diff_prints_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".danvas").mkdir()
    old = config.build_course_snapshot(FakeCourse())
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
    old = config.build_course_snapshot(FakeCourse())
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
