"""Exercise external credentials through the real CLI and subprocess boundary."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from danvas.cli import app
from danvas.credential_command import CredentialCommandError, read_command
from danvas.credentials import CredentialKind, select_credential_input
from danvas.profiles import load_user_profiles


@pytest.fixture
def command_profile(tmp_path, monkeypatch):
    marker = tmp_path / "calls"
    helper = tmp_path / "helper.py"
    helper.write_text(
        "from pathlib import Path\n"
        f'Path({str(marker)!r}).write_text("called")\n'
        'print("synthetic-canvas-token")\n'
    )
    config = tmp_path / "user.toml"
    config.write_text(
        'default_profile="test"\n[profiles.test]\napi_url="https://canvas.example/"\n'
        f"credential_command={json.dumps([sys.executable, str(helper)])}\n"
    )
    project = tmp_path / "course"
    (project / ".danvas").mkdir(parents=True)
    (project / ".danvas/config.toml").write_text('[canvas]\nprofile="test"\n')
    monkeypatch.chdir(project)
    monkeypatch.setattr("danvas.profiles.user_config_path", lambda: config)
    for name in (
        "CANVAS_SECRET_PROVIDER",
        "CANVAS_API_KEY_OP_REFERENCE",
        "CANVAS_API_KEY_ENV",
        "CANVAS_API_KEY_FILE",
        "DANVAS_PROFILE",
        "CANVAS_API_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    return marker, helper, config, project


def test_cli_lazy_resolution_and_safe_report(command_profile, monkeypatch):
    marker, _, _, _ = command_profile
    runner = CliRunner()
    for args in (["--help"], ["auth", "doctor", "--json"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert not marker.exists()
    payload = json.loads(result.output)
    assert payload["credential"]["status"] == "not_requested"
    assert payload["credential"]["kind"] == "command"

    class Canvas:
        def __init__(self, url, token):
            assert url == "https://canvas.example/"
            assert token == "synthetic-canvas-token"
            assert token not in os.environ.values()

        def get_current_user(self):
            return SimpleNamespace(id=1, name="Synthetic")

    monkeypatch.setattr("danvas.auth.Canvas", Canvas)
    result = runner.invoke(app, ["auth", "doctor", "--check-canvas", "--json"])
    assert result.exit_code == 0, result.output
    assert marker.exists()
    assert "synthetic-canvas-token" not in result.output
    assert "helper.py" not in result.output
    assert json.loads(result.output)["canvas"]["reachable"]


@pytest.mark.parametrize("selector", ["env", "file"])
def test_cli_explicit_transport_overrides_command(command_profile, monkeypatch, selector):
    marker, _, _, project = command_profile
    if selector == "env":
        monkeypatch.setenv("OVERRIDE_TOKEN", "override-token")
        args = ["--api-key-env", "OVERRIDE_TOKEN"]
    else:
        credential = project.parent / "token"
        credential.write_text("override-token")
        credential.chmod(0o600)
        args = ["--api-key-file", str(credential)]
    result = CliRunner().invoke(app, ["auth", "doctor", "--json", *args])
    assert result.exit_code == 0, result.output
    assert not marker.exists()
    assert json.loads(result.output)["credential"]["kind"] == (
        "environment" if selector == "env" else "file"
    )


@pytest.mark.parametrize(
    "config",
    [
        '[canvas]\nprofile="test"\napi_url="https://wrong.example/"\n',
        '[canvas]\nprofile="test"\ncredential_command=["/bin/echo", "bad"]\n',
    ],
)
def test_course_cannot_redirect_or_select_command(command_profile, config):
    marker, _, _, project = command_profile
    (project / ".danvas/config.toml").write_text(config)
    result = CliRunner().invoke(app, ["auth", "doctor", "--check-canvas", "--json"])
    assert result.exit_code != 0
    assert not marker.exists()


@pytest.mark.parametrize(
    "value", ['"command string"', "[]", '["relative"]', "[123]", '["/bin/echo", 123]']
)
def test_invalid_profile_command(command_profile, value):
    _, _, config, _ = command_profile
    config.write_text(
        '[profiles.test]\napi_url="https://canvas.example/"\ncredential_command=' + value
    )
    with pytest.raises(SystemExit, match="credential_command"):
        load_user_profiles(config)


@pytest.mark.parametrize("extra", ['api_key_env="KEY"', 'api_key_file="/tmp/token"'])
def test_profile_transport_conflict(command_profile, extra):
    _, _, config, _ = command_profile
    with config.open("a") as f:
        f.write(extra + "\n")
    with pytest.raises(SystemExit, match="exactly one"):
        load_user_profiles(config)


def test_command_profile_requires_origin(command_profile):
    _, _, config, _ = command_profile
    config.write_text('[profiles.test]\ncredential_command=["/bin/echo"]')
    with pytest.raises(SystemExit, match="bind an api_url"):
        load_user_profiles(config)


def test_profile_precedes_process_selector():
    selected = select_credential_input(
        profile_command=("/bin/echo", "opaque"), environ={"CANVAS_API_KEY_ENV": "OTHER"}
    )
    assert selected.kind is CredentialKind.COMMAND
    assert "opaque" not in repr(selected)


@pytest.mark.parametrize(
    "code,expected",
    [
        ('import sys; print("sensitive", file=sys.stderr); sys.exit(1)', "failed"),
        ('print("x" * 20000)', "output is too large"),
        ('import sys; sys.stderr.write("x" * 20000)', "diagnostics are too large"),
        ("import time; time.sleep(10)", "timed out"),
        ('print("op://private/item/field")', "one token"),
        ('print("bad token")', "one token"),
        ('print("")', "one token"),
        ("import sys; sys.stdout.buffer.write(bytes([255]))", "invalid text"),
    ],
)
def test_command_failure_is_safe(code, expected, monkeypatch):
    monkeypatch.setattr("danvas.credential_command.COMMAND_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(CredentialCommandError, match=expected) as caught:
        read_command((sys.executable, "-c", code))
    assert "sensitive" not in str(caught.value)
    assert "op://" not in str(caught.value)


def test_literal_argv_and_line_ending():
    assert (
        read_command(
            (
                sys.executable,
                "-c",
                'import sys; sys.stdout.write(sys.argv[1]+"\\r\\n")',
                "$(literal)",
            )
        )
        == "$(literal)"
    )


def test_missing_executable():
    with pytest.raises(CredentialCommandError, match="could not start"):
        read_command(("/nonexistent/danvas-test-helper",))


def test_closed_pipes_do_not_disable_deadline(monkeypatch):
    monkeypatch.setattr("danvas.credential_command.COMMAND_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(CredentialCommandError, match="timed out"):
        read_command(
            (sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(10)")
        )


def test_keyboard_interrupt_cleans_up_child(tmp_path, monkeypatch):
    pidfile = tmp_path / "pid"
    code = f"import os,time; from pathlib import Path; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(10)"

    def interrupt(process):
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text():
                break
            time.sleep(0.01)
        raise KeyboardInterrupt

    monkeypatch.setattr("danvas.credential_command._collect", interrupt)
    with pytest.raises(KeyboardInterrupt):
        read_command((sys.executable, "-c", code))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), signal.SIGCONT)


def test_failed_command_does_not_fall_back_to_ambient_token(command_profile, monkeypatch):
    marker, helper, _, _ = command_profile
    helper.write_text(
        'import sys\nprint("synthetic-private-error", file=sys.stderr)\nsys.exit(9)\n'
    )
    monkeypatch.setenv("CANVAS_API_KEY", "ambient-token")
    result = CliRunner().invoke(app, ["auth", "doctor", "--check-canvas", "--json"])
    assert result.exit_code == 1
    assert "synthetic-private-error" not in result.output
    assert "ambient-token" not in result.output
    payload = json.loads(result.output)
    assert payload["credential"]["status"] == "unreadable"
    assert payload["canvas"]["reachable"] is False
    assert not marker.exists()


def test_normal_canvas_client_uses_command(command_profile, monkeypatch):
    from danvas.auth import canvas_from_args
    from danvas.cli import args_for

    marker, _, _, project = command_profile
    args = args_for(api_url=None, project_root=str(project))
    observed = []
    monkeypatch.setattr("danvas.auth.Canvas", lambda url, token: observed.append((url, token)))
    canvas_from_args(args)
    assert marker.exists()
    assert observed == [("https://canvas.example/", "synthetic-canvas-token")]
