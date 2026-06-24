"""Canvas authentication helpers."""

from __future__ import annotations

import json
from typing import Any

from canvasapi import Canvas
from secretpath import SecretMiss, SecretPathError, doctor_report, resolve_named_secret

DEFAULT_API_URL = "https://auburn.instructure.com/"


def resolve_api_key(*, provider: str, op_reference: str, env_var: str) -> tuple[str, str]:
    try:
        result = resolve_named_secret(
            "canvas",
            display_name="Canvas API key",
            provider=provider,
            op_reference=op_reference,
            env_var=env_var,
        )
    except SecretPathError as error:
        raise SystemExit(str(error)) from error

    if isinstance(result, SecretMiss):
        raise SystemExit("Could not resolve Canvas API key.")
    return result.as_tuple()


def canvas_from_args(args: Any) -> Canvas:
    api_key, provider_name = resolve_api_key(
        provider=args.secret_provider,
        op_reference=args.op_reference,
        env_var=args.api_key_env,
    )
    print(f"Using API key from: {provider_name}")
    return Canvas(args.api_url, api_key)


def command_auth_doctor(args: Any) -> None:
    payload = build_auth_doctor_report(args)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_auth_doctor_report(payload)
    if payload["issues"]:
        raise SystemExit(1)


def build_auth_doctor_report(args: Any) -> dict[str, Any]:
    canvas_report: dict[str, Any] = {
        "checked": bool(getattr(args, "check_canvas", False)),
        "reachable": None,
        "current_user": None,
        "error": "",
    }
    payload: dict[str, Any] = {
        "api_url": args.api_url,
        "secretpath": doctor_report(check_resolution=False),
        "canvas": canvas_report,
        "issues": [],
    }
    payload["issues"].extend(payload["secretpath"].get("issues") or [])
    try:
        resolved = resolve_named_secret(
            "canvas",
            display_name="Canvas API key",
            provider=args.secret_provider,
            op_reference=args.op_reference,
            env_var=args.api_key_env,
            required=False,
            cache=False,
        )
    except SecretPathError as exc:
        payload["secretpath"]["resolutions"] = [
            {"name": "canvas", "resolved": False, "error": str(exc)}
        ]
        resolved = None
    else:
        if isinstance(resolved, SecretMiss):
            payload["secretpath"]["resolutions"] = [
                {
                    "name": "canvas",
                    "resolved": False,
                    "attempts": [
                        {"provider": attempt.provider, "status": attempt.status}
                        for attempt in resolved.attempts
                    ],
                }
            ]
        else:
            payload["secretpath"]["resolutions"] = [
                {"name": "canvas", "resolved": True, "source": resolved.source}
            ]

    if isinstance(resolved, SecretMiss) or resolved is None:
        payload["issues"].append("canvas secret is unresolved")

    if getattr(args, "check_canvas", False):
        if isinstance(resolved, SecretMiss) or resolved is None:
            payload["canvas"]["reachable"] = False
            payload["canvas"]["error"] = "Canvas API check skipped because the canvas secret is unresolved."
        else:
            try:
                canvas = Canvas(args.api_url, resolved.value)
                user = canvas.get_current_user()
            except Exception as exc:
                payload["canvas"]["reachable"] = False
                payload["canvas"]["error"] = safe_auth_error(exc)
                payload["issues"].append("canvas API check failed")
            else:
                payload["canvas"]["reachable"] = True
                payload["canvas"]["provider"] = resolved.source
                payload["canvas"]["current_user"] = {
                    "id": getattr(user, "id", None),
                    "name": getattr(user, "name", None)
                    or getattr(user, "sortable_name", None)
                    or "",
                }
    return payload


def print_auth_doctor_report(payload: dict[str, Any]) -> None:
    secretpath = payload["secretpath"]
    print("Auth doctor")
    print(f"API URL: {payload['api_url']}")
    print(f"op: {'available' if secretpath['op']['available'] else 'not found'}")
    print(f"direnv: {'available' if secretpath['direnv']['available'] else 'not found'}")
    print("secretpath config files:")
    if secretpath["config_files"]:
        for report in secretpath["config_files"]:
            suffix = " (permissions too broad)" if report["too_broad"] else ""
            print(f"  - {report['path']}{suffix}")
    else:
        print("  - none")
    print("secretpath resolutions:")
    if secretpath["resolutions"]:
        for report in secretpath["resolutions"]:
            if report["resolved"]:
                print(f"  - {report['name']}: resolved from {report['source']}")
            else:
                print(f"  - {report['name']}: unresolved")
    else:
        print("  - none")
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
    text = " ".join(str(error).split())
    for marker in ("token=", "verifier=", "access_token="):
        if marker in text:
            text = text.split(marker, 1)[0] + marker + "[redacted]"
    return text
