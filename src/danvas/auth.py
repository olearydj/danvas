"""Canvas authentication helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from canvasapi import Canvas

DEFAULT_API_URL = "https://auburn.instructure.com/"


def resolve_api_key(*, provider: str, op_reference: str, env_var: str) -> tuple[str, str]:
    attempts = []
    if provider in {"auto", "1password"}:
        if op_reference and shutil.which("op"):
            result = subprocess.run(
                ["op", "read", op_reference],
                capture_output=True,
                text=True,
                check=False,
            )
            token = result.stdout.strip()
            if result.returncode == 0 and token:
                return token, "1password"
            attempts.append(f"1password: {result.stderr.strip() or 'empty token'}")
        else:
            attempts.append("1password: unavailable")
    if provider in {"auto", "env"}:
        token = (os.environ.get(env_var) or "").strip()
        if token:
            return token, f"env:{env_var}"
        attempts.append(f"env:{env_var}: unavailable")
    raise SystemExit(f"Could not resolve Canvas API key. Tried: {'; '.join(attempts)}")


def canvas_from_args(args: Any) -> Canvas:
    api_key, provider_name = resolve_api_key(
        provider=args.secret_provider,
        op_reference=args.op_reference,
        env_var=args.api_key_env,
    )
    print(f"Using API key from: {provider_name}")
    return Canvas(args.api_url, api_key)
