"""User-level Canvas instance profiles and precedence resolution."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from platformdirs import user_config_path as platform_user_config_path

from danvas.credentials import (
    CredentialInput,
    require_environment_name,
    select_credential_input,
)
from danvas.project_config import find_config_dir, load_project_config
from danvas.timezones import require_timezone

PROFILE_KEYS = {
    "api_url",
    "timezone",
    "api_key_env",
    "api_key_file",
}
RETIRED_PROFILE_KEYS = {"secret_name", "secret_provider", "op_reference"}
RETIRED_ENVIRONMENT_CONTROLS = {
    "CANVAS_SECRET_PROVIDER",
    "CANVAS_API_KEY_OP_REFERENCE",
}
USER_CONFIG_KEYS = {"default_profile", "profiles"}
FORBIDDEN_SECRET_KEYS = {"api_key", "token", "access_token", "credential"}
PROJECT_CREDENTIAL_KEYS = {
    "access_token",
    "api_key",
    "api_key_env",
    "api_key_file",
    "credential",
    "credential_command",
    "op_reference",
    "resolver_command",
    "secret_name",
    "secret_provider",
    "token",
}


@dataclass(frozen=True)
class CanvasProfile:
    """Non-secret defaults for one Canvas instance."""

    name: str
    api_url: str | None = None
    timezone: str | None = None
    api_key_env: str | None = None
    api_key_file: str | None = None


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
    origin_binding_source: str | None
    origin_binding_status: str
    origin_binding_error: str
    project_root: Path | None
    credential_input: CredentialInput
    user_config_path: Path


class OriginBindingError(SystemExit):
    """Origin authorization failure that auth doctor may report safely."""

    def __init__(self, message: str, *, status: str) -> None:
        super().__init__(message)
        self.status = status


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
    explicit_api_key_env: str | None = None,
    explicit_api_key_file: str | Path | None = None,
    start: Path | None = None,
    allow_missing_api_url: bool = False,
    allow_origin_issues: bool = False,
    environ: Mapping[str, str] | None = None,
    profiles_path: Path | None = None,
) -> CanvasContext:
    """Resolve profile, instance, and credential references with stable precedence."""
    environment = environ if environ is not None else os.environ
    project = load_project_config(start)
    canvas = project.get("canvas") or {}
    if not isinstance(canvas, dict):
        raise SystemExit("[canvas] in .danvas/config.toml must be a TOML table.")
    forbidden_project_keys = sorted(PROJECT_CREDENTIAL_KEYS.intersection(canvas))
    if forbidden_project_keys:
        key = forbidden_project_keys[0]
        raise SystemExit(
            f"Course project configuration cannot select Canvas credentials: "
            f"[canvas].{key}. Configure the locator in a user profile or external "
            "process environment instead."
        )
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

    if not api_url and not allow_missing_api_url:
        raise SystemExit(
            "Canvas API URL required. Pass --api-url, initialize the course project, "
            "select a configured --profile, or set CANVAS_API_URL. "
            f"User profiles: {user_profiles.path}"
        )

    retired_controls = sorted(RETIRED_ENVIRONMENT_CONTROLS.intersection(environment))
    if retired_controls:
        raise SystemExit(
            "Removed Canvas credential environment controls are set: "
            f"{', '.join(retired_controls)}. Use CANVAS_API_KEY_ENV or "
            "CANVAS_API_KEY_FILE to select a provider-neutral input, and run the "
            "external secret provider before danvas."
        )

    origin_binding_source: str | None = None
    origin_binding_status = "unconfigured"
    origin_binding_error = ""
    if api_url:
        try:
            origin_binding_source = _require_origin_binding(
                api_url=api_url,
                api_url_source=api_url_source,
                profile=profile,
                explicit_api_url=explicit_api_url,
                environment_api_url=_optional_string(environment.get("CANVAS_API_URL")),
            )
        except OriginBindingError as exc:
            if not allow_origin_issues:
                raise
            origin_binding_status = exc.status
            origin_binding_error = str(exc)
        else:
            origin_binding_status = "bound"

    credential_input = select_credential_input(
        explicit_env=explicit_api_key_env,
        explicit_file=explicit_api_key_file,
        profile_env=profile.api_key_env if profile else None,
        profile_file=profile.api_key_file if profile else None,
        environ=environment,
    )
    config_dir = find_config_dir(start)

    return CanvasContext(
        profile=profile_name,
        profile_timezone=profile.timezone if profile else None,
        api_url=api_url,
        api_url_source=api_url_source,
        origin_binding_source=origin_binding_source,
        origin_binding_status=origin_binding_status,
        origin_binding_error=origin_binding_error,
        project_root=config_dir.parent if config_dir else None,
        credential_input=credential_input,
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
    retired = sorted(RETIRED_PROFILE_KEYS.intersection(raw))
    if retired:
        raise SystemExit(
            f"Profile {name!r} in {source} uses removed provider-specific keys: "
            f"{', '.join(retired)}. Replace them with exactly one of api_key_env "
            "or api_key_file, and run any secret provider outside danvas."
        )
    unknown = sorted(set(raw).difference(PROFILE_KEYS))
    if unknown:
        raise SystemExit(
            f"Unknown keys in profile {name!r} in {source}: {', '.join(unknown)}"
        )
    for key in ("api_key_env", "api_key_file"):
        if key in raw and (not isinstance(raw[key], str) or not raw[key].strip()):
            raise SystemExit(f"{key} in profile {name!r} in {source} must be a string.")
    values = {key: _optional_string(raw.get(key)) for key in PROFILE_KEYS}
    timezone = values["timezone"]
    if timezone:
        timezone = require_timezone(timezone, source=f"profile {name!r} in {source}")
    api_key_file = values["api_key_file"]
    if values["api_key_env"]:
        require_environment_name(
            values["api_key_env"], source=f"profile {name!r} in {source}"
        )
    if values["api_key_env"] and api_key_file:
        raise SystemExit(
            f"Profile {name!r} in {source} selects both api_key_env and api_key_file; "
            "choose one Canvas credential transport."
        )
    if api_key_file and not Path(api_key_file).is_absolute():
        raise SystemExit(
            f"api_key_file in profile {name!r} in {source} must be an absolute path."
        )
    return CanvasProfile(
        name=name,
        api_url=values["api_url"],
        timezone=timezone,
        api_key_env=values["api_key_env"],
        api_key_file=api_key_file,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_api_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit("Canvas API URL contains an invalid port.") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit(
            "Canvas API URL must be an HTTPS URL without credentials, query, or fragment."
        )
    effective_port = port or 443
    path = parsed.path.rstrip("/")
    return f"https://{parsed.hostname.casefold()}:{effective_port}{path}"


def _require_origin_binding(
    *,
    api_url: str | None,
    api_url_source: str | None,
    profile: CanvasProfile | None,
    explicit_api_url: str | None,
    environment_api_url: str | None,
) -> str | None:
    if api_url is None:
        return None
    effective = _normalized_api_url(api_url)
    if profile and profile.api_url:
        if _normalized_api_url(profile.api_url) != effective:
            raise OriginBindingError(
                f"Canvas origin conflict: profile {profile.name!r} is configured for "
                f"{profile.api_url}, but the effective API URL is {api_url}. Refusing "
                "to read credentials. Select a matching profile or correct the API URL.",
                status="conflict",
            )
        return f"profile {profile.name!r}"
    if explicit_api_url and _normalized_api_url(explicit_api_url) == effective:
        return "--api-url"
    if environment_api_url and _normalized_api_url(environment_api_url) == effective:
        return "CANVAS_API_URL"
    raise OriginBindingError(
        f"Canvas origin {api_url} is not bound to user intent. The effective URL came "
        f"from {api_url_source or 'configuration'}, but course projects cannot authorize "
        "where credentials are sent. Select a matching user profile, pass the same origin "
        "with --api-url, or set CANVAS_API_URL to the same origin.",
        status="unbound",
    )
