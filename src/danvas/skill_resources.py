"""Access the canonical version-matched danvas Agent Skill package resource."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from typing import Final

from danvas import __version__

SKILL_NAME: Final = "danvas"


@dataclass(frozen=True)
class SkillResourceFile:
    relative_path: PurePosixPath
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def canonical_skill_root() -> Traversable:
    return files("danvas._skill").joinpath(SKILL_NAME)


def _walk(root: Traversable, relative: PurePosixPath | None = None) -> list[SkillResourceFile]:
    found: list[SkillResourceFile] = []
    current = relative or PurePosixPath()
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        child_relative = current / child.name
        if child.is_dir():
            found.extend(_walk(child, child_relative))
        elif child.is_file():
            found.append(SkillResourceFile(child_relative, child.read_bytes()))
    return found


def canonical_skill_files() -> tuple[SkillResourceFile, ...]:
    return tuple(_walk(canonical_skill_root()))


def render_skill_show() -> str:
    resources = canonical_skill_files()
    main = next(resource for resource in resources if resource.relative_path.name == "SKILL.md")
    lines = [
        f"Bundled Agent Skill: {SKILL_NAME}",
        f"Danvas CLI version: {__version__}",
        "Supported targets: shared, codex, claude-code, gemini, copilot",
        "Supported scopes: user, project",
        "Files:",
    ]
    lines.extend(f"  {resource.relative_path}  sha256:{resource.sha256}" for resource in resources)
    lines.extend(("", "SKILL.md", "--------", main.content.decode("utf-8").rstrip(), ""))
    return "\n".join(lines)
