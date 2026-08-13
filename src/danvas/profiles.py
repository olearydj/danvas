"""User-level Canvas instance profiles and precedence resolution."""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_path as platform_user_config_path

from danvas.project_config import load_project_config
from danvas.timezones import require_timezone

PROFILE_KEYS = {
    "api_url",
    "timezone",
    "secret_name",
    "secret_provider",
    "op_reference",
    "api_key_env",
}
USER_CONFIG_KEYS = {"default_profile", "profiles"}
FORBIDDEN_SECRET_KEYS = {"api_key", "token", "access_token", "credential"}
SECRET_PROVIDERS = {"auto", "1password", "env"}


@dataclass(frozen=True)
class CanvasProfile:
    """Non-secret defaults for one Canvas instance."""

    name: str
    api_url: str | None = None
    timezone: str | None = None
    secret_name: str | None = None
    secret_provider: str | None = None
    op_reference: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class UserProfiles:
    """Parsed user configuration and its source path."""

    path: Path
    default_profile: str | None
    profiles: dict[str, CanvasProfile]


@dataclass(frozen=True)
class CanvasContext:
    """Fully resolved non-secret Canvas connection settings."""

    profile: str | None
    profile_timezone: str | None
    api_url: str | None
    api_url_source: str | None
    secret_name: str
    secret_provider: str
    op_reference: str
    api_key_env: str
    user_config_path: Path


def user_config_path() -> Path:
    """Return the platform-standard danvas user configuration file."""
    return platform_user_config_path("danvas", appauthor=False) / "config.toml"


def load_user_profiles(path: Path | None = None) -> UserProfiles:
    """Load and validate user-level profiles without resolving credentials."""
    source = path or user_config_path()
    if not source.is_file():
        return UserProfiles(path=source, default_profile=None, profiles={})
    try:
        data = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"Could not read danvas user config {source}: {exc}") from exc

    forbidden = sorted(FORBIDDEN_SECRET_KEYS.intersection(data))
    if forbidden:
        raise SystemExit(
            f"Danvas user config {source} cannot store secret values: {', '.join(forbidden)}"
        )
    unknown = sorted(set(data).difference(USER_CONFIG_KEYS))
    if unknown:
        raise SystemExit(f"Unknown keys in danvas user config {source}: {', '.join(unknown)}")

    default_profile = data.get("default_profile")
    if default_profile is not None and not isinstance(default_profile, str):
        raise SystemExit(f"default_profile must be a string in {source}")
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, dict):
        raise SystemExit(f"profiles must be a TOML table in {source}")

    profiles = {
        str(name): _parse_profile(str(name), raw, source)
        for name, raw in raw_profiles.items()
    }
    if default_profile and default_profile not in profiles:
        raise SystemExit(
            f"Default danvas profile {default_profile!r} is not defined in {source}"
        )
    return UserProfiles(path=source, default_profile=default_profile, profiles=profiles)


def resolve_canvas_context(
    *,
    explicit_profile: str | None = None,
    explicit_api_url: str | None = None,
    explicit_secret_name: str | None = None,
    explicit_secret_provider: str | None = None,
    explicit_op_reference: str | None = None,
    explicit_api_key_env: str | None = None,
    start: Path | None = None,
    allow_missing_api_url: bool = False,
    environ: Mapping[str, str] | None = None,
    profiles_path: Path | None = None,
) -> CanvasContext:
    """Resolve profile, instance, and credential references with stable precedence."""
    environment = environ if environ is not None else os.environ
    project = load_project_config(start)
    canvas = project.get("canvas") or {}
    if not isinstance(canvas, dict):
        raise SystemExit("[canvas] in .danvas/config.toml must be a TOML table.")
    user_profiles = load_user_profiles(profiles_path)

    project_profile = _optional_string(canvas.get("profile"))
    profile_name = (
        _optional_string(explicit_profile)
        or project_profile
        or _optional_string(environment.get("DANVAS_PROFILE"))
        or user_profiles.default_profile
    )
    profile = None
    if profile_name:
        profile = user_profiles.profiles.get(profile_name)
        if profile is None:
            raise SystemExit(
                f"Danvas profile {profile_name!r} is not defined in {user_profiles.path}."
            )

    project_api_url = _optional_string(canvas.get("api_url"))
    if explicit_api_url:
        api_url = explicit_api_url
        api_url_source = "--api-url"
    elif project_api_url:
        api_url = project_api_url
        api_url_source = ".danvas/config.toml"
    elif profile and profile.api_url:
        api_url = profile.api_url
        api_url_source = f"profile {profile.name!r}"
    else:
        api_url = _optional_string(environment.get("CANVAS_API_URL"))
        api_url_source = "CANVAS_API_URL" if api_url else None

    if (
        explicit_profile
        and project_api_url
        and profile
        and profile.api_url
        and _normalized_api_url(project_api_url) != _normalized_api_url(profile.api_url)
    ):
        print(
            f"WARNING: explicitly selected profile {profile.name!r} is configured for "
            f"{profile.api_url}, but this project is pinned to {project_api_url}. "
            "The project URL keeps precedence; verify that the selected credentials belong "
            "to this Canvas instance.",
            file=sys.stderr,
        )

    if not api_url and not allow_missing_api_url:
        raise SystemExit(
            "Canvas API URL required. Pass --api-url, initialize the course project, "
            "select a configured --profile, or set CANVAS_API_URL. "
            f"User profiles: {user_profiles.path}"
        )

    secret_name = (
        _optional_string(explicit_secret_name)
        or (profile.secret_name if profile else None)
        or "canvas"
    )
    secret_provider = (
        _optional_string(explicit_secret_provider)
        or (profile.secret_provider if profile else None)
        or _optional_string(environment.get("CANVAS_SECRET_PROVIDER"))
        or "auto"
    )
    if secret_provider not in SECRET_PROVIDERS:
        raise SystemExit(f"Unknown Canvas secret provider: {secret_provider}")
    op_reference = (
        _optional_string(explicit_op_reference)
        or (profile.op_reference if profile else None)
        or _optional_string(environment.get("CANVAS_API_KEY_OP_REFERENCE"))
        or ""
    )
    api_key_env = (
        _optional_string(explicit_api_key_env)
        or (profile.api_key_env if profile else None)
        or _optional_string(environment.get("CANVAS_API_KEY_ENV"))
        or "CANVAS_API_KEY"
    )

    return CanvasContext(
        profile=profile_name,
        profile_timezone=profile.timezone if profile else None,
        api_url=api_url,
        api_url_source=api_url_source,
        secret_name=secret_name,
        secret_provider=secret_provider,
        op_reference=op_reference,
        api_key_env=api_key_env,
        user_config_path=user_profiles.path,
    )


def _parse_profile(name: str, raw: Any, source: Path) -> CanvasProfile:
    if not isinstance(raw, dict):
        raise SystemExit(f"Profile {name!r} must be a TOML table in {source}")
    forbidden = sorted(FORBIDDEN_SECRET_KEYS.intersection(raw))
    if forbidden:
        raise SystemExit(
            f"Profile {name!r} in {source} cannot store secret values: {', '.join(forbidden)}"
        )
    unknown = sorted(set(raw).difference(PROFILE_KEYS))
    if unknown:
        raise SystemExit(
            f"Unknown keys in profile {name!r} in {source}: {', '.join(unknown)}"
        )
    values = {key: _optional_string(raw.get(key)) for key in PROFILE_KEYS}
    provider = values["secret_provider"]
    if provider and provider not in SECRET_PROVIDERS:
        raise SystemExit(f"Unknown secret_provider in profile {name!r}: {provider}")
    timezone = values["timezone"]
    if timezone:
        timezone = require_timezone(timezone, source=f"profile {name!r} in {source}")
    return CanvasProfile(
        name=name,
        api_url=values["api_url"],
        timezone=timezone,
        secret_name=values["secret_name"],
        secret_provider=provider,
        op_reference=values["op_reference"],
        api_key_env=values["api_key_env"],
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_api_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()
