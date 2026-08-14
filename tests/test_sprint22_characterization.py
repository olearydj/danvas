from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import pytest
import typer
from typer.testing import CliRunner

import danvas.cli as cli_module
from danvas.access import ACCESS_POLICIES
from danvas.cli import app
from tests.sprint22_surface import command_records, command_tree_record

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sprint22"
runner = CliRunner()

REPRESENTATIVE_HELP = {
    "root": (),
    "assignments": ("assignments",),
    "assignments-update": ("assignments", "update"),
}
WIDTHS = (80, 120)
REMOVED_SPELLINGS = (
    "--live",
    "--upload",
    "--secret-name",
    "--secret-provider",
    "--op-reference",
)


def root_command() -> click.Command:
    return typer.main.get_command(app)


def without_long_help(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in record.items() if key != "help"}
    children = normalized.get("children")
    if isinstance(children, list):
        normalized["children"] = [
            without_long_help(child) for child in children if isinstance(child, dict)
        ]
    return normalized


def render_help(path: tuple[str, ...], *, width: int, color: bool) -> str:
    env = {
        "COLUMNS": str(width),
        "FORCE_COLOR": "1" if color else None,
        "NO_COLOR": None,
    }
    result = runner.invoke(
        app,
        [*path, "--help"],
        color=color,
        terminal_width=width,
        env=env,
    )
    assert result.exit_code == 0, (path, result.output)
    return result.output


def normalize_help(output: str) -> str:
    normalized = "\n".join(line.rstrip() for line in output.splitlines())
    return normalized + ("\n" if output.endswith("\n") else "")


def test_released_executable_tree_still_matches_complete_fixture() -> None:
    expected = json.loads((FIXTURES / "command-tree-v0.19.json").read_text(encoding="utf-8"))
    actual = command_tree_record(root_command())

    actual_by_path = {
        record["path"]: without_long_help(record) for record in command_records(actual)
    }
    for released in command_records(expected):
        current = actual_by_path[released["path"]]
        released_without_help = without_long_help(released)
        current.pop("children", None)
        released_without_help.pop("children", None)
        assert current == released_without_help
    assert actual["help"] != expected["help"]
    records = command_records(actual)
    assert sum(record["kind"] == "group" for record in records) == 15
    assert sum(record["kind"] == "leaf" for record in records) == 60
    assert sum(len(record["parameters"]) for record in records) == 623


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("fixture_name,path", REPRESENTATIVE_HELP.items())
def test_representative_help_matches_width_and_color_baseline(
    fixture_name: str,
    path: tuple[str, ...],
    width: int,
) -> None:
    released = (FIXTURES / f"{fixture_name}-{width}.txt").read_text(encoding="utf-8")
    expected = (FIXTURES / f"guided-{fixture_name}-{width}.txt").read_text(encoding="utf-8")
    plain = render_help(path, width=width, color=False)
    colored = render_help(path, width=width, color=True)

    assert normalize_help(plain).rstrip("\n") == expected.rstrip("\n")
    assert normalize_help(click.unstyle(colored)).rstrip("\n") == expected.rstrip("\n")
    assert "\x1b[" not in plain
    assert "\x1b[" in colored
    assert max(map(len, expected.splitlines())) <= width
    assert expected != released


def test_every_help_screen_is_offline_and_side_effect_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("help crossed a project, credential, dispatch, or network boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(cli_module, "run_command", forbidden)
    monkeypatch.setattr(cli_module, "resolve_canvas_context", forbidden)
    monkeypatch.setattr("danvas.project_config.find_config_dir", forbidden)
    monkeypatch.setattr("danvas.auth.resolve_canvas_credential", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)

    tree = command_tree_record(root_command())
    for record in command_records(tree):
        path = tuple(record["path"].split()) if record["path"] else ()
        output = render_help(path, width=80, color=False)
        assert "Usage:" in output, record["path"]


def test_released_help_has_neutral_auth_surface_and_no_removed_spellings() -> None:
    leaves = {
        record["path"]: record
        for record in command_records(command_tree_record(root_command()))
        if record["kind"] == "leaf"
    }
    canvas_commands = {name for name, policy in ACCESS_POLICIES.items() if policy.canvas_read}
    neutral = {"--api-url", "--profile", "--api-key-env", "--api-key-file"}

    assert len(leaves) == 60
    assert len(canvas_commands) == 45
    for name, record in leaves.items():
        options = {option for parameter in record["parameters"] for option in parameter["options"]}
        assert options.intersection(neutral) == (neutral if name in canvas_commands else set())

    all_help = "\n".join(
        render_help(tuple(name.split()), width=120, color=False) for name in leaves
    )
    for spelling in REMOVED_SPELLINGS:
        assert spelling not in all_help
    lowered = all_help.lower()
    assert "auburn." + "instructure.com" not in lowered
    assert "/casa/" not in lowered
    assert "/volumes/casa/" not in lowered

    roster_help = render_help(("roster",), width=120, color=False)
    assert "--schema" not in roster_help
    assert "LoginID" in roster_help


def test_progressive_help_states_global_and_command_specific_safety() -> None:
    root = render_help((), width=120, color=False)
    family = render_help(("assignments",), width=120, color=False)
    mutation = render_help(("assignments", "update"), width=120, color=False)
    local_sync = render_help(("pages", "sync"), width=120, color=False)
    private = render_help(("submissions", "feedback"), width=120, color=False)

    assert all(
        fragment in root
        for fragment in ("Start here:", "Effects:", "Privacy:", "--apply authorizes Canvas writes")
    )
    assert all(
        heading in family
        for heading in ("Common workflows:", "Identity:", "Privacy and safety:", "Related:")
    )
    assert all(
        heading in mutation
        for heading in (
            "Effect:",
            "Privacy:",
            "Resolution:",
            "Typical sequence:",
            "Verification:",
            "Failure boundary:",
        )
    )
    assert "--apply" in mutation
    assert "never mutates Canvas" in local_sync
    assert "--apply" not in local_sync
    assert ".danvas/private/" in private
