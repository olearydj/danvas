"""Provider-neutral Canvas credential selection and bounded input readers."""

from __future__ import annotations

import os
import re
import stat
import sys
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MAX_CREDENTIAL_BYTES = 16 * 1024
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class CredentialKind(StrEnum):
    """Supported provider-neutral input transports."""

    ENVIRONMENT = "environment"
    FILE = "file"


class SelectionSource(StrEnum):
    """Configuration layer that selected a credential locator."""

    CLI = "cli"
    USER_PROFILE = "user_profile"
    PROCESS = "process"
    DEFAULT = "default"


class CredentialErrorReason(StrEnum):
    """Stable diagnostic classifications for credential-read failures."""

    MISSING = "missing"
    UNREADABLE = "unreadable"
    INVALID = "invalid"


class CredentialResolutionError(SystemExit):
    """Credential failure with a safe diagnostic classification."""

    def __init__(self, message: str, *, reason: CredentialErrorReason) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CredentialInput:
    """A validated, non-secret locator for one Canvas credential."""

    kind: CredentialKind
    locator: str
    selection_source: SelectionSource


@dataclass(frozen=True, repr=False)
class ResolvedCredential:
    """A Canvas credential and the transport danvas directly consumed."""

    value: str
    source_kind: CredentialKind
    warnings: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return (
            "ResolvedCredential(value=[redacted], "
            f"source_kind={self.source_kind.value!r})"
        )


def select_credential_input(
    *,
    explicit_env: str | None = None,
    explicit_file: str | Path | None = None,
    profile_env: str | None = None,
    profile_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> CredentialInput:
    """Select one credential locator with deterministic, validated precedence."""
    environment = os.environ if environ is None else environ
    _reject_blank_selector(explicit_env, source="--api-key-env")
    _reject_blank_selector(explicit_file, source="--api-key-file")
    _reject_blank_selector(profile_env, source="profile api_key_env")
    _reject_blank_selector(profile_file, source="profile api_key_file")
    if "CANVAS_API_KEY_ENV" in environment:
        _reject_blank_selector(
            environment.get("CANVAS_API_KEY_ENV"), source="CANVAS_API_KEY_ENV"
        )
    if "CANVAS_API_KEY_FILE" in environment:
        _reject_blank_selector(
            environment.get("CANVAS_API_KEY_FILE"), source="CANVAS_API_KEY_FILE"
        )
    process_env = _optional_text(environment.get("CANVAS_API_KEY_ENV"))
    process_file = _optional_text(environment.get("CANVAS_API_KEY_FILE"))

    layers = (
        (SelectionSource.CLI, _optional_text(explicit_env), _optional_text(explicit_file)),
        (
            SelectionSource.USER_PROFILE,
            _optional_text(profile_env),
            _optional_text(profile_file),
        ),
        (SelectionSource.PROCESS, process_env, process_file),
    )
    for source, env_name, file_path in layers:
        _reject_selector_conflict(source, env_name=env_name, file_path=file_path)

    for source, env_name, file_path in layers:
        if env_name:
            return CredentialInput(
                kind=CredentialKind.ENVIRONMENT,
                locator=require_environment_name(env_name, source=source.value),
                selection_source=source,
            )
        if file_path:
            return CredentialInput(
                kind=CredentialKind.FILE,
                locator=str(require_absolute_file_path(file_path, source=source.value)),
                selection_source=source,
            )
    return CredentialInput(
        kind=CredentialKind.ENVIRONMENT,
        locator="CANVAS_API_KEY",
        selection_source=SelectionSource.DEFAULT,
    )


def resolve_credential(
    credential_input: CredentialInput,
    *,
    project_root: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
    emit_warnings: bool = True,
) -> ResolvedCredential:
    """Read exactly one selected input and return a redacting result."""
    if credential_input.kind is CredentialKind.ENVIRONMENT:
        return resolve_environment_credential(credential_input, environ=environ)
    return resolve_file_credential(
        credential_input,
        project_root=project_root,
        emit_warnings=emit_warnings,
    )


def resolve_environment_credential(
    credential_input: CredentialInput,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> ResolvedCredential:
    """Read and remove one explicitly selected environment value."""
    if credential_input.kind is not CredentialKind.ENVIRONMENT:
        raise ValueError("Environment resolver requires an environment input.")
    environment = os.environ if environ is None else environ
    name = require_environment_name(credential_input.locator, source="credential input")
    try:
        value = environment.pop(name)
    except KeyError as exc:
        raise CredentialResolutionError(
            f"Canvas credential environment variable {name} is not set.",
            reason=CredentialErrorReason.MISSING,
        ) from exc
    _validate_credential_text(value, source="environment variable")
    return ResolvedCredential(value=value, source_kind=CredentialKind.ENVIRONMENT)


def resolve_file_credential(
    credential_input: CredentialInput,
    *,
    project_root: Path | None = None,
    emit_warnings: bool = True,
) -> ResolvedCredential:
    """Read one bounded regular file through a single opened descriptor."""
    if credential_input.kind is not CredentialKind.FILE:
        raise ValueError("File resolver requires a file input.")
    path = require_absolute_file_path(credential_input.locator, source="credential input")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CredentialResolutionError(
            "Could not open the selected Canvas credential file.",
            reason=CredentialErrorReason.UNREADABLE,
        ) from exc

    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise CredentialResolutionError(
                "The selected Canvas credential file is not a regular file.",
                reason=CredentialErrorReason.INVALID,
            )
        _reject_project_contained_file(path, opened=opened, project_root=project_root)
        content = _read_bounded(descriptor)
        warning = _broad_permissions_warning(opened)
        if warning and emit_warnings:
            print(warning, file=sys.stderr)
    finally:
        os.close(descriptor)

    value = _decode_file_value(content)
    return ResolvedCredential(
        value=value,
        source_kind=CredentialKind.FILE,
        warnings=(warning,) if warning else (),
    )


def require_environment_name(value: str, *, source: str) -> str:
    """Validate one portable environment-variable identifier."""
    if not ENVIRONMENT_NAME.fullmatch(value):
        raise SystemExit(
            f"Invalid Canvas credential environment-variable name from {source}. "
            "Use letters, digits, and underscores, beginning with a letter or underscore."
        )
    return value


def require_absolute_file_path(value: str | Path, *, source: str) -> Path:
    """Require a stable absolute credential-file locator."""
    path = Path(value)
    if not path.is_absolute():
        raise SystemExit(f"Canvas credential file path from {source} must be absolute.")
    return path


def _reject_selector_conflict(
    source: SelectionSource, *, env_name: str | None, file_path: str | None
) -> None:
    if env_name and file_path:
        label = {
            SelectionSource.CLI: "command line",
            SelectionSource.USER_PROFILE: "selected user profile",
            SelectionSource.PROCESS: "process environment",
        }[source]
        raise SystemExit(
            f"Conflicting Canvas credential selectors in the {label}: choose an "
            "environment variable or a credential file, not both."
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reject_blank_selector(value: object, *, source: str) -> None:
    if value is not None and not str(value).strip():
        raise SystemExit(f"Canvas credential selector {source} cannot be empty.")


def _validate_credential_text(value: str, *, source: str) -> None:
    if not value:
        raise CredentialResolutionError(
            f"The selected Canvas credential {source} is empty.",
            reason=CredentialErrorReason.INVALID,
        )
    if "\0" in value:
        raise CredentialResolutionError(
            f"The selected Canvas credential {source} contains a NUL byte.",
            reason=CredentialErrorReason.INVALID,
        )
    if "\n" in value or "\r" in value:
        raise CredentialResolutionError(
            f"The selected Canvas credential {source} contains multiple lines.",
            reason=CredentialErrorReason.INVALID,
        )


def _read_bounded(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_CREDENTIAL_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > MAX_CREDENTIAL_BYTES:
        raise CredentialResolutionError(
            f"The selected Canvas credential file exceeds {MAX_CREDENTIAL_BYTES} bytes.",
            reason=CredentialErrorReason.INVALID,
        )
    return content


def _decode_file_value(content: bytes) -> str:
    if content.endswith(b"\r\n"):
        content = content[:-2]
    elif content.endswith(b"\n"):
        content = content[:-1]
    try:
        value = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialResolutionError(
            "The selected Canvas credential file is not valid UTF-8.",
            reason=CredentialErrorReason.INVALID,
        ) from exc
    _validate_credential_text(value, source="file")
    return value


def _reject_project_contained_file(
    path: Path, *, opened: os.stat_result, project_root: Path | None
) -> None:
    if project_root is None:
        return
    try:
        resolved = path.resolve(strict=True)
        current = resolved.stat()
    except OSError as exc:
        raise CredentialResolutionError(
            "Could not verify the selected Canvas credential file after opening it.",
            reason=CredentialErrorReason.INVALID,
        ) from exc
    if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
        raise CredentialResolutionError(
            "The selected Canvas credential file changed while it was opened.",
            reason=CredentialErrorReason.INVALID,
        )
    root = project_root.resolve()
    if resolved == root or root in resolved.parents:
        raise CredentialResolutionError(
            "Canvas credential files cannot be stored inside the active course project. "
            "Use a user-controlled config directory or a platform secret mount.",
            reason=CredentialErrorReason.INVALID,
        )


def _broad_permissions_warning(opened: os.stat_result) -> str | None:
    if os.name != "posix" or opened.st_mode & 0o077 == 0:
        return None
    owner = getattr(opened, "st_uid", None)
    if hasattr(os, "getuid") and owner not in {None, os.getuid()}:
        return None
    return (
        "WARNING: the selected Canvas credential file is readable by group or other "
        "users; consider mode 0600 where the deployment model permits it."
    )
