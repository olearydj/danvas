from __future__ import annotations

import subprocess

import pytest
from secretpath import clear_cache

from danvas.auth import resolve_api_key


@pytest.fixture(autouse=True)
def _clear_secretpath_cache() -> None:
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
