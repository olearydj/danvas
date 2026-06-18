"""Canvas authentication helpers."""

from __future__ import annotations

from typing import Any

from canvasapi import Canvas
from secretpath import SecretPathError, resolve_named_secret

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

    return result.as_tuple()


def canvas_from_args(args: Any) -> Canvas:
    api_key, provider_name = resolve_api_key(
        provider=args.secret_provider,
        op_reference=args.op_reference,
        env_var=args.api_key_env,
    )
    print(f"Using API key from: {provider_name}")
    return Canvas(args.api_url, api_key)
