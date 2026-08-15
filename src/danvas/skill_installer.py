"""Bounded, provenance-aware installer for the embedded danvas Agent Skill."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from danvas import __version__
from danvas.skill_resources import SKILL_NAME, SkillResourceFile, canonical_skill_files

PROVENANCE_NAME: Final = ".danvas-install.json"
PROVENANCE_SCHEMA: Final = "danvas-skill-install-v1"
PROVENANCE_LIMIT: Final = 64 * 1024
SKILL_FILE_LIMIT: Final = 1024 * 1024
SKILL_TOTAL_LIMIT: Final = 4 * 1024 * 1024
FaultHook = Callable[[str], None]


class AgentTarget(StrEnum):
    SHARED = "shared"
    CODEX = "codex"
    CLAUDE_CODE = "claude-code"
    GEMINI = "gemini"
    COPILOT = "copilot"


class SkillScope(StrEnum):
    USER = "user"
    PROJECT = "project"


class InstallState(StrEnum):
    ABSENT = "absent"
    EXACT = "exact"
    OWNED_STALE = "owned_stale"
    OWNED_MODIFIED = "owned_modified"
    UNOWNED = "unowned"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class ResolvedSkillTarget:
    agent: AgentTarget
    scope: SkillScope
    base: Path
    skills_root: Path
    path: Path


@dataclass(frozen=True)
class SkillInspection:
    target: ResolvedSkillTarget
    state: InstallState
    reason: str
    differences: tuple[str, ...] = ()
    installed_version: str | None = None


@dataclass(frozen=True)
class SkillInstallResult:
    inspection: SkillInspection
    action: str
    changed: bool


@dataclass(frozen=True)
class SkillDoctorReport:
    executable: str | None
    executable_version: str | None
    executable_matches: bool
    inspections: tuple[SkillInspection, ...]


class SkillInstallRefused(RuntimeError):
    def __init__(self, inspection: SkillInspection):
        self.inspection = inspection
        super().__init__(inspection.reason)


_USER_ROOTS: Mapping[AgentTarget, PurePosixPath] = {
    AgentTarget.SHARED: PurePosixPath(".agents/skills"),
    AgentTarget.CODEX: PurePosixPath(".agents/skills"),
    AgentTarget.CLAUDE_CODE: PurePosixPath(".claude/skills"),
    AgentTarget.GEMINI: PurePosixPath(".gemini/skills"),
    AgentTarget.COPILOT: PurePosixPath(".copilot/skills"),
}
_PROJECT_ROOTS: Mapping[AgentTarget, PurePosixPath] = {
    AgentTarget.SHARED: PurePosixPath(".agents/skills"),
    AgentTarget.CODEX: PurePosixPath(".agents/skills"),
    AgentTarget.CLAUDE_CODE: PurePosixPath(".claude/skills"),
    AgentTarget.GEMINI: PurePosixPath(".gemini/skills"),
    AgentTarget.COPILOT: PurePosixPath(".github/skills"),
}


def resolve_skill_target(
    *,
    agent: AgentTarget,
    scope: SkillScope,
    home: Path | None = None,
    project_root: Path | None = None,
) -> ResolvedSkillTarget:
    if scope is SkillScope.USER:
        base = (home or Path.home()).absolute()
        relative = _USER_ROOTS[agent]
    else:
        if project_root is None:
            raise ValueError("Project-scope skill installation requires --project-root.")
        base = project_root.absolute()
        relative = _PROJECT_ROOTS[agent]
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe configured skill root for {agent.value}: {relative}")
    skills_root = base.joinpath(*relative.parts)
    target = skills_root / SKILL_NAME
    if not target.is_relative_to(base):
        raise ValueError(f"Skill target escapes its selected {scope.value} root.")
    return ResolvedSkillTarget(agent, scope, base, skills_root, target)


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _unsafe_reason(target: ResolvedSkillTarget) -> str | None:
    base_stat = _lstat(target.base)
    if base_stat is None:
        return f"Selected {target.scope.value} root does not exist: {target.base}"
    if stat.S_ISLNK(base_stat.st_mode) or not stat.S_ISDIR(base_stat.st_mode):
        return f"Selected {target.scope.value} root is not a real directory: {target.base}"
    relative = target.path.relative_to(target.base)
    current = target.base
    for index, part in enumerate(relative.parts):
        current /= part
        current_stat = _lstat(current)
        if current_stat is None:
            continue
        if stat.S_ISLNK(current_stat.st_mode):
            return f"Skill target contains a symlink component: {current}"
        is_target = index == len(relative.parts) - 1
        if not stat.S_ISDIR(current_stat.st_mode):
            noun = "target" if is_target else "parent"
            return f"Skill {noun} is not a directory: {current}"
    return None


def _resource_hashes(resources: tuple[SkillResourceFile, ...]) -> dict[str, str]:
    return {resource.relative_path.as_posix(): resource.sha256 for resource in resources}


def _read_regular_file(path: Path, *, limit: int) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"Installed skill file cannot be opened safely: {path}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"Installed skill path is not a regular file: {path}")
        if opened.st_size > limit:
            raise ValueError(f"Installed skill file exceeds the {limit}-byte limit: {path}")
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"Installed skill file exceeds the {limit}-byte limit: {path}")
    return content


def _provenance_payload(
    target: ResolvedSkillTarget, resources: tuple[SkillResourceFile, ...]
) -> dict[str, object]:
    return {
        "schema": PROVENANCE_SCHEMA,
        "skill": SKILL_NAME,
        "distribution": "danvas-cli",
        "danvas_version": __version__,
        "agent": target.agent.value,
        "scope": target.scope.value,
        "files": _resource_hashes(resources),
    }


def _read_provenance(path: Path) -> dict[str, object] | None:
    provenance = path / PROVENANCE_NAME
    provenance_stat = _lstat(provenance)
    if provenance_stat is None:
        return None
    if stat.S_ISLNK(provenance_stat.st_mode) or not stat.S_ISREG(provenance_stat.st_mode):
        raise ValueError(f"Provenance is not a regular file: {provenance}")
    if provenance_stat.st_size > PROVENANCE_LIMIT:
        return None
    try:
        payload = json.loads(_read_regular_file(provenance, limit=PROVENANCE_LIMIT))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _declared_hashes(payload: Mapping[str, object]) -> dict[str, str] | None:
    files = payload.get("files")
    if not isinstance(files, dict):
        return None
    declared: dict[str, str] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            return None
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name == PROVENANCE_NAME:
            return None
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            return None
        declared[name] = digest
    return declared


def _inventory_tree(root: Path) -> tuple[dict[str, str], set[str]]:
    file_hashes: dict[str, str] = {}
    directories: set[str] = set()
    total_size = 0

    def visit(directory: Path, relative: PurePosixPath) -> None:
        nonlocal total_size
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            child_relative = relative / entry.name
            if entry.is_symlink():
                raise ValueError(f"Installed skill contains a symlink: {child_relative}")
            if entry.is_dir(follow_symlinks=False):
                directories.add(child_relative.as_posix())
                visit(Path(entry.path), child_relative)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(f"Installed skill contains a non-regular file: {child_relative}")
            if entry.name == PROVENANCE_NAME and relative == PurePosixPath():
                continue
            content = _read_regular_file(Path(entry.path), limit=SKILL_FILE_LIMIT)
            total_size += len(content)
            if total_size > SKILL_TOTAL_LIMIT:
                raise ValueError(
                    f"Installed skill exceeds the {SKILL_TOTAL_LIMIT}-byte total limit."
                )
            digest = SkillResourceFile(child_relative, content).sha256
            file_hashes[child_relative.as_posix()] = digest

    visit(root, PurePosixPath())
    return file_hashes, directories


def _expected_directories(file_names: set[str]) -> set[str]:
    directories: set[str] = set()
    for name in file_names:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def inspect_skill_target(
    target: ResolvedSkillTarget,
    *,
    resources: tuple[SkillResourceFile, ...] | None = None,
) -> SkillInspection:
    unsafe = _unsafe_reason(target)
    if unsafe:
        return SkillInspection(target, InstallState.UNSAFE, unsafe)
    target_stat = _lstat(target.path)
    if target_stat is None:
        return SkillInspection(target, InstallState.ABSENT, "No skill is installed at this target.")
    try:
        provenance = _read_provenance(target.path)
    except ValueError as exc:
        return SkillInspection(target, InstallState.UNSAFE, str(exc))
    if provenance is None:
        return SkillInspection(
            target,
            InstallState.UNOWNED,
            "Target exists without valid danvas installer provenance; refusing to replace it.",
        )
    if (
        provenance.get("schema") != PROVENANCE_SCHEMA
        or provenance.get("skill") != SKILL_NAME
        or provenance.get("distribution") != "danvas-cli"
    ):
        return SkillInspection(
            target,
            InstallState.UNOWNED,
            "Target provenance is not owned by this danvas installer.",
        )
    declared = _declared_hashes(provenance)
    if declared is None:
        return SkillInspection(
            target,
            InstallState.UNOWNED,
            "Target provenance has an invalid or unsafe file manifest.",
        )
    try:
        actual, directories = _inventory_tree(target.path)
    except (OSError, ValueError) as exc:
        return SkillInspection(target, InstallState.UNSAFE, str(exc))
    expected_directories = _expected_directories(set(declared))
    differences = tuple(
        [
            *(
                f"file differs: {name}"
                for name in sorted(set(actual) & set(declared))
                if actual[name] != declared[name]
            ),
            *(f"file missing: {name}" for name in sorted(set(declared) - set(actual))),
            *(f"unexpected file: {name}" for name in sorted(set(actual) - set(declared))),
            *(
                f"unexpected directory: {name}"
                for name in sorted(directories - expected_directories)
            ),
        ]
    )
    installed_version = provenance.get("danvas_version")
    version = installed_version if isinstance(installed_version, str) else None
    if differences:
        return SkillInspection(
            target,
            InstallState.OWNED_MODIFIED,
            "Danvas-owned target has local modifications; refusing to replace it.",
            differences,
            version,
        )
    current_resources = resources or canonical_skill_files()
    current_hashes = _resource_hashes(current_resources)
    if declared == current_hashes and version == __version__:
        return SkillInspection(
            target,
            InstallState.EXACT,
            "Installed skill exactly matches this danvas version.",
            installed_version=version,
        )
    stale_differences = tuple(
        [
            *(
                f"bundled file changed: {name}"
                for name in sorted(set(declared) & set(current_hashes))
                if declared[name] != current_hashes[name]
            ),
            *(
                f"bundled file added: {name}"
                for name in sorted(set(current_hashes) - set(declared))
            ),
            *(
                f"bundled file removed: {name}"
                for name in sorted(set(declared) - set(current_hashes))
            ),
        ]
    )
    return SkillInspection(
        target,
        InstallState.OWNED_STALE,
        "Unmodified danvas-owned skill differs from the bundled version and can be updated.",
        stale_differences,
        version,
    )


def _ensure_directory_chain(target: ResolvedSkillTarget) -> None:
    current = target.base
    for part in target.skills_root.relative_to(target.base).parts:
        current /= part
        current_stat = _lstat(current)
        if current_stat is None:
            with suppress(FileExistsError):
                current.mkdir(mode=0o755)
            current_stat = _lstat(current)
        if (
            current_stat is None
            or stat.S_ISLNK(current_stat.st_mode)
            or not stat.S_ISDIR(current_stat.st_mode)
        ):
            raise RuntimeError(f"Unsafe skill parent appeared during installation: {current}")


def _write_staging_tree(
    staging: Path,
    target: ResolvedSkillTarget,
    resources: tuple[SkillResourceFile, ...],
    fault_hook: FaultHook | None,
) -> None:
    for resource in resources:
        relative = resource.relative_path
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Bundled skill path is unsafe: {relative}")
        destination = staging.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(resource.content)
            handle.flush()
            os.fsync(handle.fileno())
        if fault_hook:
            fault_hook(f"after_file:{relative.as_posix()}")
    provenance = staging / PROVENANCE_NAME
    payload = (
        json.dumps(
            _provenance_payload(target, resources),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with provenance.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if fault_hook:
        fault_hook(f"after_file:{PROVENANCE_NAME}")


def _call_rename(function_name: str, source: Path, destination: Path, flags: int) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if function_name == "renameat2":
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source_bytes, -100, destination_bytes, flags)
    else:
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source_bytes, destination_bytes, flags)
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)


def _rename_noreplace(source: Path, destination: Path) -> None:
    if sys.platform.startswith("linux"):
        _call_rename("renameat2", source, destination, 1)
        return
    if sys.platform == "darwin":
        _call_rename("renamex_np", source, destination, 4)
        return
    raise RuntimeError("Atomic skill installation is supported only on Linux and macOS.")


def _exchange(source: Path, destination: Path) -> None:
    if sys.platform.startswith("linux"):
        _call_rename("renameat2", source, destination, 2)
        return
    if sys.platform == "darwin":
        _call_rename("renamex_np", source, destination, 2)
        return
    raise RuntimeError("Atomic skill updates are supported only on Linux and macOS.")


def _commit_absent(staging: Path, target: ResolvedSkillTarget) -> None:
    try:
        _rename_noreplace(staging, target.path)
    except FileExistsError as exc:
        raise SkillInstallRefused(
            SkillInspection(
                target,
                InstallState.UNSAFE,
                "Skill target appeared during installation; refusing to overwrite it.",
            )
        ) from exc


def _commit_stale_update(
    staging: Path,
    target: ResolvedSkillTarget,
    bundled: tuple[SkillResourceFile, ...],
    fault_hook: FaultHook | None,
) -> None:
    current = inspect_skill_target(target, resources=bundled)
    if current.state is not InstallState.OWNED_STALE:
        raise SkillInstallRefused(
            SkillInspection(
                target,
                InstallState.UNSAFE,
                "Skill target changed after staging; refusing the update race.",
            )
        )
    if fault_hook:
        fault_hook("before_update_exchange")
    _exchange(staging, target.path)
    displaced = ResolvedSkillTarget(
        target.agent,
        target.scope,
        target.base,
        target.skills_root,
        staging,
    )
    if inspect_skill_target(displaced, resources=bundled).state is not InstallState.OWNED_STALE:
        _exchange(staging, target.path)
        raise SkillInstallRefused(
            SkillInspection(
                target,
                InstallState.UNSAFE,
                "Skill target changed during the atomic update; the conflicting target was restored.",
            )
        )


def install_skill(
    target: ResolvedSkillTarget,
    *,
    dry_run: bool = False,
    resources: tuple[SkillResourceFile, ...] | None = None,
    fault_hook: FaultHook | None = None,
) -> SkillInstallResult:
    bundled = resources or canonical_skill_files()
    inspection = inspect_skill_target(target, resources=bundled)
    if inspection.state is InstallState.EXACT:
        return SkillInstallResult(inspection, "already installed", False)
    if inspection.state not in {InstallState.ABSENT, InstallState.OWNED_STALE}:
        raise SkillInstallRefused(inspection)
    action = "create" if inspection.state is InstallState.ABSENT else "update"
    if dry_run:
        return SkillInstallResult(inspection, f"would {action}", False)

    _ensure_directory_chain(target)
    after_parents = inspect_skill_target(target, resources=bundled)
    if after_parents.state is not inspection.state:
        raise SkillInstallRefused(
            SkillInspection(
                target,
                InstallState.UNSAFE,
                "Skill target changed after preflight; refusing the installation race.",
            )
        )
    staging = Path(tempfile.mkdtemp(prefix=".danvas-skill-staging-", dir=target.skills_root))
    committed = False
    try:
        if fault_hook:
            fault_hook("after_staging_created")
        _write_staging_tree(staging, target, bundled, fault_hook)
        staged_files, staged_directories = _inventory_tree(staging)
        expected_hashes = _resource_hashes(bundled)
        if staged_files != expected_hashes or staged_directories != _expected_directories(
            set(expected_hashes)
        ):
            raise RuntimeError("Staged skill failed its content validation.")
        if fault_hook:
            fault_hook("before_commit")
        if inspection.state is InstallState.ABSENT:
            _commit_absent(staging, target)
        else:
            _commit_stale_update(staging, target, bundled, fault_hook)
        committed = True
        if fault_hook:
            fault_hook("after_commit")
    finally:
        if staging.exists():
            with suppress(OSError):
                shutil.rmtree(staging)
    if not committed:
        raise RuntimeError("Skill installation did not reach its atomic commit.")
    final = inspect_skill_target(target, resources=bundled)
    if final.state is not InstallState.EXACT:
        raise RuntimeError(f"Installed skill failed final validation: {final.state.value}")
    return SkillInstallResult(final, "created" if action == "create" else "updated", True)


def _executable_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    prefix = "danvas "
    output = result.stdout.strip()
    return output.removeprefix(prefix) if output.startswith(prefix) else None


def skill_doctor(
    *,
    agent: AgentTarget | None = None,
    home: Path | None = None,
    project_root: Path,
    which: Callable[[str], str | None] = shutil.which,
    version_reader: Callable[[str], str | None] = _executable_version,
) -> SkillDoctorReport:
    agents = (agent,) if agent is not None else tuple(AgentTarget)
    inspections = tuple(
        inspect_skill_target(
            resolve_skill_target(
                agent=selected,
                scope=scope,
                home=home,
                project_root=project_root,
            )
        )
        for selected in agents
        for scope in (SkillScope.USER, SkillScope.PROJECT)
    )
    executable = which("danvas")
    executable_version = version_reader(executable) if executable else None
    return SkillDoctorReport(
        executable=executable,
        executable_version=executable_version,
        executable_matches=executable_version == __version__,
        inspections=inspections,
    )


def install_action(inspection: SkillInspection) -> str:
    agent = inspection.target.agent.value
    scope = inspection.target.scope.value
    command = f"danvas skill install --agent {agent} --scope {scope}"
    if inspection.target.scope is SkillScope.PROJECT:
        command += f" --project-root {inspection.target.base}"
    if inspection.state in {InstallState.ABSENT, InstallState.OWNED_STALE}:
        return command
    if inspection.state is InstallState.EXACT:
        return "none"
    return "inspect or move the conflicting target aside, then rerun the install command"


def render_install_result(
    result: SkillInstallResult, resources: tuple[SkillResourceFile, ...]
) -> str:
    inspection = result.inspection
    lines = [
        f"Target: {inspection.target.path}",
        f"Agent: {inspection.target.agent.value}",
        f"Scope: {inspection.target.scope.value}",
        f"State: {inspection.state.value}",
        f"Version: {__version__}",
        f"Action: {result.action}",
        "Files:",
    ]
    if inspection.installed_version is not None:
        lines.insert(5, f"Installed version: {inspection.installed_version}")
    lines.extend(f"  {resource.relative_path}  sha256:{resource.sha256}" for resource in resources)
    lines.extend(f"Difference: {difference}" for difference in inspection.differences)
    return "\n".join(lines) + "\n"


def render_doctor(report: SkillDoctorReport) -> str:
    lines = ["Danvas skill doctor"]
    if report.executable is None:
        lines.extend(
            ("Executable: missing", "Executable repair: install the danvas-cli distribution")
        )
    else:
        lines.extend(
            (
                f"Executable: {report.executable}",
                f"Executable version: {report.executable_version or 'unreadable'}",
                f"Executable matches: {str(report.executable_matches).lower()}",
            )
        )
    for inspection in report.inspections:
        lines.extend(
            (
                "",
                f"{inspection.target.agent.value} {inspection.target.scope.value}",
                f"  Target: {inspection.target.path}",
                f"  State: {inspection.state.value}",
                f"  Detail: {inspection.reason}",
            )
        )
        lines.extend(f"  Difference: {difference}" for difference in inspection.differences)
        lines.append(f"  Repair: {install_action(inspection)}")
    return "\n".join(lines) + "\n"
