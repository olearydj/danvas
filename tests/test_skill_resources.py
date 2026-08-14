from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath

import click
import typer
import yaml
from typer.testing import CliRunner

from danvas.cli import app
from danvas.skill_resources import SKILL_NAME, canonical_skill_files, render_skill_show

runner = CliRunner()
EXPECTED_FILES = {
    PurePosixPath("SKILL.md"),
    PurePosixPath("references/discovery.md"),
    PurePosixPath("references/privacy-and-auth.md"),
    PurePosixPath("references/safety-and-recovery.md"),
    PurePosixPath("references/workflows.md"),
}


def frontmatter(text: str) -> dict[str, object]:
    _, block, _body = text.split("---", 2)
    payload = yaml.safe_load(block)
    assert isinstance(payload, dict)
    return payload


def public_commands() -> dict[tuple[str, ...], click.Command]:
    found: dict[tuple[str, ...], click.Command] = {}

    def visit(command: click.Command, path: tuple[str, ...] = ()) -> None:
        found[path] = command
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                visit(child, (*path, name))

    visit(typer.main.get_command(app))
    return found


def validate_example(command_text: str, commands: dict[tuple[str, ...], click.Command]) -> None:
    tokens = tuple(shlex.split(command_text))
    assert tokens and tokens[0] == "danvas"
    trailing = tokens[1:]
    candidates = [path for path in commands if path]
    candidates.sort(key=lambda path: len(path), reverse=True)
    candidate = next((path for path in candidates if trailing[: len(path)] == path), None)
    matched: tuple[str, ...]
    if candidate is None:
        assert not trailing or trailing[0].startswith("--"), command_text
        matched = ()
    else:
        matched = candidate
    command = commands[matched]
    options = {
        option
        for parameter in command.params
        if isinstance(parameter, click.Option)
        for option in (*parameter.opts, *parameter.secondary_opts)
    } | {"--help"}
    for token in trailing[len(matched) :]:
        if token.startswith("--"):
            assert token in options, (command_text, token, options)


def test_canonical_skill_is_small_spec_valid_and_provider_neutral() -> None:
    resources = canonical_skill_files()
    assert {resource.relative_path for resource in resources} == EXPECTED_FILES
    main = next(resource for resource in resources if resource.relative_path.name == "SKILL.md")
    text = main.content.decode("utf-8")
    metadata = frontmatter(text)

    assert SKILL_NAME == "danvas"
    assert metadata["name"] == SKILL_NAME
    assert set(metadata) == {"name", "description", "license", "compatibility", "metadata"}
    assert metadata["license"] == "MIT"
    assert "danvas-cli 0.20.x" in str(metadata["compatibility"])
    assert metadata["metadata"] == {
        "danvas-cli-distribution": "danvas-cli",
        "danvas-cli-version": "0.20.0",
        "skill-version": "1",
    }
    assert len(text.splitlines()) < 500
    assert len(text.split()) < 5_000

    combined = "\n".join(resource.content.decode("utf-8") for resource in resources)
    lowered = combined.lower()
    for forbidden in (
        "allowed-tools",
        "--live",
        "--upload",
        "--secret-name",
        "--secret-provider",
        "--op-reference",
        "legacy-v1",
        "auburn." + "instructure.com",
        "/casa/",
        "/volumes/casa/",
        "danvas-op",
        "op run",
    ):
        assert forbidden not in lowered


def test_skill_references_are_one_level_deep_and_reachable() -> None:
    resources = {resource.relative_path: resource for resource in canonical_skill_files()}
    main = resources[PurePosixPath("SKILL.md")].content.decode("utf-8")
    references = re.findall(r"\]\((references/[^)]+)\)", main)

    assert {PurePosixPath(reference) for reference in references} == EXPECTED_FILES - {
        PurePosixPath("SKILL.md")
    }
    for path, resource in resources.items():
        if path.parts[0] == "references":
            assert "](references/" not in resource.content.decode("utf-8")


def test_every_skill_command_example_matches_the_live_cli() -> None:
    commands = public_commands()
    combined = "\n".join(resource.content.decode("utf-8") for resource in canonical_skill_files())
    examples = re.findall(r"`(danvas(?:\s+[^`]+)?)`", combined)

    assert len(examples) >= 15
    for example in examples:
        validate_example(example, commands)


def test_skill_show_is_deterministic_and_does_not_expose_package_paths() -> None:
    expected = render_skill_show()
    result = runner.invoke(app, ["skill", "show"])

    assert result.exit_code == 0
    assert result.output == expected
    assert expected == render_skill_show()
    assert "Bundled Agent Skill: danvas" in expected
    assert "src/danvas/_skill" not in expected
    assert all(resource.sha256 in expected for resource in canonical_skill_files())
