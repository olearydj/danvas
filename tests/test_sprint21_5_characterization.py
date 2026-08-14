from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
import typer

import danvas.auth as auth_module
import danvas.cli as cli_module
from danvas.access import ACCESS_POLICIES
from danvas.auth import canvas_from_args, command_auth_doctor, resolve_api_key
from danvas.cli import app
from danvas.profiles import CanvasContext, resolve_canvas_context

ROOT = Path(__file__).parents[1]
CURRENT_AUTH_OPTIONS = {
    "--api-url",
    "--profile",
    "--secret-name",
    "--secret-provider",
    "--op-reference",
    "--api-key-env",
}


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


def auth_args(context: CanvasContext) -> SimpleNamespace:
    return SimpleNamespace(
        api_url=context.api_url,
        secret_name=context.secret_name,
        secret_provider=context.secret_provider,
        op_reference=context.op_reference,
        api_key_env=context.api_key_env,
    )


def write_profile(path: Path, *, name: str, api_url: str, token_env: str) -> None:
    path.write_text(
        (
            f"[profiles.{name}]\n"
            f'api_url = "{api_url}"\n'
            'secret_provider = "env"\n'
            f'api_key_env = "{token_env}"\n'
        ),
        encoding="utf-8",
    )


def test_current_authentication_option_surface_is_exactly_forty_five_commands() -> None:
    commands = leaf_commands()
    canvas_commands = {
        name for name, policy in ACCESS_POLICIES.items() if policy.canvas_read
    }
    actual = {
        name: option_names(command).intersection(CURRENT_AUTH_OPTIONS)
        for name, command in commands.items()
    }

    assert len(commands) == 55
    assert len(canvas_commands) == 45
    assert set(actual) == set(commands)
    assert {
        name for name, names in actual.items() if names
    } == canvas_commands
    assert all(actual[name] == CURRENT_AUTH_OPTIONS for name in canvas_commands)
    assert all(actual[name] == set() for name in set(commands).difference(canvas_commands))

    for name in canvas_commands:
        command = commands[name]
        assert all(option(command, flag).default is None for flag in CURRENT_AUTH_OPTIONS)
        provider = option(command, "--secret-provider")
        assert isinstance(provider.type, click.Choice)
        assert tuple(provider.type.choices) == ("auto", "1password", "env")


def test_current_secretpath_wrapper_and_provider_notice_are_characterized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_resolution: dict[str, Any] = {}

    def fake_resolve_named_secret(name: str, **kwargs: Any) -> SimpleNamespace:
        captured_resolution["name"] = name
        captured_resolution.update(kwargs)
        return SimpleNamespace(
            value="credential-sentinel",
            source="1password",
            as_tuple=lambda: ("credential-sentinel", "1password"),
        )

    monkeypatch.setattr(auth_module, "resolve_named_secret", fake_resolve_named_secret)

    assert resolve_api_key(
        provider="1password",
        op_reference="op://Example/Canvas/credential",
        env_var="EXAMPLE_CANVAS_TOKEN",
        secret_name="canvas-example",
    ) == ("credential-sentinel", "1password")
    assert captured_resolution == {
        "name": "canvas-example",
        "display_name": "Canvas API key",
        "provider": "1password",
        "op_reference": "op://Example/Canvas/credential",
        "env_var": "EXAMPLE_CANVAS_TOKEN",
    }

    canvas_init: dict[str, str] = {}

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            canvas_init.update(api_url=api_url, api_key=api_key)

    monkeypatch.setattr(auth_module, "Canvas", FakeCanvas)
    monkeypatch.setattr(
        auth_module,
        "resolve_api_key",
        lambda **kwargs: ("credential-sentinel", "1password"),
    )

    canvas_from_args(
        SimpleNamespace(
            api_url="https://canvas.example.edu/",
            secret_name="canvas-example",
            secret_provider="1password",
            op_reference="op://Example/Canvas/credential",
            api_key_env="EXAMPLE_CANVAS_TOKEN",
        )
    )

    assert canvas_init == {
        "api_url": "https://canvas.example.edu/",
        "api_key": "credential-sentinel",
    }
    assert capsys.readouterr().out == "Using API key from: 1password\n"


def test_current_auth_doctor_text_and_json_shapes_are_characterized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def current_doctor_report(*, check_resolution: bool) -> dict[str, Any]:
        assert check_resolution is False
        return {
            "op": {"available": True, "path": "/usr/bin/op"},
            "direnv": {"available": False, "path": None},
            "config_files": [],
            "secrets": ["canvas-example"],
            "resolutions": [],
            "issues": [],
        }

    monkeypatch.setattr(auth_module, "doctor_report", current_doctor_report)
    monkeypatch.setattr(
        auth_module,
        "resolve_named_secret",
        lambda *args, **kwargs: SimpleNamespace(
            value="credential-sentinel", source="1password"
        ),
    )
    base_args = {
        "profile": "example",
        "api_url": "https://canvas.example.edu/",
        "secret_name": "canvas-example",
        "secret_provider": "1password",
        "op_reference": "op://Example/Canvas/credential",
        "api_key_env": "EXAMPLE_CANVAS_TOKEN",
        "check_canvas": False,
    }

    command_auth_doctor(SimpleNamespace(**base_args, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "profile": "example",
        "api_url": "https://canvas.example.edu/",
        "secretpath": {
            "op": {"available": True, "path": "/usr/bin/op"},
            "direnv": {"available": False, "path": None},
            "config_files": [],
            "secrets": ["canvas-example"],
            "resolutions": [
                {
                    "name": "canvas-example",
                    "resolved": True,
                    "source": "1password",
                }
            ],
            "issues": [],
        },
        "canvas": {
            "checked": False,
            "reachable": None,
            "current_user": None,
            "error": "",
        },
        "issues": [],
    }

    command_auth_doctor(SimpleNamespace(**base_args, json=False))
    assert capsys.readouterr().out == (
        "Auth doctor\n"
        "Profile: example\n"
        "API URL: https://canvas.example.edu/\n"
        "op: available\n"
        "direnv: not found\n"
        "secretpath config files:\n"
        "  - none\n"
        "secretpath resolutions:\n"
        "  - canvas-example: resolved from 1password\n"
        "Canvas API: not checked\n"
        "status: ok\n"
    )


def test_missing_url_currently_fails_before_reading_any_auth_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_module,
        "resolve_api_key",
        lambda **kwargs: pytest.fail("credential resolution must not run"),
    )

    with pytest.raises(SystemExit, match="before resolving credentials"):
        canvas_from_args(SimpleNamespace(api_url=None))


def test_main_currently_loads_local_dotenv_inputs_in_debugger_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_token = "dotenv-credential-sentinel"
    dotenv_url = "https://dotenv.canvas.example.edu/"
    (tmp_path / ".env").write_text(
        f"CANVAS_API_KEY={dotenv_token}\nCANVAS_API_URL={dotenv_url}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CANVAS_API_KEY", raising=False)
    monkeypatch.delenv("CANVAS_API_URL", raising=False)
    monkeypatch.setattr(sys, "gettrace", lambda: object())
    observed: dict[str, Any] = {}

    def capture_app() -> None:
        observed["api_key"] = os.environ.get("CANVAS_API_KEY")
        observed["context"] = resolve_canvas_context(
            start=tmp_path,
            profiles_path=tmp_path / "missing-user-config.toml",
        )

    monkeypatch.setattr(cli_module, "app", capture_app)
    cli_module.main()

    assert observed["api_key"] == dotenv_token
    context = observed["context"]
    assert isinstance(context, CanvasContext)
    assert context.api_url == dotenv_url
    assert context.api_url_source == "CANVAS_API_URL"


def test_current_explicit_profile_mismatch_warns_but_authenticates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    context = resolve_canvas_context(
        explicit_profile="other",
        start=project,
        profiles_path=profiles_path,
        environ={},
    )
    warning = capsys.readouterr().err
    resolution: dict[str, Any] = {}
    canvas_init: dict[str, str] = {}

    def fake_resolve_api_key(**kwargs: Any) -> tuple[str, str]:
        resolution.update(kwargs)
        return "other-credential-sentinel", "env:OTHER_CANVAS_TOKEN"

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            canvas_init.update(api_url=api_url, api_key=api_key)

    monkeypatch.setattr(auth_module, "resolve_api_key", fake_resolve_api_key)
    monkeypatch.setattr(auth_module, "Canvas", FakeCanvas)
    canvas_from_args(auth_args(context))

    assert "explicitly selected profile 'other'" in warning
    assert "project URL keeps precedence" in warning
    assert resolution == {
        "provider": "env",
        "op_reference": "",
        "env_var": "OTHER_CANVAS_TOKEN",
        "secret_name": "canvas",
    }
    assert canvas_init == {
        "api_url": "https://project.canvas.example.edu/",
        "api_key": "other-credential-sentinel",
    }


def test_current_project_only_origin_authenticates_without_user_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas" / "config.toml").write_text(
        '[canvas]\napi_url = "https://project.canvas.example.edu/"\ncourse_id = 101\n',
        encoding="utf-8",
    )
    context = resolve_canvas_context(
        start=project,
        profiles_path=tmp_path / "missing-user-config.toml",
        environ={"CANVAS_API_KEY": "default-credential-sentinel"},
    )
    canvas_init: dict[str, str] = {}

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            canvas_init.update(api_url=api_url, api_key=api_key)

    monkeypatch.setattr(
        auth_module,
        "resolve_api_key",
        lambda **kwargs: ("default-credential-sentinel", "env:CANVAS_API_KEY"),
    )
    monkeypatch.setattr(auth_module, "Canvas", FakeCanvas)
    canvas_from_args(auth_args(context))

    assert context.profile is None
    assert context.api_url_source == ".danvas/config.toml"
    assert context.secret_provider == "auto"
    assert context.api_key_env == "CANVAS_API_KEY"
    assert canvas_init == {
        "api_url": "https://project.canvas.example.edu/",
        "api_key": "default-credential-sentinel",
    }
