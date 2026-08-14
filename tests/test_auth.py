from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from danvas.auth import (
    AUTH_DOCTOR_SCHEMA,
    build_auth_doctor_report,
    canvas_from_args,
    command_auth_doctor,
    resolve_canvas_credential,
    safe_auth_error,
)
from danvas.credentials import (
    CredentialInput,
    CredentialKind,
    ResolvedCredential,
    SelectionSource,
)


def credential_input(
    kind: CredentialKind, locator: str, source: SelectionSource = SelectionSource.CLI
) -> CredentialInput:
    return CredentialInput(kind=kind, locator=locator, selection_source=source)


def doctor_args(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "profile": None,
        "api_url": "https://canvas.example/",
        "api_url_source": "--api-url",
        "origin_binding_source": "--api-url",
        "origin_binding_status": "bound",
        "origin_binding_error": "",
        "credential_input": credential_input(
            CredentialKind.ENVIRONMENT, "DANVAS_TEST_CANVAS_TOKEN"
        ),
        "credential_project_root": None,
        "check_canvas": False,
        "json": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_canvas_requires_instance_before_credential_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "danvas.auth.resolve_canvas_credential",
        lambda args: pytest.fail("credential resolution must not run"),
    )

    with pytest.raises(SystemExit, match="before resolving credentials"):
        canvas_from_args(SimpleNamespace(api_url=None))


def test_environment_is_removed_before_canvas_construction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    variable = "DANVAS_TEST_CANVAS_TOKEN"
    token = "canvas-construction-credential-sentinel"
    monkeypatch.setenv(variable, token)
    observed: dict[str, str | bool] = {}

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            observed.update(
                api_url=api_url,
                api_key=api_key,
                variable_absent=variable not in os.environ,
            )

    monkeypatch.setattr("danvas.auth.Canvas", FakeCanvas)
    result = canvas_from_args(
        SimpleNamespace(
            api_url="https://canvas.example/",
            credential_input=credential_input(CredentialKind.ENVIRONMENT, variable),
            credential_project_root=None,
        )
    )

    assert isinstance(result, FakeCanvas)
    assert observed == {
        "api_url": "https://canvas.example/",
        "api_key": token,
        "variable_absent": True,
    }
    output = capsys.readouterr().out
    assert output == "Using Canvas credential from: environment\n"
    assert token not in output


def test_file_uses_shared_canvas_credential_resolver(tmp_path: Path) -> None:
    path = tmp_path / "canvas-token"
    path.write_text("file-credential-sentinel\n", encoding="utf-8")

    resolved = resolve_canvas_credential(
        SimpleNamespace(
            api_url="https://canvas.example/",
            credential_input=credential_input(CredentialKind.FILE, str(path)),
            credential_project_root=None,
        )
    )

    assert resolved.value == "file-credential-sentinel"
    assert resolved.source_kind is CredentialKind.FILE
    assert resolved.value not in repr(resolved)


def test_canvas_credential_result_repr_is_redacted() -> None:
    token = "canvas-wrapper-credential-sentinel"
    resolved = ResolvedCredential(token, CredentialKind.ENVIRONMENT)

    assert token not in repr(resolved)


@pytest.mark.parametrize("marker", ["token=", "verifier=", "access_token="])
def test_safe_auth_error_redacts_credentials(marker: str) -> None:
    message = safe_auth_error(RuntimeError(f"request failed {marker}abc123 trailing"))

    assert "abc123" not in message
    assert f"{marker}[redacted]" in message


def test_auth_doctor_reports_neutral_environment_without_canvas_ping(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "doctor-credential-sentinel"
    monkeypatch.setenv("DANVAS_TEST_CANVAS_TOKEN", token)

    command_auth_doctor(doctor_args())

    output = capsys.readouterr().out
    assert f"Schema: {AUTH_DOCTOR_SCHEMA}" in output
    assert "Origin binding: bound" in output
    assert "Credential transport: environment" in output
    assert "Credential locator: DANVAS_TEST_CANVAS_TOKEN" in output
    assert "Credential status: resolved" in output
    assert "Canvas API: not checked" in output
    assert "status: ok" in output
    assert token not in output


def test_auth_doctor_json_reports_canvas_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DANVAS_TEST_CANVAS_TOKEN", "token")

    class FakeCanvas:
        def __init__(self, api_url: str, api_key: str) -> None:
            assert api_url == "https://canvas.example/"
            assert api_key == "token"

        def get_current_user(self) -> SimpleNamespace:
            return SimpleNamespace(id=42, name="Instructor")

    monkeypatch.setattr("danvas.auth.Canvas", FakeCanvas)

    report = build_auth_doctor_report(doctor_args(check_canvas=True))

    assert report["schema"] == AUTH_DOCTOR_SCHEMA
    assert report["origin"] == {
        "status": "bound",
        "api_url": "https://canvas.example/",
        "source": "--api-url",
        "binding_source": "--api-url",
        "error": "",
    }
    assert report["credential"] == {
        "kind": "environment",
        "selection_source": "cli",
        "locator": "DANVAS_TEST_CANVAS_TOKEN",
        "status": "resolved",
        "warnings": [],
        "error": "",
    }
    assert report["canvas"]["reachable"] is True
    assert report["canvas"]["current_user"] == {"id": 42, "name": "Instructor"}
    assert report["issues"] == []


def test_auth_doctor_is_useful_offline_without_api_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DANVAS_TEST_CANVAS_TOKEN", "must-not-read")

    command_auth_doctor(
        doctor_args(
            api_url=None,
            api_url_source=None,
            origin_binding_source=None,
            origin_binding_status="unconfigured",
        )
    )

    output = capsys.readouterr().out
    assert "API URL: unconfigured" in output
    assert "Credential status: not_checked" in output
    assert "status: ok" in output
    assert os.environ["DANVAS_TEST_CANVAS_TOKEN"] == "must-not-read"


def test_auth_doctor_check_canvas_requires_api_url() -> None:
    report = build_auth_doctor_report(
        doctor_args(
            api_url=None,
            api_url_source=None,
            origin_binding_source=None,
            origin_binding_status="unconfigured",
            check_canvas=True,
        )
    )

    assert report["canvas"]["reachable"] is False
    assert "canvas API URL is unconfigured" in report["issues"]


@pytest.mark.parametrize("status", ["conflict", "unbound"])
def test_auth_doctor_origin_issue_does_not_read_credential(
    status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DANVAS_TEST_CANVAS_TOKEN", "must-not-read")

    report = build_auth_doctor_report(
        doctor_args(
            origin_binding_status=status,
            origin_binding_source=None,
            origin_binding_error="safe origin diagnostic",
            check_canvas=True,
        )
    )

    assert report["credential"]["status"] == "not_checked"
    assert report["issues"] == [f"canvas origin is {status}"]
    assert os.environ["DANVAS_TEST_CANVAS_TOKEN"] == "must-not-read"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "missing"),
        ("", "invalid"),
        ("line-one\nline-two", "invalid"),
    ],
)
def test_auth_doctor_classifies_environment_failures(
    value: str | None, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if value is None:
        monkeypatch.delenv("DANVAS_TEST_CANVAS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DANVAS_TEST_CANVAS_TOKEN", value)

    report = build_auth_doctor_report(doctor_args())

    assert report["credential"]["status"] == expected
    assert report["issues"] == [f"canvas credential input is {expected}"]


def test_auth_doctor_redacts_file_locator_and_reports_permission_warning(
    tmp_path: Path,
) -> None:
    credential = tmp_path / "highly-identifying-secret-path"
    credential.write_text("token\n", encoding="utf-8")
    credential.chmod(0o644)

    report = build_auth_doctor_report(
        doctor_args(
            credential_input=credential_input(CredentialKind.FILE, str(credential))
        )
    )

    assert report["credential"]["locator"] == "configured credential file"
    assert report["credential"]["status"] == "resolved"
    assert report["credential"]["warnings"]
    assert str(credential) not in repr(report)


def test_auth_doctor_classifies_unreadable_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing-token"

    report = build_auth_doctor_report(
        doctor_args(credential_input=credential_input(CredentialKind.FILE, str(missing)))
    )

    assert report["credential"]["status"] == "unreadable"
    assert str(missing) not in repr(report)


def test_auth_doctor_exits_nonzero_when_credential_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DANVAS_TEST_CANVAS_TOKEN", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        command_auth_doctor(doctor_args(json=True))

    assert excinfo.value.code == 1
