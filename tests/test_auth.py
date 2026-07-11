from __future__ import annotations

import subprocess
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from secretpath import SecretMiss, clear_cache

from danvas.auth import (
    build_auth_doctor_report,
    command_auth_doctor,
    resolve_api_key,
    safe_auth_error,
)


@pytest.fixture(autouse=True)
def _clear_secretpath_cache() -> Generator[None]:
    clear_cache()
    yield
    clear_cache()


def test_resolve_api_key_uses_env_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANVAS_API_KEY", "from-env")

    assert resolve_api_key(
        provider="env",
        op_reference="op://Vault/Canvas/credential",
        env_var="CANVAS_API_KEY",
    ) == ("from-env", "env:CANVAS_API_KEY")


def test_resolve_api_key_auto_prefers_1password(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="from-op\n", stderr="")

    monkeypatch.setenv("CANVAS_API_KEY", "from-env")
    monkeypatch.setattr("secretpath.core.shutil.which", lambda name: "/usr/local/bin/op")
    monkeypatch.setattr("secretpath.core.subprocess.run", fake_run)

    assert resolve_api_key(
        provider="auto",
        op_reference="op://Vault/Canvas/credential",
        env_var="CANVAS_API_KEY",
    ) == ("from-op", "1password")
    assert len(calls) == 1


def test_resolve_api_key_auto_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANVAS_API_KEY", "from-env")
    monkeypatch.setattr("secretpath.core.shutil.which", lambda name: None)

    assert resolve_api_key(
        provider="auto",
        op_reference="op://Vault/Canvas/credential",
        env_var="CANVAS_API_KEY",
    ) == ("from-env", "env:CANVAS_API_KEY")


def test_resolve_api_key_exits_with_safe_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CANVAS_API_KEY", raising=False)
    monkeypatch.setattr("secretpath.core.shutil.which", lambda name: None)

    with pytest.raises(SystemExit) as excinfo:
        resolve_api_key(
            provider="auto",
            op_reference="op://Vault/Canvas/credential",
            env_var="CANVAS_API_KEY",
        )

    message = str(excinfo.value)
    assert "Canvas API key" in message
    assert "1password" in message
    assert "env" in message
    assert "op://" not in message
    assert "CANVAS_API_KEY" not in message


@pytest.mark.parametrize("marker", ["token=", "verifier=", "access_token="])
def test_safe_auth_error_redacts_credentials(marker: str) -> None:
    message = safe_auth_error(RuntimeError(f"request failed {marker}abc123 trailing"))

    assert "abc123" not in message
    assert f"{marker}[redacted]" in message


def test_auth_doctor_reports_canvas_secret_without_canvas_ping(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "danvas.auth.doctor_report",
        lambda check_resolution: {
            "op": {"available": True, "path": "/usr/bin/op"},
            "direnv": {"available": False, "path": None},
            "config_files": [],
            "secrets": ["canvas", "openai"],
            "resolutions": [],
            "issues": [],
        },
    )
    monkeypatch.setattr(
        "danvas.auth.resolve_named_secret",
        lambda *args, **kwargs: SimpleNamespace(value="token", source="1password"),
    )

    command_auth_doctor(
        SimpleNamespace(
            api_url="https://canvas.example/",
            secret_provider="auto",
            op_reference="",
            api_key_env="CANVAS_API_KEY",
            check_canvas=False,
            json=False,
        )
    )

    output = capsys.readouterr().out
    assert "Auth doctor" in output
    assert "canvas: resolved from 1password" in output
    assert "Canvas API: not checked" in output
    assert "token" not in output


def test_auth_doctor_json_reports_canvas_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "danvas.auth.doctor_report",
        lambda check_resolution: {
            "op": {"available": True, "path": "/usr/bin/op"},
            "direnv": {"available": False, "path": None},
            "config_files": [],
            "secrets": ["canvas"],
            "resolutions": [],
            "issues": [],
        },
    )
    monkeypatch.setattr(
        "danvas.auth.resolve_named_secret",
        lambda *args, **kwargs: SimpleNamespace(value="token", source="env:CANVAS_API_KEY"),
    )

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            assert api_url == "https://canvas.example/"
            assert api_key == "token"

        def get_current_user(self) -> SimpleNamespace:
            return SimpleNamespace(id=42, name="Instructor")

    monkeypatch.setattr("danvas.auth.Canvas", FakeCanvas)

    report = build_auth_doctor_report(
        SimpleNamespace(
            api_url="https://canvas.example/",
            secret_provider="env",
            op_reference="",
            api_key_env="CANVAS_API_KEY",
            check_canvas=True,
        )
    )

    assert report["secretpath"]["resolutions"] == [
        {"name": "canvas", "resolved": True, "source": "env:CANVAS_API_KEY"}
    ]
    assert report["canvas"]["reachable"] is True
    assert report["canvas"]["current_user"] == {"id": 42, "name": "Instructor"}
    assert report["issues"] == []


def test_auth_doctor_exits_nonzero_when_canvas_secret_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "danvas.auth.doctor_report",
        lambda check_resolution: {
            "op": {"available": False, "path": None},
            "direnv": {"available": False, "path": None},
            "config_files": [],
            "secrets": [],
            "resolutions": [],
            "issues": [],
        },
    )
    monkeypatch.setattr(
        "danvas.auth.resolve_named_secret",
        lambda *args, **kwargs: SecretMiss(name="canvas", attempts=()),
    )

    with pytest.raises(SystemExit) as excinfo:
        command_auth_doctor(
            SimpleNamespace(
                api_url="https://canvas.example/",
                secret_provider="auto",
                op_reference="",
                api_key_env="CANVAS_API_KEY",
                check_canvas=False,
                json=True,
            )
        )

    assert excinfo.value.code == 1
