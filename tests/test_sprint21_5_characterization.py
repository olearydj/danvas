from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
import typer
from typer.testing import CliRunner

import danvas.auth as auth_module
import danvas.cli as cli_module
from danvas.access import ACCESS_POLICIES
from danvas.auth import AUTH_DOCTOR_SCHEMA, canvas_from_args, command_auth_doctor
from danvas.cli import app
from danvas.credentials import CredentialInput, CredentialKind, SelectionSource
from danvas.profiles import resolve_canvas_context

ROOT = Path(__file__).parents[1]
runner = CliRunner()
CURRENT_AUTH_OPTIONS = {
    "--api-url",
    "--profile",
    "--api-key-env",
    "--api-key-file",
}
RETIRED_AUTH_OPTIONS = {"--secret-name", "--secret-provider", "--op-reference"}


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


def option_names(command: click.Command) -> set[str]:
    names: set[str] = set()
    for parameter in command.params:
        if isinstance(parameter, click.Option):
            names.update(parameter.opts)
            names.update(parameter.secondary_opts)
    return names


def option(command: click.Command, name: str) -> click.Option:
    for parameter in command.params:
        if isinstance(parameter, click.Option) and name in (
            *parameter.opts,
            *parameter.secondary_opts,
        ):
            return parameter
    raise AssertionError(f"Missing {name} on {command.name}")


def write_profile(path: Path, *, name: str, api_url: str, token_env: str) -> None:
    path.write_text(
        (
            f"[profiles.{name}]\n"
            f'api_url = "{api_url}"\n'
            f'api_key_env = "{token_env}"\n'
        ),
        encoding="utf-8",
    )


def test_provider_neutral_authentication_surface_is_exactly_forty_six_commands() -> None:
    commands = leaf_commands()
    canvas_commands = {
        name for name, policy in ACCESS_POLICIES.items() if policy.canvas_read
    }
    relevant = CURRENT_AUTH_OPTIONS | RETIRED_AUTH_OPTIONS
    actual = {
        name: option_names(command).intersection(relevant)
        for name, command in commands.items()
    }

    assert len(commands) == 61
    assert len(canvas_commands) == 46
    assert set(actual) == set(commands)
    assert {name for name, names in actual.items() if names} == canvas_commands
    assert all(actual[name] == CURRENT_AUTH_OPTIONS for name in canvas_commands)
    assert all(actual[name] == set() for name in set(commands).difference(canvas_commands))
    assert all(
        option(commands[name], flag).default is None
        for name in canvas_commands
        for flag in CURRENT_AUTH_OPTIONS
    )


def test_every_retired_cli_spelling_fails_as_an_unknown_option() -> None:
    canvas_commands = sorted(
        name for name, policy in ACCESS_POLICIES.items() if policy.canvas_read
    )

    for command_name in canvas_commands:
        for retired in sorted(RETIRED_AUTH_OPTIONS):
            result = runner.invoke(app, [*command_name.split(), retired, "retired-value"])
            assert result.exit_code == 2, (command_name, retired, result.output)
            assert "No such option" in result.output, (
                command_name,
                retired,
                result.output,
            )


def test_provider_specific_runtime_and_dependencies_are_absent() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "src" / "danvas").glob("*.py"))
    )
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for spelling in (
        "secretpath",
        "resolve_named_secret",
        "load_dotenv",
        "op://",
    ):
        assert spelling not in production
    assert '"secretpath' not in pyproject
    assert '"python-dotenv' not in pyproject


def test_provider_neutral_auth_doctor_schema_replaces_old_shape(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = "credential-sentinel"
    monkeypatch.setenv("EXAMPLE_CANVAS_TOKEN", token)
    base_args = {
        "profile": "example",
        "api_url": "https://canvas.example.edu/",
        "api_url_source": "profile 'example'",
        "origin_binding_source": "profile 'example'",
        "origin_binding_status": "bound",
        "origin_binding_error": "",
        "credential_input": CredentialInput(
            CredentialKind.ENVIRONMENT,
            "EXAMPLE_CANVAS_TOKEN",
            SelectionSource.USER_PROFILE,
        ),
        "credential_project_root": None,
        "check_canvas": False,
    }

    command_auth_doctor(SimpleNamespace(**base_args, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema": AUTH_DOCTOR_SCHEMA,
        "profile": "example",
        "origin": {
            "status": "bound",
            "api_url": "https://canvas.example.edu/",
            "source": "profile 'example'",
            "binding_source": "profile 'example'",
            "error": "",
        },
        "credential": {
            "kind": "environment",
            "selection_source": "user_profile",
            "locator": "EXAMPLE_CANVAS_TOKEN",
            "status": "resolved",
            "warnings": [],
            "error": "",
        },
        "canvas": {
            "checked": False,
            "reachable": None,
            "current_user": None,
            "error": "",
        },
        "issues": [],
    }
    assert "secretpath" not in payload
    assert "api_url" not in payload
    assert token not in repr(payload)

    monkeypatch.setenv("EXAMPLE_CANVAS_TOKEN", token)
    command_auth_doctor(SimpleNamespace(**base_args, json=False))
    assert capsys.readouterr().out == (
        "Auth doctor\n"
        f"Schema: {AUTH_DOCTOR_SCHEMA}\n"
        "Profile: example\n"
        "API URL: https://canvas.example.edu/\n"
        "Origin binding: bound\n"
        "Origin binding source: profile 'example'\n"
        "Credential transport: environment\n"
        "Credential selection: user_profile\n"
        "Credential locator: EXAMPLE_CANVAS_TOKEN\n"
        "Credential status: resolved\n"
        "Canvas API: not checked\n"
        "status: ok\n"
    )


def test_missing_url_fails_before_reading_any_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_module,
        "resolve_canvas_credential",
        lambda args: pytest.fail("credential resolution must not run"),
    )

    with pytest.raises(SystemExit, match="before resolving credentials"):
        canvas_from_args(SimpleNamespace(api_url=None))


def test_main_ignores_local_dotenv_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text(
        "CANVAS_API_KEY=dotenv-credential-sentinel\n"
        "CANVAS_API_URL=https://dotenv.canvas.example.edu/\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CANVAS_API_KEY", raising=False)
    monkeypatch.delenv("CANVAS_API_URL", raising=False)
    observed: dict[str, object] = {}

    def capture_app() -> None:
        observed["api_key"] = os.environ.get("CANVAS_API_KEY")
        observed["api_url"] = os.environ.get("CANVAS_API_URL")

    monkeypatch.setattr(cli_module, "app", capture_app)
    cli_module.main()

    assert observed == {"api_key": None, "api_url": None}


def test_profile_mismatch_fails_before_authentication(tmp_path: Path) -> None:
    profiles_path = tmp_path / "user-config.toml"
    write_profile(
        profiles_path,
        name="other",
        api_url="https://other.canvas.example.edu/",
        token_env="OTHER_CANVAS_TOKEN",
    )
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example.edu/"\ncourse_id = 101\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Canvas origin conflict"):
        resolve_canvas_context(
            explicit_profile="other",
            start=project,
            profiles_path=profiles_path,
            environ={},
        )


def test_project_only_origin_fails_before_authentication(tmp_path: Path) -> None:
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example.edu/"\ncourse_id = 101\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="not bound to user intent"):
        resolve_canvas_context(
            start=project,
            profiles_path=tmp_path / "missing-user-config.toml",
            environ={"CANVAS_API_KEY": "default-credential-sentinel"},
        )
