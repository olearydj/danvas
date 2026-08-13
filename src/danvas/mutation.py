"""Shared plan/apply boundary for Canvas mutations."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

DRY_RUN_HELP = "Plan without changing Canvas (also the default)."
APPLY_HELP = "Apply the planned change to Canvas."


class MutationMode(StrEnum):
    PLAN = "plan"
    APPLY = "apply"


def resolve_mutation_mode(
    *,
    dry_run: bool,
    apply: bool,
    legacy_live: bool = False,
) -> MutationMode:
    """Resolve raw CLI flags once, rejecting ambiguous authorization."""
    if dry_run and apply:
        raise ValueError("--dry-run and --apply cannot be combined.")
    if legacy_live and dry_run:
        raise ValueError("--live and --dry-run cannot be combined.")
    if legacy_live and apply:
        raise ValueError("--live and --apply cannot be combined.")
    return MutationMode.APPLY if apply or legacy_live else MutationMode.PLAN


def mutation_mode_from_args(args: Any) -> MutationMode:
    """Read a normalized mode, with a compatibility path for direct callers."""
    raw_mode = getattr(args, "mutation_mode", None)
    if raw_mode is not None:
        try:
            return MutationMode(raw_mode)
        except ValueError as exc:
            raise RuntimeError(f"Invalid normalized mutation mode: {raw_mode!r}") from exc
    return MutationMode.PLAN if bool(getattr(args, "dry_run", True)) else MutationMode.APPLY


def assert_canvas_mutation_allowed(mode_or_args: MutationMode | Any, command: str) -> None:
    """Fail closed immediately before a Canvas write primitive is reached."""
    mode = (
        mode_or_args
        if isinstance(mode_or_args, MutationMode)
        else mutation_mode_from_args(mode_or_args)
    )
    if mode is not MutationMode.APPLY:
        raise RuntimeError(f"Canvas mutation blocked for {command}: mode is {mode.value!r}.")
