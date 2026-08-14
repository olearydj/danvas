from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from danvas.credentials import (
    MAX_CREDENTIAL_BYTES,
    CredentialInput,
    CredentialKind,
    ResolvedCredential,
    SelectionSource,
    resolve_credential,
    select_credential_input,
)


@pytest.mark.parametrize(
    ("kwargs", "environment", "expected"),
    [
        (
            {
                "explicit_env": "CLI_TOKEN",
                "profile_file": "/profile/token",
            },
            {"CANVAS_API_KEY_FILE": "/process/token"},
            (CredentialKind.ENVIRONMENT, "CLI_TOKEN", SelectionSource.CLI),
        ),
        (
            {"profile_file": "/profile/token"},
            {"CANVAS_API_KEY_ENV": "PROCESS_TOKEN"},
            (CredentialKind.FILE, "/profile/token", SelectionSource.USER_PROFILE),
        ),
        (
            {},
            {"CANVAS_API_KEY_ENV": "PROCESS_TOKEN", "CANVAS_API_KEY": "value"},
            (CredentialKind.ENVIRONMENT, "PROCESS_TOKEN", SelectionSource.PROCESS),
        ),
        (
            {},
            {"CANVAS_API_KEY": "value"},
            (CredentialKind.ENVIRONMENT, "CANVAS_API_KEY", SelectionSource.DEFAULT),
        ),
    ],
)
def test_credential_selection_precedence_has_independent_winners(
    kwargs: dict[str, str],
    environment: dict[str, str],
    expected: tuple[CredentialKind, str, SelectionSource],
) -> None:
    selected = select_credential_input(**kwargs, environ=environment)

    assert (selected.kind, selected.locator, selected.selection_source) == expected


@pytest.mark.parametrize(
    ("kwargs", "environment", "layer"),
    [
        (
            {"explicit_env": "CLI_TOKEN", "explicit_file": "/cli/token"},
            {},
            "command line",
        ),
        (
            {"profile_env": "PROFILE_TOKEN", "profile_file": "/profile/token"},
            {},
            "selected user profile",
        ),
        (
            {},
            {
                "CANVAS_API_KEY_ENV": "PROCESS_TOKEN",
                "CANVAS_API_KEY_FILE": "/process/token",
            },
            "process environment",
        ),
    ],
)
def test_selector_conflicts_fail_at_each_layer(
    kwargs: dict[str, str], environment: dict[str, str], layer: str
) -> None:
    with pytest.raises(SystemExit, match=layer):
        select_credential_input(**kwargs, environ=environment)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "cannot be empty"),
        ("9TOKEN", "environment-variable name"),
        ("TOKEN-NAME", "environment-variable name"),
        ("TOKEN.NAME", "environment-variable name"),
        ("TOKEN NAME", "environment-variable name"),
    ],
)
def test_environment_selector_requires_portable_name(name: str, message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        select_credential_input(explicit_env=name or " ", environ={})


def test_file_selector_requires_absolute_path() -> None:
    with pytest.raises(SystemExit, match="must be absolute"):
        select_credential_input(explicit_file="relative/token", environ={})


def test_environment_resolution_reads_once_removes_selected_and_redacts_repr() -> None:
    token = "random-credential-sentinel-9f7a"
    environment = {"SELECTED_TOKEN": token, "UNRELATED_TOKEN": "leave-me"}
    selected = CredentialInput(
        CredentialKind.ENVIRONMENT,
        "SELECTED_TOKEN",
        SelectionSource.CLI,
    )

    resolved = resolve_credential(selected, environ=environment)

    assert resolved.value == token
    assert resolved.source_kind is CredentialKind.ENVIRONMENT
    assert "SELECTED_TOKEN" not in environment
    assert environment == {"UNRELATED_TOKEN": "leave-me"}
    assert token not in repr(resolved)
    assert repr(resolved) == (
        "ResolvedCredential(value=[redacted], source_kind='environment')"
    )


def test_resolved_credential_assertion_representation_is_redacted() -> None:
    token = "assertion-credential-sentinel-c41b"
    resolved = ResolvedCredential(token, CredentialKind.ENVIRONMENT)

    with pytest.raises(AssertionError) as exc_info:
        assert resolved == "different object"

    assert token not in str(exc_info.value)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "is not set"),
        ("", "is empty"),
        ("abc\0def", "NUL"),
        ("abc\ndef", "multiple lines"),
        ("abc\rdef", "multiple lines"),
    ],
)
def test_invalid_selected_environment_never_falls_back(
    value: str | None, message: str
) -> None:
    environment = {"CANVAS_API_KEY": "fallback-must-not-run"}
    if value is not None:
        environment["SELECTED_TOKEN"] = value
    selected = CredentialInput(
        CredentialKind.ENVIRONMENT,
        "SELECTED_TOKEN",
        SelectionSource.CLI,
    )

    with pytest.raises(SystemExit, match=message):
        resolve_credential(selected, environ=environment)

    assert environment["CANVAS_API_KEY"] == "fallback-must-not-run"
    if value is not None:
        assert "SELECTED_TOKEN" not in environment


def test_removed_environment_value_is_not_inherited_by_a_child() -> None:
    token = "child-inheritance-credential-sentinel"
    variable = "DANVAS_TEST_CHILD_TOKEN"
    environment = os.environ.copy()
    environment[variable] = token
    selected = CredentialInput(
        CredentialKind.ENVIRONMENT,
        variable,
        SelectionSource.CLI,
    )
    resolve_credential(selected, environ=environment)

    child = subprocess.run(
        [sys.executable, "-c", f"import os; print(os.environ.get('{variable}', 'absent'))"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert child.stdout == "absent\n"
    assert token not in child.stdout + child.stderr


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [(b"", "token-value"), (b"\n", "token-value"), (b"\r\n", "token-value")],
)
def test_file_transport_accepts_one_optional_terminal_line_ending(
    tmp_path: Path, suffix: bytes, expected: str
) -> None:
    path = tmp_path / "canvas-token"
    path.write_bytes(b"token-value" + suffix)
    before = path.stat()
    selected = CredentialInput(CredentialKind.FILE, str(path), SelectionSource.CLI)

    resolved = resolve_credential(selected)

    after = path.stat()
    assert resolved.value == expected
    assert resolved.source_kind is CredentialKind.FILE
    assert (after.st_mode, after.st_size, after.st_ino) == (
        before.st_mode,
        before.st_size,
        before.st_ino,
    )


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "is empty"),
        (b"abc\0def", "NUL"),
        (b"abc\ndef", "multiple lines"),
        (b"abc\rdef", "multiple lines"),
        (b"abc\n\n", "multiple lines"),
        (b"\xff", "UTF-8"),
        (b"x" * (MAX_CREDENTIAL_BYTES + 1), "exceeds"),
    ],
)
def test_file_transport_rejects_invalid_content(
    tmp_path: Path, content: bytes, message: str
) -> None:
    path = tmp_path / "canvas-token"
    path.write_bytes(content)
    selected = CredentialInput(CredentialKind.FILE, str(path), SelectionSource.CLI)

    with pytest.raises(SystemExit, match=message):
        resolve_credential(selected)


def test_file_transport_rejects_directory_device_fifo_and_socket(tmp_path: Path) -> None:
    fifo = tmp_path / "token.fifo"
    os.mkfifo(fifo)
    with tempfile.TemporaryDirectory(prefix="danvas-socket-", dir="/private/tmp") as temp:
        socket_path = Path(temp) / "s"
        server = socket.socket(socket.AF_UNIX)
        try:
            candidates = [tmp_path, Path("/dev/null"), fifo]
            try:
                server.bind(str(socket_path))
            except PermissionError:
                # The managed macOS sandbox forbids AF_UNIX bind; CI exercises it.
                pass
            else:
                candidates.append(socket_path)
            for candidate in candidates:
                selected = CredentialInput(
                    CredentialKind.FILE,
                    str(candidate),
                    SelectionSource.CLI,
                )
                with pytest.raises(SystemExit):
                    resolve_credential(selected)
        finally:
            server.close()


def test_projected_volume_style_symlink_is_read_once(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    data = mount / "..data"
    data.mkdir(parents=True)
    target = data / "canvas-token"
    target.write_text("projected-token\n", encoding="utf-8")
    selected_path = mount / "canvas-token"
    selected_path.symlink_to(Path("..data") / "canvas-token")

    resolved = resolve_credential(
        CredentialInput(CredentialKind.FILE, str(selected_path), SelectionSource.PROCESS)
    )

    assert resolved.value == "projected-token"


def test_project_contained_file_and_symlink_are_rejected(tmp_path: Path) -> None:
    project = tmp_path / "course"
    project.mkdir()
    inside = project / "token"
    inside.write_text("credential", encoding="utf-8")
    outside_link = tmp_path / "outside-link"
    outside_link.symlink_to(inside)

    for candidate in (inside, outside_link):
        selected = CredentialInput(
            CredentialKind.FILE,
            str(candidate),
            SelectionSource.CLI,
        )
        with pytest.raises(SystemExit, match="inside the active course project"):
            resolve_credential(selected, project_root=project)


def test_path_replacement_after_open_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "course"
    project.mkdir()
    selected_path = tmp_path / "selected-token"
    replacement = tmp_path / "replacement-token"
    selected_path.write_text("original", encoding="utf-8")
    replacement.write_text("replacement", encoding="utf-8")
    original_open = os.open
    opens = 0

    def replace_after_open(path: Path, flags: int) -> int:
        nonlocal opens
        opens += 1
        descriptor = original_open(path, flags)
        os.replace(replacement, selected_path)
        return descriptor

    monkeypatch.setattr(os, "open", replace_after_open)
    selected = CredentialInput(
        CredentialKind.FILE,
        str(selected_path),
        SelectionSource.CLI,
    )

    with pytest.raises(SystemExit, match="changed while it was opened"):
        resolve_credential(selected, project_root=project)
    assert opens == 1


def test_broad_user_owned_file_permissions_warn_without_revealing_path_or_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "private-name-must-not-print"
    token = "permission-credential-sentinel"
    path.write_text(token, encoding="utf-8")
    path.chmod(0o644)

    resolved = resolve_credential(
        CredentialInput(CredentialKind.FILE, str(path), SelectionSource.CLI)
    )

    warning = capsys.readouterr().err
    assert resolved.value == token
    assert "readable by group or other users" in warning
    assert str(path) not in warning
    assert token not in warning
