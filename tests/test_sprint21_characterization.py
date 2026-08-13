from __future__ import annotations

import re
import tomllib
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
import typer

import danvas.config as config_module
from danvas.cli import app
from danvas.files import (
    DEFAULT_INVENTORY_IGNORE_PATTERNS,
    EXCLUDED_LOCAL_PARTS,
    files_inventory_ignore_patterns,
)
from danvas.gradebook import GRADE_VARIANTS, GROUP_VARIANTS, METADATA_COLUMNS, TOTAL_VARIANTS
from danvas.sources import DEFAULT_SOURCE_EXCLUDES, DEFAULT_SOURCE_PATTERNS, source_options
from danvas.status import next_action_for

ROOT = Path(__file__).resolve().parents[1]


def leaf_commands() -> dict[str, click.Command]:
    found: dict[str, click.Command] = {}

    def visit(command: click.Command, prefix: tuple[str, ...] = ()) -> None:
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                visit(child, (*prefix, name))
            return
        found[" ".join(prefix)] = command

    visit(typer.main.get_command(app))
    return found


def option(command: click.Command, name: str) -> click.Option:
    for parameter in command.params:
        if isinstance(parameter, click.Option) and name in (
            *parameter.opts,
            *parameter.secondary_opts,
        ):
            return parameter
    raise AssertionError(f"Missing {name} on {command.name}")


def test_legacy_source_defaults_and_compatibility_spellings_are_frozen() -> None:
    assert DEFAULT_SOURCE_PATTERNS == {
        "announcement": ["content/announcements/*.md"],
        "discussion": ["content/discussions/*.md"],
        "quiz": ["content/quizzes/chap*.md"],
        "assignment": ["content/cases/*-assignment.md"],
        "page": ["content/pages/*.md", "content/pages/*.html"],
    }
    assert DEFAULT_SOURCE_EXCLUDES == {"page": ["content/pages/*-preview.html"]}
    assert source_options("assignment", {}) == {
        "include": ["content/cases/*-assignment.md"],
        "exclude": [],
        "require_assignment_metadata": False,
    }
    assert source_options(
        "assignment",
        {
            "assignment": {
                "includes": ["coursework/*.md"],
                "excludes": ["coursework/draft-*.md"],
            }
        },
    ) == {
        "include": ["coursework/*.md"],
        "exclude": ["coursework/draft-*.md"],
        "require_assignment_metadata": True,
    }


def test_project_config_writer_does_not_materialize_a_source_layout(tmp_path: Path) -> None:
    path = tmp_path / ".danvas/config.toml"

    config_module.write_project_config(
        path,
        course_snapshot={
            "course": {"id": 101, "name": "Example Course"},
            "assignment_groups": [],
        },
        api_url="https://canvas.example.edu/",
        timezone="America/Chicago",
    )

    text = path.read_text(encoding="utf-8")
    assert "[sources]" not in text
    assert "source_layout" not in text


def test_status_next_actions_use_fixed_legacy_content_paths() -> None:
    assert next_action_for("announcements", {"classification": "Canvas-only"}) == (
        "Run `danvas announcements sync --output-dir content/announcements --dry-run` "
        "to plan a local source file."
    )
    assert next_action_for("discussions", {"classification": "Canvas-only"}) == (
        "Run `danvas discussions sync-prompts --output-dir content/discussions --dry-run` "
        "to plan a local prompt source file."
    )
    assert next_action_for("pages", {"classification": "Canvas-only"}) == (
        "Run `danvas pages sync --output-dir content/pages --dry-run` to plan a local source."
    )


def test_inventory_defaults_are_extended_and_enforced_in_two_places(tmp_path: Path) -> None:
    assert {
        ".git",
        ".obsidian",
        ".danvas",
        "_archive",
        "_inventory",
        "grading",
        "node_modules",
        "__pycache__",
    } == EXCLUDED_LOCAL_PARTS
    assert DEFAULT_INVENTORY_IGNORE_PATTERNS == [
        ".danvas/**",
        "_archive/**",
        "_inventory/**",
        "node_modules/**",
        "__pycache__/**",
        ".DS_Store",
        "**/.DS_Store",
        "files-inventory.csv",
        "files-inventory.json",
        "files-missing-report.md",
    ]

    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[canvas]\ncourse_id = 101\n\n"
        "[files.inventory]\nuse_default_ignores = false\nignore = ['scratch/**']\n",
        encoding="utf-8",
    )

    # The 0.17.0 parser ignores use_default_ignores and always extends defaults.
    assert files_inventory_ignore_patterns(tmp_path) == [
        *DEFAULT_INVENTORY_IGNORE_PATTERNS,
        "scratch/**",
    ]


def test_english_gradebook_heading_profile_is_frozen() -> None:
    assert TOTAL_VARIANTS == [
        "Unposted Final Score",
        "Final Score",
        "Unposted Current Score",
        "Current Score",
    ]
    assert GRADE_VARIANTS == [
        "Unposted Final Grade",
        "Final Grade",
        "Unposted Current Grade",
        "Current Grade",
    ]
    assert GROUP_VARIANTS == TOTAL_VARIANTS
    assert {
        "Student",
        "ID",
        "SIS User ID",
        "SIS Login ID",
        "Section",
        "Email",
        "Root Account",
    } == METADATA_COLUMNS


def test_deprecated_options_and_panopto_language_default_are_frozen() -> None:
    commands = leaf_commands()
    options_by_name = {
        option_name: {
            command_name
            for command_name, command in commands.items()
            if any(
                isinstance(parameter, click.Option)
                and option_name in (*parameter.opts, *parameter.secondary_opts)
                for parameter in command.params
            )
        }
        for option_name in ("--live", "--upload", "--schema")
    }

    assert options_by_name == {
        "--live": {"assignments overrides-sync"},
        "--upload": {"discussions score"},
        "--schema": {"roster"},
    }
    roster_schema = option(commands["roster"], "--schema")
    assert roster_schema.default == "v2"
    assert isinstance(roster_schema.type, click.Choice)
    assert tuple(roster_schema.type.choices) == ("v2", "legacy-v1")
    assert option(commands["recordings panopto-captions"], "--caption-language").default == (
        "English_USA"
    )


def test_invalid_init_timezone_currently_reaches_canvas_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class FakeCanvas:
        def get_course(self, course_id: int) -> SimpleNamespace:
            calls.append(f"course:{course_id}")
            return SimpleNamespace()

    def fake_canvas_from_args(args: object) -> FakeCanvas:
        calls.append("canvas")
        return FakeCanvas()

    monkeypatch.setattr(config_module, "canvas_from_args", fake_canvas_from_args)

    with pytest.raises(SystemExit, match="Unknown timezone in --timezone"):
        config_module.command_init(
            SimpleNamespace(
                project_root=str(tmp_path),
                course_id=101,
                force=False,
                timezone="Not/A-Timezone",
            )
        )

    assert calls == ["canvas", "course:101"]
    assert not (tmp_path / ".danvas").exists()


def test_package_metadata_gaps_are_frozen() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "danvas"
    assert project["version"] == "0.17.0"
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"] == {"danvas": "danvas.cli:main"}
    assert pyproject["tool"]["uv"]["build-backend"]["module-name"] == "danvas"
    assert {
        "license",
        "authors",
        "maintainers",
        "classifiers",
        "keywords",
        "urls",
    }.isdisjoint(project)
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License\n")


def test_public_documentation_gaps_and_ssh_install_are_frozen() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ssh_install = "danvas @ git+ssh://git@github.com/olearydj/danvas.git@v0.17.0"
    missing = {
        path.relative_to(ROOT).as_posix()
        for path in (
            ROOT / "docs/configuration.md",
            ROOT / "docs/authentication.md",
            ROOT / "docs/privacy.md",
            ROOT / "docs/compatibility.md",
            ROOT / "docs/authored-sources.md",
            ROOT / "docs/mutation-safety.md",
            ROOT / "CHANGELOG.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "SECURITY.md",
        )
        if not path.exists()
    }

    assert readme.count(ssh_install) == 2
    assert "git+https://github.com/olearydj/danvas.git@v0.17.0" not in readme
    assert missing == {
        "docs/configuration.md",
        "docs/authentication.md",
        "docs/privacy.md",
        "docs/compatibility.md",
        "docs/authored-sources.md",
        "docs/mutation-safety.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    }


def test_ci_and_secret_scan_gaps_are_frozen() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses = Counter(re.findall(r"^\s*- uses:\s+(\S+)$", workflow, flags=re.MULTILINE))

    assert 'python-version: ["3.12", "3.14"]' in workflow
    assert workflow.count("runs-on: ubuntu-latest") == 2
    assert "macos-latest" not in workflow
    assert "permissions:" not in workflow
    assert uses == Counter(
        {
            "actions/checkout@v7.0.1": 2,
            "astral-sh/setup-uv@v9.0.0": 2,
        }
    )
    assert "gitleaks" not in workflow.lower()
    assert not any("gitleaks" in path.name.lower() for path in (ROOT / "scripts").iterdir())


def test_current_tree_identity_breadcrumbs_are_frozen() -> None:
    canvas_host = "auburn." + "instructure.com"
    panopto_host = "auburn." + "hosted.panopto.com"
    searchable = [
        *sorted((ROOT / "src/danvas").glob("*.py")),
        *sorted((ROOT / "tests").glob("*.py")),
        ROOT / "README.md",
        ROOT / "docs/course-yaml.md",
    ]
    searchable = [path for path in searchable if path != Path(__file__)]

    canvas_occurrences = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8").count(canvas_host)
        for path in searchable
        if canvas_host in path.read_text(encoding="utf-8")
    }
    panopto_occurrences = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8").count(panopto_host)
        for path in searchable
        if panopto_host in path.read_text(encoding="utf-8")
    }
    numeric_occurrences = {
        path.relative_to(ROOT).as_posix(): sorted(
            set(re.findall(r"(?<![A-Za-z0-9])\d{6,}(?![A-Za-z0-9])", path.read_text()))
        )
        for path in searchable
    }
    numeric_occurrences = {path: values for path, values in numeric_occurrences.items() if values}

    assert canvas_occurrences == {"tests/test_config.py": 1}
    assert panopto_occurrences == {"tests/test_panopto.py": 5}
    assert numeric_occurrences == {
        "docs/course-yaml.md": ["14702073", "14702074", "14875304", "14875406"],
        "tests/test_config.py": ["1742717"],
        "tests/test_override_sync.py": ["501234"],
        "tests/test_overrides.py": ["123456"],
        "tests/test_pages.py": ["123456"],
        "tests/test_panopto.py": ["448843", "99999999999999999"],
        "tests/test_submissions.py": [
            "0000001",
            "4024825",
            "4025725",
            "5113936",
            "9999999",
        ],
    }
