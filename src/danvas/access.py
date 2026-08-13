"""Typed command access policy for Canvas and retained local effects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class DryRunKind(StrEnum):
    NONE = "none"
    CANVAS_MUTATION = "canvas_mutation"
    LOCAL_WRITE = "local_write"


@dataclass(frozen=True)
class CommandAccessPolicy:
    command: str
    canvas_read: bool = False
    local_write: bool = False
    canvas_mutation: bool = False
    dry_run_kind: DryRunKind = DryRunKind.NONE
    bare_canvas_mutation: bool = False
    destructive: bool = False
    grade_affecting: bool = False
    notification_or_visibility: bool = False
    authoritative_verification: bool = False

    def __post_init__(self) -> None:
        if self.canvas_mutation and not self.canvas_read:
            raise ValueError(f"Canvas mutation policy must also declare Canvas read: {self.command}")
        if self.bare_canvas_mutation and not self.canvas_mutation:
            raise ValueError(f"Bare mutation requires Canvas mutation: {self.command}")
        if self.dry_run_kind is DryRunKind.CANVAS_MUTATION and not self.canvas_mutation:
            raise ValueError(f"Mutation dry-run requires Canvas mutation: {self.command}")
        if self.dry_run_kind is DryRunKind.LOCAL_WRITE and not self.local_write:
            raise ValueError(f"Local dry-run requires local write: {self.command}")


def _policy(
    command: str,
    *,
    canvas_read: bool = False,
    local_write: bool = False,
    canvas_mutation: bool = False,
    dry_run_kind: DryRunKind = DryRunKind.NONE,
    bare_canvas_mutation: bool = False,
    destructive: bool = False,
    grade_affecting: bool = False,
    notification_or_visibility: bool = False,
    authoritative_verification: bool = False,
) -> CommandAccessPolicy:
    return CommandAccessPolicy(
        command=command,
        canvas_read=canvas_read,
        local_write=local_write,
        canvas_mutation=canvas_mutation,
        dry_run_kind=dry_run_kind,
        bare_canvas_mutation=bare_canvas_mutation,
        destructive=destructive,
        grade_affecting=grade_affecting,
        notification_or_visibility=notification_or_visibility,
        authoritative_verification=authoritative_verification,
    )


def _policies() -> tuple[CommandAccessPolicy, ...]:
    local_only = (
        _policy("status", local_write=True, authoritative_verification=True),
        _policy("reports list", local_write=True),
        _policy("reports latest", local_write=True),
        _policy("assignments audit", local_write=True, authoritative_verification=True),
        _policy("gradebook check", local_write=True, authoritative_verification=True),
        _policy("gradebook audit", local_write=True, authoritative_verification=True),
        _policy("quiz analysis", local_write=True),
        _policy("sources lint", local_write=True, authoritative_verification=True),
        _policy("pages render", local_write=True),
        _policy("pages css-check", authoritative_verification=True),
    )
    canvas_read = (
        _policy("init", canvas_read=True, local_write=True),
        _policy("refresh", canvas_read=True, local_write=True),
        _policy("courses", canvas_read=True, local_write=True),
        _policy("roster", canvas_read=True, local_write=True),
        _policy("auth doctor", canvas_read=True),
        _policy("assignments export", canvas_read=True, local_write=True),
        _policy("assignments overrides", canvas_read=True, local_write=True),
        _policy(
            "assignments verify",
            canvas_read=True,
            local_write=True,
            authoritative_verification=True,
        ),
        _policy("submissions export", canvas_read=True, local_write=True),
        _policy("submissions grades", canvas_read=True, local_write=True),
        _policy("submissions media", canvas_read=True, local_write=True),
        _policy("grades comments", canvas_read=True, local_write=True),
        _policy(
            "grades verify", canvas_read=True, local_write=True, authoritative_verification=True
        ),
        _policy("discussions export", canvas_read=True, local_write=True),
        _policy(
            "discussions verify",
            canvas_read=True,
            local_write=True,
            authoritative_verification=True,
        ),
        _policy("pages list", canvas_read=True),
        _policy("pages export", canvas_read=True, local_write=True),
        _policy(
            "pages verify", canvas_read=True, local_write=True, authoritative_verification=True
        ),
        _policy("announcements export", canvas_read=True, local_write=True),
        _policy("announcements latest", canvas_read=True, local_write=True),
        _policy(
            "announcements verify",
            canvas_read=True,
            local_write=True,
            authoritative_verification=True,
        ),
        _policy("files inventory", canvas_read=True, local_write=True),
        _policy("files download", canvas_read=True, local_write=True),
        _policy("files download-one", canvas_read=True, local_write=True),
        _policy(
            "files compare", canvas_read=True, local_write=True, authoritative_verification=True
        ),
        _policy(
            "discussions score",
            canvas_read=True,
            local_write=True,
            grade_affecting=True,
            notification_or_visibility=True,
        ),
    )
    local_write = tuple(
        _policy(
            command,
            canvas_read=True,
            local_write=True,
            dry_run_kind=DryRunKind.LOCAL_WRITE,
        )
        for command in (
            "pages sync",
            "announcements sync",
            "discussions sync-prompts",
            "recordings panopto-captions",
        )
    )
    mutation = (
        _policy(
            "assignments overrides-sync",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            destructive=True,
            authoritative_verification=True,
        ),
        _policy(
            "assignments create",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "assignments update",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "assignments upsert",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "quiz import-qti",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "submissions feedback",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "grades post",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "grades clear",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            destructive=True,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "discussions create",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "discussions update",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            grade_affecting=True,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "pages create",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "pages update",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "announcements create",
            canvas_read=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            notification_or_visibility=True,
        ),
        _policy(
            "announcements update",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            notification_or_visibility=True,
            authoritative_verification=True,
        ),
        _policy(
            "files upload",
            canvas_read=True,
            local_write=True,
            canvas_mutation=True,
            dry_run_kind=DryRunKind.CANVAS_MUTATION,
            destructive=True,
            authoritative_verification=True,
        ),
    )
    return (*local_only, *canvas_read, *local_write, *mutation)


ACCESS_POLICIES: Mapping[str, CommandAccessPolicy] = {
    policy.command: policy for policy in _policies()
}


def access_policy(command: str) -> CommandAccessPolicy:
    try:
        return ACCESS_POLICIES[command]
    except KeyError as exc:
        raise ValueError(f"No access policy declared for command: {command}") from exc
