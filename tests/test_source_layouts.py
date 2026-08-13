from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import danvas.config as config_module
from danvas.cli import app
from danvas.source_layouts import (
    materialize_source_config,
    resolve_source_config,
    resolve_source_output_dir,
    source_output_dir_value,
)

runner = CliRunner()


def init_args(root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "project_root": str(root),
        "course_id": 101,
        "force": False,
        "require_complete": False,
        "api_url": "https://canvas.example.edu/",
        "profile": None,
        "profile_timezone": None,
        "timezone": "America/Chicago",
        "source_layout": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def stub_init_canvas(monkeypatch: pytest.MonkeyPatch) -> None:
    course = SimpleNamespace(id=101, name="Example Course")
    canvas = SimpleNamespace(get_course=lambda course_id: course)
    monkeypatch.setattr(config_module, "canvas_from_args", lambda args: canvas)
    monkeypatch.setattr(
        config_module,
        "build_course_snapshot",
        lambda course, **kwargs: {
            "schema_version": config_module.SNAPSHOT_SCHEMA_VERSION,
            "generated_at": "2026-08-13T00:00:00Z",
            "snapshot_status": "complete",
            "course": {"id": 101, "name": "Example Course"},
            "assignment_groups": [],
            "collections": {},
        },
    )


def test_new_init_materializes_standard_layout_without_creating_sources(
    tmp_path: Path, stub_init_canvas: None
) -> None:
    config_module.command_init(init_args(tmp_path))

    project = tomllib.loads(
        (tmp_path / ".danvas/config.toml").read_text(encoding="utf-8")
    )
    assert project["sources"] == materialize_source_config({"layout": "standard-v1"})
    assert not (tmp_path / "content").exists()


def test_new_init_can_materialize_legacy_layout(
    tmp_path: Path, stub_init_canvas: None
) -> None:
    config_module.command_init(init_args(tmp_path, source_layout="legacy-v1"))

    project = tomllib.loads(
        (tmp_path / ".danvas/config.toml").read_text(encoding="utf-8")
    )
    assert project["sources"] == materialize_source_config({"layout": "legacy-v1"})


def test_force_without_layout_preserves_effective_sources_and_unrelated_tables(
    tmp_path: Path, stub_init_canvas: None
) -> None:
    config_path = tmp_path / ".danvas/config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "[canvas]\n"
        "api_url = 'https://canvas.example.edu/'\n"
        "course_id = 101\n"
        "timezone = 'America/New_York'\n\n"
        "[sources.assignment]\n"
        "includes = ['coursework/*.md']\n"
        "excludes = ['coursework/draft-*.md']\n\n"
        "[files.inventory]\n"
        "use_default_ignores = false\n"
        "ignore = ['scratch/**']\n",
        encoding="utf-8",
    )

    config_module.command_init(
        init_args(tmp_path, force=True, timezone=None, source_layout=None)
    )

    project = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert project["sources"] == materialize_source_config(
        {
            "assignment": {
                "includes": ["coursework/*.md"],
                "excludes": ["coursework/draft-*.md"],
            }
        }
    )
    assert project["files"]["inventory"] == {
        "use_default_ignores": False,
        "ignore": ["scratch/**"],
    }
    assert project["canvas"]["timezone"] == "America/New_York"


def test_force_with_layout_replaces_only_source_configuration(
    tmp_path: Path, stub_init_canvas: None
) -> None:
    config_path = tmp_path / ".danvas/config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "[canvas]\n"
        "api_url = 'https://canvas.example.edu/'\n"
        "course_id = 101\n\n"
        "[sources.assignments]\n"
        "include = ['coursework/*.md']\n\n"
        "[custom]\n"
        "enabled = true\n",
        encoding="utf-8",
    )

    config_module.command_init(
        init_args(tmp_path, force=True, source_layout="standard-v1")
    )

    project = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert project["sources"] == materialize_source_config({"layout": "standard-v1"})
    assert project["custom"] == {"enabled": True}


def test_mixed_existing_sources_inherit_unspecified_legacy_kinds() -> None:
    effective = resolve_source_config(
        {"assignments": {"include": ["coursework/*.md"]}}
    )

    assert effective["layout"] == "legacy-v1"
    assert effective["assignments"]["include"] == ["coursework/*.md"]
    assert effective["assignments"]["require_assignment_metadata"] is True
    assert effective["quizzes"]["include"] == ["content/quizzes/chap*.md"]


@pytest.mark.parametrize(
    ("source_config", "message"),
    [
        ({"assignments": {"incldue": ["*.md"]}}, "sources.assignments.incldue"),
        ({"layout": "future"}, "sources.layout must be one of"),
        ({"pages": {"output_dir": "/tmp/pages"}}, "relative path"),
        ({"pages": {"output_dir": "content/*/pages"}}, "glob syntax"),
        ({"quizzes": {"include": ["../quizzes/*.md"]}}, "relative path"),
    ],
)
def test_source_configuration_rejects_unknown_or_unsafe_values(
    source_config: dict[str, object], message: str
) -> None:
    with pytest.raises(SystemExit, match=message):
        resolve_source_config(source_config)


def test_invalid_existing_sources_fail_before_canvas_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / ".danvas/config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "[canvas]\ncourse_id = 101\n\n[sources.pages]\noutpt_dir = 'pages'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        config_module,
        "canvas_from_args",
        lambda args: pytest.fail("Canvas context must not be resolved"),
    )

    with pytest.raises(SystemExit, match="sources.pages.outpt_dir"):
        config_module.command_init(init_args(tmp_path, force=True))


def test_cli_invalid_init_timezone_fails_before_canvas_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "danvas.cli.resolve_canvas_context",
        lambda **kwargs: pytest.fail("Canvas context must not be resolved"),
    )

    result = runner.invoke(
        app,
        [
            "init",
            "101",
            "--project-root",
            str(tmp_path),
            "--timezone",
            "Not/A-Timezone",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown timezone in --timezone" in result.output
    assert not (tmp_path / ".danvas").exists()


def test_source_output_directory_uses_config_then_unambiguous_include_parent(
    tmp_path: Path,
) -> None:
    assert source_output_dir_value(
        "announcement",
        {
            "announcements": {
                "include": ["authored/news/*.md"],
                "output_dir": "generated/announcements",
            }
        },
    ) == "generated/announcements"
    assert source_output_dir_value(
        "discussion", {"discussions": {"include": ["authored/prompts/*.md"]}}
    ) == "authored/prompts"
    assert resolve_source_output_dir(
        "page",
        project_root=tmp_path,
        source_config={"pages": {"include": ["pages/*.md", "pages/*.html"]}},
    ) == (tmp_path / "pages").resolve()


def test_source_output_directory_rejects_ambiguous_include_parents(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="sources.pages.output_dir is required"):
        resolve_source_output_dir(
            "page",
            project_root=tmp_path,
            source_config={"pages": {"include": ["pages/*.md", "html/*.html"]}},
        )


@pytest.mark.parametrize(
    "command",
    [
        ["announcements", "sync"],
        ["discussions", "sync-prompts"],
        ["pages", "sync"],
    ],
)
def test_sync_output_resolution_fails_before_canvas_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
) -> None:
    config_path = tmp_path / ".danvas/config.toml"
    config_path.parent.mkdir()
    kind = {
        "announcements": "announcements",
        "discussions": "discussions",
        "pages": "pages",
    }[command[0]]
    config_path.write_text(
        "[canvas]\ncourse_id = 101\napi_url = 'https://canvas.example.edu/'\n\n"
        f"[sources.{kind}]\n"
        "include = ['one/*.md', 'two/*.md']\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "danvas.cli.resolve_canvas_context",
        lambda **kwargs: pytest.fail("Canvas context must not be resolved"),
    )

    result = runner.invoke(
        app,
        [*command, "--course-id", "101", "--project-root", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert f"sources.{kind}.output_dir is required" in result.output
