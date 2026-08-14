"""Canvas authentication helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canvasapi import Canvas

from danvas.credentials import (
    CredentialInput,
    CredentialKind,
    CredentialResolutionError,
    ResolvedCredential,
    resolve_credential,
)
from danvas.sanitize import sanitize_error

AUTH_DOCTOR_SCHEMA = "danvas-auth-doctor-v1"


def canvas_from_args(args: Any) -> Canvas:
    api_url = getattr(args, "api_url", None)
    if not api_url:
        raise SystemExit(
            "Canvas API URL required before resolving credentials. Pass --api-url, "
            "initialize the course project, select a configured --profile, or set "
            "CANVAS_API_URL."
        )
    credential = resolve_canvas_credential(args)
    announce_canvas_credential(credential)
    return Canvas(api_url, credential.value)


def resolve_canvas_credential(args: Any) -> ResolvedCredential:
    """Resolve the shared Canvas/Panopto credential boundary."""
    if not getattr(args, "api_url", None):
        raise SystemExit(
            "Canvas API URL required before resolving credentials. Pass --api-url, "
            "initialize the course project, select a configured --profile, or set "
            "CANVAS_API_URL."
        )
    credential_input = getattr(args, "credential_input", None)
    if not isinstance(credential_input, CredentialInput):
        raise SystemExit("Canvas credential input was not resolved.")
    return resolve_credential(
        credential_input,
        project_root=_optional_path(getattr(args, "credential_project_root", None)),
    )


def announce_canvas_credential(credential: ResolvedCredential) -> None:
    """Report only the transport danvas directly observed."""
    source = (
        "environment"
        if credential.source_kind is CredentialKind.ENVIRONMENT
        else "credential file"
    )
    print(f"Using Canvas credential from: {source}")


def command_auth_doctor(args: Any) -> None:
    payload = build_auth_doctor_report(args)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_auth_doctor_report(payload)
    if payload["issues"]:
        raise SystemExit(1)


def build_auth_doctor_report(args: Any) -> dict[str, Any]:
    """Build the versioned provider-neutral boundary diagnostic."""
    api_url = getattr(args, "api_url", None)
    origin_status = getattr(
        args,
        "origin_binding_status",
        "bound" if api_url else "unconfigured",
    )
    check_canvas = bool(getattr(args, "check_canvas", False))
    credential_input = getattr(args, "credential_input", None)
    credential_report: dict[str, Any] = {
        "kind": credential_input.kind.value
        if isinstance(credential_input, CredentialInput)
        else None,
        "selection_source": credential_input.selection_source.value
        if isinstance(credential_input, CredentialInput)
        else None,
        "locator": _doctor_locator(credential_input),
        "status": "not_checked",
        "warnings": [],
        "error": "",
    }
    canvas_report: dict[str, Any] = {
        "checked": check_canvas,
        "reachable": None,
        "current_user": None,
        "error": "",
    }
    payload: dict[str, Any] = {
        "schema": AUTH_DOCTOR_SCHEMA,
        "profile": getattr(args, "profile", None),
        "origin": {
            "status": origin_status,
            "api_url": api_url,
            "source": getattr(args, "api_url_source", None),
            "binding_source": getattr(args, "origin_binding_source", None),
            "error": getattr(args, "origin_binding_error", ""),
        },
        "credential": credential_report,
        "canvas": canvas_report,
        "issues": [],
    }

    if origin_status in {"conflict", "unbound"}:
        payload["issues"].append(f"canvas origin is {origin_status}")
        canvas_report["reachable"] = False if check_canvas else None
        if check_canvas:
            canvas_report["error"] = (
                "Canvas API check skipped because the origin is not safely bound."
            )
        return payload

    if origin_status == "unconfigured":
        if check_canvas:
            canvas_report["reachable"] = False
            canvas_report["error"] = (
                "Canvas API check skipped because the Canvas API URL is unconfigured."
            )
            payload["issues"].append("canvas API URL is unconfigured")
        return payload

    if not isinstance(credential_input, CredentialInput):
        credential_report["status"] = "invalid"
        credential_report["error"] = "Canvas credential input was not resolved."
        payload["issues"].append("canvas credential input is invalid")
        if check_canvas:
            canvas_report["reachable"] = False
            canvas_report["error"] = (
                "Canvas API check skipped because the credential input is invalid."
            )
        return payload

    try:
        resolved = resolve_credential(
            credential_input,
            project_root=_optional_path(
                getattr(args, "credential_project_root", None)
            ),
            emit_warnings=False,
        )
    except CredentialResolutionError as exc:
        credential_report["status"] = exc.reason.value
        credential_report["error"] = str(exc)
        payload["issues"].append(
            f"canvas credential input is {exc.reason.value}"
        )
        if check_canvas:
            canvas_report["reachable"] = False
            canvas_report["error"] = (
                "Canvas API check skipped because the credential input did not resolve."
            )
        return payload

    credential_report["status"] = "resolved"
    credential_report["warnings"] = list(resolved.warnings)
    if check_canvas:
        try:
            canvas = Canvas(api_url, resolved.value)
            user = canvas.get_current_user()
        except Exception as exc:
            canvas_report["reachable"] = False
            canvas_report["error"] = safe_auth_error(exc)
            payload["issues"].append("canvas API check failed")
        else:
            canvas_report["reachable"] = True
            canvas_report["current_user"] = {
                "id": getattr(user, "id", None),
                "name": getattr(user, "name", None)
                or getattr(user, "sortable_name", None)
                or "",
            }
    return payload


def print_auth_doctor_report(payload: dict[str, Any]) -> None:
    """Render the neutral diagnostic without provider or secret details."""
    print("Auth doctor")
    print(f"Schema: {payload['schema']}")
    if payload.get("profile"):
        print(f"Profile: {payload['profile']}")
    origin = payload["origin"]
    print(f"API URL: {origin['api_url'] or 'unconfigured'}")
    print(f"Origin binding: {origin['status']}")
    if origin["binding_source"]:
        print(f"Origin binding source: {origin['binding_source']}")
    if origin["error"]:
        print(f"Origin error: {origin['error']}")

    credential = payload["credential"]
    print(f"Credential transport: {credential['kind'] or 'unconfigured'}")
    if credential["selection_source"]:
        print(f"Credential selection: {credential['selection_source']}")
    if credential["locator"]:
        print(f"Credential locator: {credential['locator']}")
    print(f"Credential status: {credential['status']}")
    for warning in credential["warnings"]:
        print(f"Credential warning: {warning}")
    if credential["error"]:
        print(f"Credential error: {credential['error']}")

    canvas = payload["canvas"]
    if canvas["checked"]:
        status = "reachable" if canvas["reachable"] else "failed"
        print(f"Canvas API: {status}")
        if canvas["current_user"]:
            user = canvas["current_user"]
            print(f"  user: {user.get('name') or user.get('id') or 'unknown'}")
        if canvas["error"]:
            print(f"  error: {canvas['error']}")
    else:
        print("Canvas API: not checked")
    if payload["issues"]:
        print("issues:")
        for issue in payload["issues"]:
            print(f"  - {issue}")
    else:
        print("status: ok")


def safe_auth_error(error: Exception) -> str:
    """Compatibility export for the shared public error sanitizer."""
    return sanitize_error(error)


def _doctor_locator(credential_input: object) -> str | None:
    if not isinstance(credential_input, CredentialInput):
        return None
    if credential_input.kind is CredentialKind.ENVIRONMENT:
        return credential_input.locator
    return "configured credential file"


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return Path(value)
    raise TypeError("credential project root must be path-like")
