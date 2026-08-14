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
    local_files,
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


def test_project_config_writer_materializes_selected_source_layout(tmp_path: Path) -> None:
    path = tmp_path / ".danvas/config.toml"

    config_module.write_project_config(
        path,
        course_snapshot={
            "course": {"id": 101, "name": "Example Course"},
            "assignment_groups": [],
        },
        api_url="https://canvas.example.edu/",
        timezone="America/Chicago",
        source_config=config_module.source_config_for_init(
            existing_config={}, requested_layout=None, config_exists=False
        ),
    )

    project = tomllib.loads(path.read_text(encoding="utf-8"))
    assert project["sources"]["layout"] == "standard-v1"
    assert project["sources"]["assignments"] == {
        "include": ["content/assignments/*.md"],
        "require_assignment_metadata": True,
    }


def test_status_next_actions_use_effective_source_output_paths() -> None:
    source_config = {
        "announcements": {"output_dir": "authored/news"},
        "discussions": {"include": ["authored/prompts/*.md"]},
        "pages": {"include": ["pages/*.md", "site/*.html"]},
    }
    assert next_action_for(
        "announcements", {"classification": "Canvas-only"}, source_config=source_config
    ) == (
        "Run `danvas announcements sync --output-dir authored/news --dry-run` "
        "to plan a local source file."
    )
    assert next_action_for(
        "discussions", {"classification": "Canvas-only"}, source_config=source_config
    ) == (
        "Run `danvas discussions sync-prompts --output-dir authored/prompts --dry-run` "
        "to plan a local prompt source file."
    )
    assert next_action_for(
        "pages", {"classification": "Canvas-only"}, source_config=source_config
    ) == (
        "Set `sources.pages.output_dir` in `.danvas/config.toml`; the include patterns "
        "do not have one unambiguous static parent."
    )


def test_inventory_mandatory_and_replaceable_exclusions_are_split(tmp_path: Path) -> None:
    assert {".git", ".danvas"} == EXCLUDED_LOCAL_PARTS
    assert DEFAULT_INVENTORY_IGNORE_PATTERNS == [
        ".obsidian/**",
        "**/.obsidian/**",
        "_archive/**",
        "**/_archive/**",
        "_inventory/**",
        "**/_inventory/**",
        "grading/**",
        "**/grading/**",
        "node_modules/**",
        "**/node_modules/**",
        "__pycache__/**",
        "**/__pycache__/**",
        ".*",
        "**/.*",
        "**/.*/**",
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

    assert files_inventory_ignore_patterns(tmp_path) == [
        ".git/**",
        ".danvas/**",
        "scratch/**",
    ]
    for relative in (
        ".git/metadata",
        ".danvas/private/artifact",
        "grading/grades.csv",
        "_archive/old.pdf",
        ".notes/outline.md",
        "scratch/ignored.txt",
        "content/included.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")

    assert {row["relative_path"] for row in local_files(
        tmp_path, ignore_patterns=files_inventory_ignore_patterns(tmp_path)
    )} == {
        ".notes/outline.md",
        "_archive/old.pdf",
        "content/included.md",
        "grading/grades.csv",
    }


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


def test_due_deprecations_and_roster_compatibility_are_removed() -> None:
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
        "--live": set(),
        "--upload": set(),
        "--schema": set(),
    }
    assert option(commands["recordings panopto-captions"], "--caption-language").default is None


def test_invalid_init_timezone_fails_before_canvas_context(
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

    assert calls == []
    assert not (tmp_path / ".danvas").exists()


def test_public_beta_package_metadata_preserves_released_identity() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "danvas-cli"
    assert project["version"] == "0.20.0"
    assert project["requires-python"] == ">=3.12,<3.15"
    assert project["scripts"] == {"danvas": "danvas.cli:main"}
    assert pyproject["tool"]["uv"]["build-backend"]["module-name"] == "danvas"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["authors"] == [{"name": "Dan O'Leary"}]
    assert project["maintainers"] == [{"name": "Dan O'Leary"}]
    assert set(project["urls"]) == {"Repository", "Issues", "Documentation", "Changelog"}
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert "Programming Language :: Python :: 3.14" in project["classifiers"]
    assert "Operating System :: MacOS" in project["classifiers"]
    assert "Operating System :: POSIX :: Linux" in project["classifiers"]
    assert not any(value.startswith("License ::") for value in project["classifiers"])
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License\n")


def test_public_documentation_suite_and_anonymous_install_are_declared() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    expected = {
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
    observed = {path for path in expected if (ROOT / path).is_file()}

    assert observed == expected
    assert (
        'danvas-cli @ git+https://github.com/olearydj/danvas.git@v0.20.0'
        in readme
    )
    assert "git+ssh" not in readme
    assert "signed release `v0.20.0` is the latest public beta" in readme
    assert "must not be represented as released" not in readme
    assert "not affiliated with or endorsed by Instructure" in readme
    public_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in expected)
    assert "/Users/" not in public_text
    assert "/Volumes/" not in public_text
    assert "/casa/" not in public_text
    assert "git+ssh" not in public_text


def test_ci_and_secret_scan_contract_is_enforced() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses = Counter(re.findall(r"^\s*- uses:\s+(\S+)", workflow, flags=re.MULTILINE))

    assert 'python-version: ["3.12", "3.13", "3.14"]' in workflow
    assert workflow.count("runs-on: ubuntu-latest") == 3
    assert workflow.count("runs-on: macos-latest") == 1
    assert "permissions:\n  contents: read" in workflow
    assert "pull_request_target" not in workflow
    assert "${{ secrets." not in workflow
    assert uses == Counter(
        {
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1": 4,
            "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9": 3,
        }
    )
    assert "# v7.0.1" in workflow
    assert "# v9.0.0" in workflow
    assert "fetch-depth: 0" in workflow
    assert "scripts/check-secrets.sh" in workflow
    assert "tests/test_artifacts.py" in workflow
    assert "scripts/release-smoke.sh" in workflow

    script = (ROOT / "scripts/check-secrets.sh").read_text(encoding="utf-8")
    assert 'GITLEAKS_VERSION="8.30.1"' in script
    assert "--redact=100" in script
    assert "--log-opts=--all" in script


def test_public_fixtures_use_placeholder_hosts_and_ids() -> None:
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

    assert canvas_occurrences == {}
    assert panopto_occurrences == {}
    assert numeric_occurrences == {
        "tests/test_pages.py": ["123456"],
        "tests/test_panopto.py": ["99999999999999999"],
    }
