"""Stable serialization helpers for the Sprint 22 interface baseline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import click


def json_value(value: Any) -> Any:
    """Return a deterministic JSON-safe representation of a Click default."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, tuple | list):
        return [json_value(item) for item in value]
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def parameter_record(parameter: click.Parameter) -> dict[str, Any]:
    """Serialize the executable parts of one Click argument or option."""
    parameter_type = parameter.type
    record: dict[str, Any] = {
        "kind": "option" if isinstance(parameter, click.Option) else "argument",
        "name": parameter.name,
        "type": parameter_type.name,
        "required": parameter.required,
        "default": json_value(parameter.default),
        "nargs": parameter.nargs,
        "multiple": parameter.multiple,
        "envvar": json_value(parameter.envvar),
    }
    if isinstance(parameter_type, click.Choice):
        record["choices"] = [json_value(choice) for choice in parameter_type.choices]
        record["case_sensitive"] = bool(parameter_type.case_sensitive)
    if isinstance(parameter, click.Option):
        record.update(
            {
                "options": [*parameter.opts, *parameter.secondary_opts],
                "help": parameter.help,
                "hidden": parameter.hidden,
                "is_flag": parameter.is_flag,
                "flag_value": json_value(parameter.flag_value),
                "count": parameter.count,
            }
        )
    else:
        record.update(
            {
                "options": [],
                "help": getattr(parameter, "help", None),
                "hidden": getattr(parameter, "hidden", False),
            }
        )
    return record


def command_tree_record(root: click.Command) -> dict[str, Any]:
    """Serialize the complete ordered Click tree, including group metadata."""

    def visit(command: click.Command, path: tuple[str, ...]) -> dict[str, Any]:
        record: dict[str, Any] = {
            "path": " ".join(path),
            "kind": "group" if isinstance(command, click.Group) else "leaf",
            "name": command.name,
            "help": command.help,
            "short_help": command.short_help,
            "completion_summary": command.get_short_help_str(),
            "deprecated": bool(command.deprecated),
            "hidden": command.hidden,
            "parameters": [parameter_record(parameter) for parameter in command.params],
        }
        if isinstance(command, click.Group):
            record["children"] = [
                visit(child, (*path, name)) for name, child in command.commands.items()
            ]
        return record

    return visit(root, ())


def command_records(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a serialized tree in displayed command order."""
    records = [tree]
    for child in tree.get("children", []):
        records.extend(command_records(child))
    return records
