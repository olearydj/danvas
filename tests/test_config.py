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
