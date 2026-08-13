"""Typed artifact policy and creation-time private filesystem helpers."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO

from danvas import __version__
from danvas.project_config import find_config_dir

PRIVATE_DIR_NAME = "private"
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
ARTIFACT_SCHEMA_VERSION = 1


class ArtifactClass(StrEnum):
    SHAREABLE = "shareable"
    COURSE_INTERNAL = "course_internal"
    PRIVATE = "private"


@dataclass(frozen=True)
class ArtifactPolicy:
    command: str
    artifact_class: ArtifactClass
    default_relative: str | None = None


@dataclass(frozen=True)
class ResolvedPrivatePath:
    path: Path
    private_root: Path | None
    used_project_default: bool
    outside_project_private_root: bool


def _policies() -> tuple[ArtifactPolicy, ...]:
    course_internal = (
        "init",
        "refresh",
        "status",
        "reports list",
        "reports latest",
        "courses",
        "assignments export",
        "assignments create",
        "assignments verify",
        "assignments update",
        "assignments upsert",
        "assignments audit",
        "quiz import-qti",
        "discussions create",
        "discussions verify",
        "discussions update",
        "discussions sync-prompts",
        "sources lint",
        "pages export",
        "pages sync",
        "pages render",
        "pages create",
        "pages update",
        "pages verify",
        "announcements latest",
        "announcements sync",
        "announcements update",
        "announcements verify",
        "files inventory",
        "files download",
        "files download-one",
        "files compare",
        "files upload",
    )
    private = (
        "roster",
        "assignments overrides",
        "assignments overrides-sync",
        "gradebook check",
        "gradebook audit",
        "quiz analysis",
        "submissions export",
        "submissions grades",
        "submissions media",
        "submissions feedback",
        "grades post",
        "grades clear",
        "grades comments",
        "grades verify",
        "discussions export",
        "discussions score",
        "announcements export",
        "recordings panopto-captions",
    )
    return tuple(
        [ArtifactPolicy(command, ArtifactClass.COURSE_INTERNAL) for command in course_internal]
        + [ArtifactPolicy(command, ArtifactClass.PRIVATE) for command in private]
    )


ARTIFACT_POLICIES: Mapping[str, ArtifactPolicy] = {policy.command: policy for policy in _policies()}


def artifact_policy(command: str) -> ArtifactPolicy:
    try:
        return ARTIFACT_POLICIES[command]
    except KeyError as exc:
        raise ValueError(f"No artifact policy declared for command: {command}") from exc


def require_private_platform() -> None:
    if os.name != "posix":
        raise SystemExit(
            "Private artifact output is supported only on POSIX platforms where "
            "danvas can enforce mode 0700 directories and mode 0600 files."
        )


def project_private_root(project_root: Path | None = None) -> Path | None:
    config_dir = find_config_dir(project_root)
    return config_dir / PRIVATE_DIR_NAME if config_dir else None


def resolve_private_path(
    *,
    explicit: str | Path | None,
    project_root: Path | None,
    default_relative: str | Path,
    option_name: str,
) -> ResolvedPrivatePath:
    """Resolve a private destination without creating files or touching Canvas."""
    require_private_platform()
    root = project_private_root(project_root)
    if explicit is not None:
        path = Path(explicit)
        outside = root is not None and not _is_relative_to(path, root)
        return ResolvedPrivatePath(
            path=path,
            private_root=root,
            used_project_default=False,
            outside_project_private_root=outside,
        )

    if root is None:
        raise SystemExit(
            "No .danvas project found for private output. "
            f"Pass {option_name} with an explicit private destination."
        )
    relative = Path(default_relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Private default must be a contained relative path: {relative}")
    path = root / relative
    _reject_symlinks_below(root, path)
    if not _is_relative_to(path, root):
        raise ValueError(f"Private default escapes .danvas/private: {relative}")
    return ResolvedPrivatePath(
        path=path,
        private_root=root,
        used_project_default=True,
        outside_project_private_root=False,
    )


def warn_if_external_private_path(resolved: ResolvedPrivatePath) -> None:
    if resolved.outside_project_private_root:
        print(
            "WARNING: private artifact destination is outside this project's "
            ".danvas/private directory; danvas will protect the artifact itself but will not "
            "change unrelated ancestor permissions.",
            file=sys.stderr,
        )


def ensure_private_directory(
    path: Path,
    *,
    exist_ok: bool = True,
    tighten_existing: bool = False,
) -> Path:
    """Create a private directory tree without a permissive creation window."""
    require_private_platform()
    path = path.absolute()
    if path.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {path}")
    if path.exists():
        if not path.is_dir():
            raise NotADirectoryError(path)
        if not exist_ok:
            raise FileExistsError(path)
        mode = stat.S_IMODE(path.stat().st_mode)
        if tighten_existing:
            path.chmod(PRIVATE_DIRECTORY_MODE)
        elif mode & 0o077:
            raise SystemExit(
                f"Private output directory allows group/other access: {path}. "
                "Choose a private directory or restrict it to mode 0700."
            )
        return path

    missing: list[Path] = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise SystemExit(f"Refusing private artifact symlink: {current}")
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    if current.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {current}")
    for directory in reversed(missing):
        os.mkdir(directory, PRIVATE_DIRECTORY_MODE)
        directory.chmod(PRIVATE_DIRECTORY_MODE)
    return path


def ensure_private_parent(path: Path) -> Path:
    """Create missing artifact parents privately without chmodding existing ancestors."""
    parent = path.absolute().parent
    if parent.exists():
        if parent.is_symlink():
            raise SystemExit(f"Refusing private artifact symlink: {parent}")
        if not parent.is_dir():
            raise NotADirectoryError(parent)
        return parent
    return ensure_private_directory(parent)


def write_private_bytes(path: Path, data: bytes, *, overwrite: bool = False) -> Path:
    return _write_private(path, overwrite=overwrite, writer=lambda handle: handle.write(data))


def write_private_text(path: Path, text: str, *, overwrite: bool = False) -> Path:
    return write_private_bytes(path, text.encode("utf-8"), overwrite=overwrite)


def write_private_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    command: str,
    overwrite: bool = False,
    classify: bool = True,
) -> Path:
    body = dict(payload)
    if classify:
        body.setdefault("artifact_schema_version", ARTIFACT_SCHEMA_VERSION)
        body.setdefault("artifact_class", ArtifactClass.PRIVATE.value)
        body.setdefault("command", command)
    text = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
    return write_private_text(path, text, overwrite=overwrite)


def write_private_rows(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
    *,
    command: str,
    overwrite: bool = False,
    sidecar_path: Path | None = None,
    sidecar_fields: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return write_private_pair(
        path,
        stream.getvalue().encode("utf-8"),
        command=command,
        overwrite=overwrite,
        sidecar_path=sidecar_path,
        sidecar_fields=sidecar_fields,
    )


def write_private_pair(
    path: Path,
    data: bytes,
    *,
    command: str,
    overwrite: bool = False,
    sidecar_path: Path | None = None,
    sidecar_fields: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write data then integrity metadata; a torn pair is always detectable."""
    require_private_platform()
    sidecar = sidecar_path or path.with_name(f"{path.name}.artifact.json")
    ensure_private_parent(path)
    ensure_private_parent(sidecar)
    if path.absolute().parent != sidecar.absolute().parent:
        raise ValueError("Private data and sidecar must share a directory.")
    _preflight_target(path, overwrite=overwrite)
    _preflight_target(sidecar, overwrite=overwrite)

    data_temp = _stage_bytes(path, data)
    return commit_private_staged_pair(
        data_temp,
        path,
        command=command,
        overwrite=overwrite,
        sidecar_path=sidecar,
        sidecar_fields=sidecar_fields,
    )


def commit_private_staged_pair(
    staged: Path,
    path: Path,
    *,
    command: str,
    overwrite: bool = False,
    sidecar_path: Path | None = None,
    sidecar_fields: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Commit an owned 0600 staged file followed by its integrity sidecar."""
    sidecar = sidecar_path or path.with_name(f"{path.name}.artifact.json")
    if staged.absolute() in {path.absolute(), sidecar.absolute()}:
        raise ValueError("Private staging path must differ from final targets.")
    sidecar_temp: Path | None = None
    data_committed = False
    try:
        ensure_private_parent(path)
        ensure_private_parent(sidecar)
        if path.absolute().parent != sidecar.absolute().parent:
            raise ValueError("Private data and sidecar must share a directory.")
        _preflight_target(path, overwrite=overwrite)
        _preflight_target(sidecar, overwrite=overwrite)
        if staged.is_symlink() or not staged.is_file():
            raise SystemExit(f"Private staged artifact is not a regular file: {staged}")
        if stat.S_IMODE(staged.stat().st_mode) & 0o077:
            raise SystemExit(f"Private staged artifact has unsafe permissions: {staged}")

        metadata = {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_class": ArtifactClass.PRIVATE.value,
            "command": command,
        }
        metadata.update(dict(sidecar_fields or {}))
        metadata["sha256"] = private_file_sha256(staged)
        sidecar_data = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode()
        sidecar_temp = _stage_bytes(sidecar, sidecar_data)
        _commit_staged(staged, path, overwrite=overwrite)
        data_committed = True
        _commit_staged(sidecar_temp, sidecar, overwrite=overwrite)
    except BaseException:
        _unlink_owned(staged)
        if sidecar_temp is not None:
            _unlink_owned(sidecar_temp)
        if data_committed and not overwrite:
            _unlink_owned(path)
        raise
    return path, sidecar


@contextmanager
def private_staged_file(path: Path):
    """Open an exact private staging path exclusively and remove it on handled failure."""
    require_private_platform()
    ensure_private_parent(path)
    if path.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    except FileExistsError:
        raise FileExistsError(path) from None
    completed = False
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        completed = True
    finally:
        if not completed:
            _unlink_owned(path)


def private_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_private_sidecar(path: Path, sidecar: Path | None = None) -> bool:
    metadata_path = sidecar or path.with_name(f"{path.name}.artifact.json")
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    try:
        return (
            isinstance(payload, dict)
            and payload.get("artifact_class") == ArtifactClass.PRIVATE.value
            and payload.get("sha256") == private_file_sha256(path)
        )
    except OSError:
        return False


def _write_private(
    path: Path,
    *,
    overwrite: bool,
    writer: Callable[[BinaryIO], object],
) -> Path:
    require_private_platform()
    ensure_private_parent(path)
    _preflight_target(path, overwrite=overwrite)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        _commit_staged(temporary, path, overwrite=overwrite)
    finally:
        _unlink_owned(temporary)
    return path


def _stage_bytes(path: Path, data: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        _unlink_owned(temporary)
        raise
    return temporary


def _preflight_target(path: Path, *, overwrite: bool) -> None:
    if path.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    if path.exists() and not path.is_file():
        raise SystemExit(f"Private artifact target is not a regular file: {path}")


def _commit_staged(temporary: Path, path: Path, *, overwrite: bool) -> None:
    if overwrite:
        _preflight_target(path, overwrite=True)
        os.replace(temporary, path)
    else:
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            raise FileExistsError(path) from None
        temporary.unlink()
    path.chmod(PRIVATE_FILE_MODE)
    _fsync_directory(path.parent)


def _unlink_owned(path: Path) -> None:
    with suppress(FileNotFoundError):
        path.unlink()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _reject_symlinks_below(root: Path, path: Path) -> None:
    if root.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {root}")
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError(f"Private path escapes its managed root: {path}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise SystemExit(f"Refusing private artifact symlink: {current}")


def artifact_metadata(*, command: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_class": ArtifactClass.PRIVATE.value,
        "command": command,
        "danvas_version": __version__,
        "files": files,
    }
