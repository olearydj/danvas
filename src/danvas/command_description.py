"""Deterministic text and JSON discovery for the public danvas command tree."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Final

from typer.core import TyperGroup, TyperOption

from danvas import __version__
from danvas.access import ACCESS_POLICIES
from danvas.artifacts import ARTIFACT_POLICIES
from danvas.command_guides import COMMAND_GUIDES

COMMAND_GUIDE_SCHEMA: Final = "danvas-command-guide-v1"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _parameter_record(parameter: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": "option" if isinstance(parameter, TyperOption) else "argument",
        "name": parameter.name,
        "type": parameter.type.name,
        "required": parameter.required,
        "multiple": parameter.multiple,
        "nargs": parameter.nargs,
        "safe_default": _json_value(parameter.default),
        "description": getattr(parameter, "help", None),
    }
    choices = getattr(parameter.type, "choices", None)
    if choices is not None:
        record["choices"] = [_json_value(choice) for choice in choices]
        record["case_sensitive"] = bool(getattr(parameter.type, "case_sensitive", True))
    if isinstance(parameter, TyperOption):
        record.update(
            {
                "names": [*parameter.opts, *parameter.secondary_opts],
                "is_flag": parameter.is_flag,
                "hidden": parameter.hidden,
            }
        )
    else:
        record["names"] = []
    return record


def _access_record(command: str) -> dict[str, Any] | None:
    policy = ACCESS_POLICIES.get(command)
    if policy is None:
        return None
    record = asdict(policy)
    record["dry_run_kind"] = policy.dry_run_kind.value
    return record


def _artifact_record(command: str) -> dict[str, Any]:
    policy = ARTIFACT_POLICIES.get(command)
    if policy is None:
        return {"retained": False, "artifact_class": None, "default_relative": None}
    return {
        "retained": policy.retained,
        "artifact_class": policy.artifact_class.value,
        "default_relative": policy.default_relative,
    }


def _guide_record(command: str) -> dict[str, Any]:
    guide = COMMAND_GUIDES[command]
    return {
        "purpose": guide.purpose,
        "identity": [
            {"kind": rule.kind.value, "description": rule.description} for rule in guide.identities
        ],
        "outputs": list(guide.outputs),
        "guards": list(guide.guards),
        "exit_statuses": [asdict(status) for status in guide.exits],
        "examples": [
            {
                "label": example.label,
                "argv": list(example.argv),
                "stage": example.stage.value,
            }
            for example in guide.examples
        ],
        "workflows": [
            {"title": workflow.title, "steps": [list(step) for step in workflow.steps]}
            for workflow in guide.workflows
        ],
        "recovery": [category.value for category in guide.recovery],
        "related_commands": list(guide.related_commands),
        "guide_topics": list(guide.guide_topics),
    }


def _requirements(command: Any, path: str) -> dict[str, Any]:
    option_names = {
        option
        for parameter in command.params
        if isinstance(parameter, TyperOption)
        for option in (*parameter.opts, *parameter.secondary_opts)
    }
    access = ACCESS_POLICIES.get(path)
    return {
        "canvas": bool(access and access.canvas_read),
        "network": bool(access and access.canvas_read),
        "credentials": bool(access and access.canvas_read),
        "profile_supported": "--profile" in option_names,
        "project_option": "--project-root" in option_names,
    }


def _command_record(command: Any, path: tuple[str, ...]) -> dict[str, Any]:
    canonical = " ".join(path)
    guide = COMMAND_GUIDES[canonical]
    record: dict[str, Any] = {
        "command_path": canonical,
        "name": command.name,
        "kind": "group" if isinstance(command, TyperGroup) else "leaf",
        "aliases": [],
        "summary": command.get_short_help_str(),
        **_guide_record(canonical),
        "parameters": [_parameter_record(parameter) for parameter in command.params],
        "requirements": _requirements(command, canonical),
        "access": _access_record(canonical),
        "artifact": _artifact_record(canonical),
    }
    access = ACCESS_POLICIES.get(canonical)
    record["plan_apply"] = {
        "dry_run_kind": access.dry_run_kind.value if access else "none",
        "apply_option": bool(access and access.canvas_mutation),
        "additional_guards": list(guide.guards),
    }
    if isinstance(command, TyperGroup):
        record["children"] = [
            _command_record(child, (*path, name)) for name, child in command.commands.items()
        ]
    return record


def _resolve_command(
    root: Any, command_path: tuple[str, ...]
) -> tuple[Any, tuple[str, ...]]:
    current = root
    resolved: list[str] = []
    for part in command_path:
        if not isinstance(current, TyperGroup) or part not in current.commands:
            available = sorted(current.commands) if isinstance(current, TyperGroup) else []
            suffix = f" Available here: {', '.join(available)}." if available else ""
            raise ValueError(
                f"Unknown command path: {' '.join(command_path)!r}.{suffix} "
                "Run 'danvas --help' to inspect the command tree."
            )
        current = current.commands[part]
        resolved.append(part)
    return current, tuple(resolved)


def describe_payload(root: Any, command_path: tuple[str, ...] = ()) -> dict[str, Any]:
    command, resolved = _resolve_command(root, command_path)
    return {
        "schema_version": COMMAND_GUIDE_SCHEMA,
        "danvas_version": __version__,
        "command_path": " ".join(resolved),
        "command": _command_record(command, resolved),
    }


def describe_json(root: Any, command_path: tuple[str, ...] = ()) -> str:
    return (
        json.dumps(
            describe_payload(root, command_path),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def describe_text(root: Any, command_path: tuple[str, ...] = ()) -> str:
    command, resolved = _resolve_command(root, command_path)
    canonical = " ".join(resolved)
    guide = COMMAND_GUIDES[canonical]
    title = "danvas" if not canonical else f"danvas {canonical}"
    lines = [title, guide.purpose]
    access = ACCESS_POLICIES.get(canonical)
    if access is not None:
        lines.append(
            "Effects: "
            f"canvas_read={str(access.canvas_read).lower()}, "
            f"local_write={str(access.local_write).lower()}, "
            f"canvas_mutation={str(access.canvas_mutation).lower()}, "
            f"verification={str(access.authoritative_verification).lower()}"
        )
        lines.append(
            f"Privacy: {_artifact_record(canonical)['artifact_class'] or 'no retained output'}"
        )
    if guide.examples:
        lines.append("Examples:")
        lines.extend(f"  {' '.join(example.argv)}" for example in guide.examples)
    if isinstance(command, TyperGroup):
        lines.append("Commands:")
        lines.extend(
            f"  {name:<20} {child.get_short_help_str()}" for name, child in command.commands.items()
        )
    return "\n".join(lines) + "\n"
