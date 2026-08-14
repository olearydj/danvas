"""Progressive, registry-backed help rendering for the Typer interface."""

from __future__ import annotations

from collections.abc import Iterable

import typer
from typer.main import get_command_name
from typer.models import CommandInfo, TyperInfo

from danvas.access import ACCESS_POLICIES, CommandAccessPolicy, DryRunKind
from danvas.artifacts import ARTIFACT_POLICIES, ArtifactClass
from danvas.command_guides import COMMAND_GUIDES, CommandGuide, RecoveryCategory

_INSTALLED_APP_IDS: set[int] = set()


def _command_name(info: CommandInfo) -> str:
    if info.name:
        return info.name
    callback_name = getattr(info.callback, "__name__", None)
    if not isinstance(callback_name, str):
        raise ValueError("Registered danvas command has no name or callback")
    return get_command_name(callback_name)


def _group_name(info: TyperInfo) -> str:
    if info.name:
        return info.name
    if info.typer_instance is None:
        raise ValueError("Registered danvas group has no Typer instance")
    callback_name = getattr(info.typer_instance.info.callback, "__name__", None)
    if not isinstance(callback_name, str):
        raise ValueError("Registered danvas group has no name or callback")
    return get_command_name(callback_name)


def _lines_for_commands(commands: Iterable[tuple[str, ...]]) -> list[str]:
    return [f"    {' '.join(command)}" for command in commands]


def _artifact_text(command: str) -> str:
    policy = ARTIFACT_POLICIES.get(command)
    if policy is None or not policy.retained:
        return "No retained artifact is declared by default."
    if policy.artifact_class is ArtifactClass.PRIVATE:
        return (
            "Retained output may contain private course or student data. In an "
            "initialized project, private defaults stay beneath .danvas/private/."
        )
    if policy.artifact_class is ArtifactClass.COURSE_INTERNAL:
        return "Retained output is course-internal and is not automatically safe to publish."
    return "Retained output is shareable for its documented use."


def _effect_text(policy: CommandAccessPolicy) -> str:
    if policy.canvas_mutation:
        text = (
            "Reads Canvas and can change Canvas only with --apply. Omission or "
            "--dry-run produces a plan."
        )
    elif policy.dry_run_kind is DryRunKind.LOCAL_WRITE:
        text = (
            "Reads Canvas and may create local files. --dry-run previews local "
            "writes; this command never mutates Canvas."
        )
    elif policy.canvas_read and policy.local_write:
        text = "Reads Canvas and may retain local output; it does not mutate Canvas."
    elif policy.canvas_read:
        text = "Reads Canvas without mutating it."
    elif policy.local_write:
        text = "Uses local project data and may retain local output; it does not access Canvas."
    else:
        text = "Runs locally without Canvas access or retained output."
    additions: list[str] = []
    if policy.destructive:
        additions.append("The applied operation can remove or replace existing Canvas state.")
    if policy.grade_affecting:
        additions.append("The workflow can affect grades.")
    if policy.notification_or_visibility:
        additions.append("The workflow can affect notifications or visibility.")
    return " ".join((text, *additions))


_RECOVERY_TEXT = {
    RecoveryCategory.CORRECT_INPUT: "Correct the reported input or configuration issue, then rerun.",
    RecoveryCategory.INSPECT_EVIDENCE: "Inspect the retained plan/result evidence before deciding what to do next.",
    RecoveryCategory.REFRESH_AND_REPLAN: "Refresh current Canvas state and generate a new plan before applying again.",
    RecoveryCategory.DO_NOT_BLINDLY_RETRY: "Do not blindly retry an accepted-unverified or indeterminate write.",
    RecoveryCategory.MOVE_ASIDE: "Move an incomplete or conflicting local artifact aside; danvas will not delete it for you.",
}


def _leaf_epilog(guide: CommandGuide, policy: CommandAccessPolicy) -> str:
    sections = [
        f"Effect:\n\n  {_effect_text(policy)}",
        f"Privacy:\n\n  {_artifact_text(guide.command)}",
    ]
    if guide.identities:
        sections.append(
            "Resolution:\n\n" + "\n\n".join(f"  {rule.description}" for rule in guide.identities)
        )
    if guide.examples:
        sections.append(
            "Typical sequence:\n\n"
            + "\n\n".join(_lines_for_commands(example.argv for example in guide.examples))
        )
    if guide.outputs:
        sections.append("Outputs:\n\n" + "\n\n".join(f"  {output}" for output in guide.outputs))
    if policy.authoritative_verification:
        sections.append(
            "Verification:\n\n"
            "  Applied or compared state is checked against authoritative evidence."
        )
    if guide.guards:
        sections.append("Safety guards:\n\n" + "\n\n".join(f"  {guard}" for guard in guide.guards))
    if guide.recovery:
        sections.append(
            "Failure boundary:\n\n"
            + "\n\n".join(f"  {_RECOVERY_TEXT[category]}" for category in guide.recovery)
        )
    if guide.related_commands:
        sections.append(
            "Related:\n\n"
            + "\n\n".join(f"  danvas {command}" for command in guide.related_commands)
        )
    return "\n\n".join(sections)


def _group_privacy(prefix: str) -> str:
    classes = {
        policy.artifact_class
        for command, policy in ARTIFACT_POLICIES.items()
        if command.startswith(f"{prefix} ")
    }
    if ArtifactClass.PRIVATE in classes:
        return (
            "Some retained outputs in this family are private and default beneath "
            ".danvas/private/ in an initialized project."
        )
    if ArtifactClass.COURSE_INTERNAL in classes:
        return "Retained outputs are course-internal and are not automatically safe to publish."
    return "This family has no private retained-output default."


def _group_safety(prefix: str) -> str:
    policies = [
        policy for command, policy in ACCESS_POLICIES.items() if command.startswith(f"{prefix} ")
    ]
    statements: list[str] = []
    if any(policy.canvas_mutation for policy in policies):
        statements.append(
            "Canvas-changing subcommands plan on omission; --apply authorizes the write."
        )
    if any(policy.dry_run_kind is DryRunKind.LOCAL_WRITE for policy in policies):
        statements.append(
            "Local sync/download subcommands use --dry-run for local-write previews and never use --apply."
        )
    if not statements:
        statements.append("Subcommands do not mutate Canvas.")
    return " ".join(statements)


def _group_help(summary: str, guide: CommandGuide) -> str:
    lines = [summary, "", guide.purpose]
    if guide.workflows:
        lines.extend(("", "Common workflows:"))
        for workflow in guide.workflows:
            lines.extend(("", f"  {workflow.title}:"))
            lines.extend(_lines_for_commands(workflow.steps))
    if guide.identities:
        lines.extend(("", "Identity:"))
        lines.extend(f"  {rule.description}" for rule in guide.identities)
    lines.extend(
        (
            "",
            "Privacy and safety:",
            f"  {_group_privacy(guide.command)}",
            f"  {_group_safety(guide.command)}",
        )
    )
    if guide.related_commands:
        lines.extend(("", "Related:"))
        lines.extend(f"  danvas {command}" for command in guide.related_commands)
    return "\n".join(lines)


def _root_help(summary: str) -> str:
    return "\n".join(
        (
            summary,
            "",
            "Danvas supports operational Canvas course work; archival ledger and history tooling is out of scope.",
            "",
            "Start here:",
            "  danvas auth doctor",
            "  danvas init 12345 --profile example",
            "  danvas refresh --diff",
            "  danvas status",
            "",
            "Effects:",
            "  Read-only commands inspect local or Canvas state. Local-write commands retain reports, exports, downloads, or authored sources. Canvas-changing commands plan on omission; --apply authorizes Canvas writes.",
            "",
            "Privacy:",
            "  Student-identifying artifacts default beneath .danvas/private/ in an initialized project. Course-internal output is not automatically safe to publish.",
            "",
            "More guidance:",
            "  danvas guide list",
            "  danvas describe assignments create --format json",
        )
    )


def _install_commands(typer_app: typer.Typer, prefix: tuple[str, ...]) -> None:
    for info in typer_app.registered_commands:
        name = _command_name(info)
        command = " ".join((*prefix, name))
        guide = COMMAND_GUIDES[command]
        policy = ACCESS_POLICIES[command]
        summary = info.help or guide.purpose
        info.help = summary if summary == guide.purpose else f"{summary}\n\n{guide.purpose}"
        info.epilog = _leaf_epilog(guide, policy)
    for group in typer_app.registered_groups:
        name = _group_name(group)
        command = " ".join((*prefix, name))
        child = group.typer_instance
        if child is None:
            raise ValueError(f"Registered danvas group has no Typer instance: {command}")
        summary = str(child.info.help)
        child.info.help = _group_help(summary, COMMAND_GUIDES[command])
        _install_commands(child, (*prefix, name))


def install_guided_help(typer_app: typer.Typer) -> None:
    """Attach deterministic long help after every command has been registered."""
    if id(typer_app) in _INSTALLED_APP_IDS:
        return
    typer_app.info.help = _root_help(str(typer_app.info.help))
    _install_commands(typer_app, ())
    _INSTALLED_APP_IDS.add(id(typer_app))
