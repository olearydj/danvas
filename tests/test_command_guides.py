from __future__ import annotations

from dataclasses import fields

import click
import pytest
import typer

from danvas.access import ACCESS_POLICIES
from danvas.artifacts import ARTIFACT_POLICIES, ArtifactClass
from danvas.cli import app
from danvas.command_guides import (
    COMMAND_GUIDES,
    CommandGuide,
    ExampleStage,
    command_guide,
)


def command_tree() -> dict[str, click.Command]:
    found: dict[str, click.Command] = {}

    def visit(command: click.Command, path: tuple[str, ...] = ()) -> None:
        found[" ".join(path)] = command
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                visit(child, (*path, name))

    visit(typer.main.get_command(app))
    return found


def example_target(
    argv: tuple[str, ...], commands: dict[str, click.Command]
) -> tuple[str, click.Command, tuple[str, ...]]:
    assert argv[0] == "danvas"
    tokens = argv[1:]
    candidates = sorted(
        ((tuple(path.split()), path, command) for path, command in commands.items() if path),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for prefix, path, command in candidates:
        if tokens[: len(prefix)] == prefix:
            return path, command, tokens[len(prefix) :]
    if tokens and tokens[0].startswith("-"):
        return "", commands[""], tokens
    raise AssertionError(f"Example does not name a public command: {argv!r}")


def validate_argv(argv: tuple[str, ...], commands: dict[str, click.Command]) -> str:
    path, command, trailing = example_target(argv, commands)
    options = {
        option
        for parameter in command.params
        if isinstance(parameter, click.Option)
        for option in (*parameter.opts, *parameter.secondary_opts)
    }
    options.add("--help")
    for token in trailing:
        if token.startswith("--"):
            assert token in options, (argv, token, options)
    return path


def test_command_guides_cover_every_released_group_and_leaf_exactly() -> None:
    commands = command_tree()

    assert len(commands) == 73
    assert len(COMMAND_GUIDES) == 73
    assert set(COMMAND_GUIDES) == set(commands)


def test_guide_examples_workflows_and_relationships_name_real_surface() -> None:
    commands = command_tree()

    for guide in COMMAND_GUIDES.values():
        for example in guide.examples:
            validate_argv(example.argv, commands)
        for workflow in guide.workflows:
            for step in workflow.steps:
                validate_argv(step, commands)
        for related in guide.related_commands:
            assert related in commands, (guide.command, related)


def test_mutation_guides_have_plan_then_apply_without_retyping_effects() -> None:
    guide_fields = {field.name for field in fields(CommandGuide)}

    assert {
        "canvas_read",
        "canvas_mutation",
        "local_write",
        "artifact_class",
        "privacy",
    }.isdisjoint(guide_fields)

    for command, policy in ACCESS_POLICIES.items():
        stages = [example.stage for example in COMMAND_GUIDES[command].examples]
        if policy.canvas_mutation:
            assert stages[:2] == [ExampleStage.PLAN, ExampleStage.APPLY], command
            plan, apply = COMMAND_GUIDES[command].examples[:2]
            assert "--apply" not in plan.argv
            assert "--apply" in apply.argv
        else:
            assert ExampleStage.APPLY not in stages, command


def test_private_and_effect_truth_remain_owned_by_existing_registries() -> None:
    commands = command_tree()
    leaves = {path for path, command in commands.items() if not isinstance(command, click.Group)}

    assert set(ACCESS_POLICIES) == leaves
    assert {
        command
        for command, policy in ARTIFACT_POLICIES.items()
        if policy.artifact_class is ArtifactClass.PRIVATE
    } == {
        "roster",
        "assignments overrides",
        "assignments overrides-sync",
        "gradebook check",
        "gradebook audit",
        "quiz analysis",
        "submissions export",
        "submissions grades",
        "submissions media",
        "submissions feedback",
        "grades post",
        "grades clear",
        "grades comments",
        "grades verify",
        "discussions export",
        "discussions score",
        "announcements export",
        "recordings panopto-captions",
    }


def test_command_guide_lookup_rejects_unknown_path() -> None:
    assert command_guide("assignments update").guide_topics
    with pytest.raises(ValueError, match="No command guide"):
        command_guide("missing command")
