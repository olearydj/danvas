from __future__ import annotations

from types import SimpleNamespace

import pytest

from danvas.mutation import (
    MutationMode,
    assert_canvas_mutation_allowed,
    mutation_mode_from_args,
    resolve_mutation_mode,
)


@pytest.mark.parametrize(
    ("dry_run", "apply", "expected"),
    [
        (False, False, MutationMode.PLAN),
        (True, False, MutationMode.PLAN),
        (False, True, MutationMode.APPLY),
    ],
)
def test_resolve_mutation_mode(
    dry_run: bool,
    apply: bool,
    expected: MutationMode,
) -> None:
    assert (
        resolve_mutation_mode(
            dry_run=dry_run,
            apply=apply,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("dry_run", "apply"),
    [(True, True)],
)
def test_resolve_mutation_mode_rejects_conflicts(
    dry_run: bool,
    apply: bool,
) -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_mutation_mode(
            dry_run=dry_run,
            apply=apply,
        )


def test_normalized_mode_outranks_compatibility_dry_run() -> None:
    args = SimpleNamespace(mutation_mode="plan", dry_run=False)

    assert mutation_mode_from_args(args) is MutationMode.PLAN
    with pytest.raises(RuntimeError, match="mode is 'plan'"):
        assert_canvas_mutation_allowed(args, "example command")


def test_direct_caller_compatibility_is_fail_closed_when_dry_run_is_missing() -> None:
    assert mutation_mode_from_args(SimpleNamespace()) is MutationMode.PLAN
    assert mutation_mode_from_args(SimpleNamespace(dry_run=False)) is MutationMode.APPLY


def test_pre_write_assertion_accepts_only_apply() -> None:
    assert_canvas_mutation_allowed(MutationMode.APPLY, "example command")
    with pytest.raises(RuntimeError, match="Canvas mutation blocked"):
        assert_canvas_mutation_allowed(MutationMode.PLAN, "example command")
