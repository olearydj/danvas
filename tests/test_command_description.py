from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import click
import pytest
import typer
from typer.testing import CliRunner

from danvas import __version__
from danvas.access import ACCESS_POLICIES
from danvas.cli import app, normalize_describe_path
from danvas.command_description import (
    COMMAND_GUIDE_SCHEMA,
    describe_json,
    describe_payload,
    describe_text,
)

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def root_command() -> click.Command:
    return typer.main.get_command(app)


def test_variadic_command_path_is_compatible_with_joined_or_split_typer_values() -> None:
    assert normalize_describe_path(["assignments", "create"]) == ("assignments", "create")
    assert normalize_describe_path(["assignments create"]) == ("assignments", "create")


def record_count(record: dict[str, Any]) -> int:
    return 1 + sum(record_count(child) for child in record.get("children", []))


def value_at(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for part in dotted.split("."):
        value = value[part]
    return value


def assert_v1_contract(payload: dict[str, Any], contract: dict[str, Any]) -> None:
    expected_types = {
        "string": str,
        "array": list,
        "object": dict,
    }
    assert payload["schema_version"] == contract["schema_version"]
    for path, expected in contract["required_paths"].items():
        assert isinstance(value_at(payload, path), expected_types[expected]), path


def test_full_json_description_is_deterministic_and_complete() -> None:
    root = root_command()
    first = describe_json(root)
    second = describe_json(root)
    payload = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert payload["schema_version"] == COMMAND_GUIDE_SCHEMA
    assert payload["danvas_version"] == __version__
    assert payload["command_path"] == ""
    assert record_count(payload["command"]) == 75


def test_leaf_description_derives_click_access_and_artifact_truth() -> None:
    root = root_command()
    payload = describe_payload(root, ("assignments", "create"))
    command = payload["command"]
    assert isinstance(root, click.Group)
    assignments = root.commands["assignments"]
    assert isinstance(assignments, click.Group)
    click_command = assignments.commands["create"]

    assert command["command_path"] == "assignments create"
    assert command["access"]["canvas_mutation"] is True
    assert command["access"]["dry_run_kind"] == "canvas_mutation"
    assert command["artifact"]["artifact_class"] == "course_internal"
    assert command["plan_apply"]["apply_option"] is True
    assert [parameter["name"] for parameter in command["parameters"]] == [
        parameter.name for parameter in click_command.params
    ]
    assert command["access"]["authoritative_verification"] == (
        ACCESS_POLICIES["assignments create"].authoritative_verification
    )
    assert {example["stage"] for example in command["examples"]} == {"plan", "apply"}


def test_group_and_text_descriptions_are_bounded_subtrees() -> None:
    root = root_command()
    group = describe_payload(root, ("files",))["command"]
    leaf = describe_payload(root, ("files", "compare"))["command"]
    text = describe_text(root, ("files",))

    assert [child["name"] for child in group["children"]] == [
        "inventory",
        "download",
        "download-one",
        "compare",
        "upload",
    ]
    assert "children" not in leaf
    assert "danvas files" in text
    assert "Commands:" in text
    assert len(text.splitlines()) < 20


def test_schema_fixture_allows_additive_fields_and_detects_breaking_changes() -> None:
    contract = json.loads(
        (ROOT / "tests" / "fixtures" / "sprint22" / "describe-v1-contract.json").read_text(
            encoding="utf-8"
        )
    )
    payload = describe_payload(root_command(), ("assignments", "create"))
    assert_v1_contract(payload, contract)

    additive = copy.deepcopy(payload)
    additive["command"]["future_optional_field"] = "allowed"
    assert_v1_contract(additive, contract)

    breaking = copy.deepcopy(payload)
    del breaking["command"]["identity"]
    with pytest.raises(KeyError):
        assert_v1_contract(breaking, contract)


def test_description_never_emits_runtime_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sentinels = (
        "https://runtime-origin.invalid/",
        "runtime-profile-sentinel",
        "runtime-token-sentinel",
        str(tmp_path),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANVAS_API_URL", sentinels[0])
    monkeypatch.setenv("DANVAS_PROFILE", sentinels[1])
    monkeypatch.setenv("CANVAS_API_KEY", sentinels[2])

    output = describe_json(root_command())

    assert all(sentinel not in output for sentinel in sentinels)


def test_roster_description_is_login_id_only_while_source_layout_stays_versioned() -> None:
    root = root_command()
    roster = describe_json(root, ("roster",))
    init_payload = describe_payload(root, ("init",))["command"]

    assert "LoginID" in roster
    assert "--schema" not in roster
    assert "legacy-v1" not in roster
    source_layout = next(
        parameter
        for parameter in init_payload["parameters"]
        if parameter["name"] == "source_layout"
    )
    assert source_layout["choices"] == ["standard-v1", "legacy-v1"]


def test_describe_cli_formats_and_unknown_path() -> None:
    text_result = runner.invoke(app, ["describe", "assignments", "create"])
    json_result = runner.invoke(
        app,
        ["describe", "assignments", "create", "--format", "json"],
    )
    missing = runner.invoke(app, ["describe", "assignments", "missing"])

    assert text_result.exit_code == 0
    assert text_result.output.startswith("danvas assignments create\n")
    assert json.loads(json_result.output)["command_path"] == "assignments create"
    assert missing.exit_code == 2
    assert "Unknown command path" in missing.output
    assert "danvas --help" in missing.output
