"""Versioned authored-source layouts and project configuration resolution."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from danvas.project_config import load_project_config

SOURCE_KINDS = ("announcement", "discussion", "quiz", "assignment", "page")
SOURCE_CONFIG_KEYS = {
    "announcement": "announcements",
    "discussion": "discussions",
    "quiz": "quizzes",
    "assignment": "assignments",
    "page": "pages",
}
SOURCE_KIND_BY_CONFIG_KEY = {value: key for key, value in SOURCE_CONFIG_KEYS.items()}

LEGACY_SOURCE_PATTERNS = {
    "announcement": ["content/announcements/*.md"],
    "discussion": ["content/discussions/*.md"],
    "quiz": ["content/quizzes/chap*.md"],
    "assignment": ["content/cases/*-assignment.md"],
    "page": ["content/pages/*.md", "content/pages/*.html"],
}
LEGACY_SOURCE_EXCLUDES = {"page": ["content/pages/*-preview.html"]}

SOURCE_LAYOUTS: dict[str, dict[str, dict[str, Any]]] = {
    "legacy-v1": {
        "announcement": {
            "include": LEGACY_SOURCE_PATTERNS["announcement"],
            "output_dir": "content/announcements",
        },
        "discussion": {
            "include": LEGACY_SOURCE_PATTERNS["discussion"],
            "output_dir": "content/discussions",
        },
        "quiz": {"include": LEGACY_SOURCE_PATTERNS["quiz"]},
        "assignment": {
            "include": LEGACY_SOURCE_PATTERNS["assignment"],
            "require_assignment_metadata": False,
        },
        "page": {
            "include": LEGACY_SOURCE_PATTERNS["page"],
            "exclude": LEGACY_SOURCE_EXCLUDES["page"],
            "output_dir": "content/pages",
        },
    },
    "standard-v1": {
        "announcement": {
            "include": ["content/announcements/*.md"],
            "output_dir": "content/announcements",
        },
        "discussion": {
            "include": ["content/discussions/*.md"],
            "output_dir": "content/discussions",
        },
        "quiz": {"include": ["content/quizzes/*.md"]},
        "assignment": {
            "include": ["content/assignments/*.md"],
            "require_assignment_metadata": True,
        },
        "page": {
            "include": ["content/pages/*.md", "content/pages/*.html"],
            "exclude": ["content/pages/*-preview.html"],
            "output_dir": "content/pages",
        },
    },
}
SOURCE_LAYOUT_NAMES = tuple(SOURCE_LAYOUTS)
IMPLICIT_EXISTING_SOURCE_LAYOUT = "legacy-v1"
NEW_PROJECT_SOURCE_LAYOUT = "standard-v1"

_COMMON_KIND_KEYS = {"include", "includes", "exclude", "excludes"}
_OUTPUT_KINDS = {"announcement", "discussion", "page"}
_GLOB_CHARS = frozenset("*?[]")


def resolve_source_config(
    source_config: dict[str, Any] | None,
    *,
    default_layout: str = IMPLICIT_EXISTING_SOURCE_LAYOUT,
) -> dict[str, Any]:
    """Return validated, canonical effective source configuration."""
    raw = source_config or {}
    if not isinstance(raw, dict):
        raise SystemExit("[sources] must be a TOML table.")
    _reject_unknown_source_keys(raw)

    layout = raw.get("layout", default_layout)
    if not isinstance(layout, str) or layout not in SOURCE_LAYOUTS:
        choices = ", ".join(SOURCE_LAYOUT_NAMES)
        raise SystemExit(f"sources.layout must be one of: {choices}.")

    effective: dict[str, Any] = {"layout": layout}
    for kind in SOURCE_KINDS:
        config_key = SOURCE_CONFIG_KEYS[kind]
        plural_options = raw.get(config_key)
        singular_options = raw.get(kind)
        if plural_options is not None and singular_options is not None:
            raise SystemExit(
                f"Configure either [sources.{config_key}] or [sources.{kind}], not both."
            )
        for table_name, options in (
            (config_key, plural_options),
            (kind, singular_options),
        ):
            if options is not None:
                _validate_kind_table(kind, table_name, options)
        raw_options = plural_options if plural_options is not None else singular_options
        raw_options = raw_options or {}

        base = deepcopy(SOURCE_LAYOUTS[layout][kind])
        custom_include = "include" in raw_options or "includes" in raw_options
        base["include"] = patterns_from_config(
            raw_options.get("include", raw_options.get("includes")),
            default=base.get("include", []),
            label=f"sources.{config_key}.include",
        )
        base["exclude"] = patterns_from_config(
            raw_options.get("exclude", raw_options.get("excludes")),
            default=base.get("exclude", []),
            label=f"sources.{config_key}.exclude",
        )
        base["require_assignment_metadata"] = False
        if kind == "assignment":
            inherited_requirement = bool(
                SOURCE_LAYOUTS[layout][kind].get("require_assignment_metadata", False)
            )
            base["require_assignment_metadata"] = bool_from_config(
                raw_options.get("require_assignment_metadata"),
                default=True if custom_include else inherited_requirement,
                label=f"sources.{config_key}.require_assignment_metadata",
            )
        if kind in _OUTPUT_KINDS:
            base["output_dir"] = output_dir_from_config(
                raw_options.get("output_dir"),
                default=base.get("output_dir"),
                label=f"sources.{config_key}.output_dir",
            )
        effective[config_key] = base
    return effective


def materialize_source_config(
    source_config: dict[str, Any] | None,
    *,
    default_layout: str = IMPLICIT_EXISTING_SOURCE_LAYOUT,
) -> dict[str, Any]:
    """Return canonical TOML-ready source configuration with inherited values expanded."""
    effective = resolve_source_config(source_config, default_layout=default_layout)
    materialized: dict[str, Any] = {"layout": effective["layout"]}
    for kind in SOURCE_KINDS:
        config_key = SOURCE_CONFIG_KEYS[kind]
        options = effective[config_key]
        rendered: dict[str, Any] = {"include": list(options["include"])}
        if options["exclude"]:
            rendered["exclude"] = list(options["exclude"])
        if kind == "assignment":
            rendered["require_assignment_metadata"] = bool(
                options["require_assignment_metadata"]
            )
        if kind in _OUTPUT_KINDS:
            rendered["output_dir"] = options["output_dir"]
        materialized[config_key] = rendered
    return materialized


def source_options(kind: str, source_config: dict[str, Any] | None) -> dict[str, Any]:
    """Return discovery options for one authored-source kind."""
    if kind not in SOURCE_CONFIG_KEYS:
        raise KeyError(kind)
    options = resolve_source_config(source_config)[SOURCE_CONFIG_KEYS[kind]]
    return {
        "include": list(options["include"]),
        "exclude": list(options["exclude"]),
        "require_assignment_metadata": bool(options["require_assignment_metadata"]),
    }


def source_output_dir_value(
    kind: str, source_config: dict[str, Any] | None
) -> str | None:
    """Resolve a configured or unambiguously derived relative sync directory."""
    if kind not in _OUTPUT_KINDS:
        raise KeyError(kind)
    raw = source_config or {}
    effective = resolve_source_config(raw)
    config_key = SOURCE_CONFIG_KEYS[kind]
    raw_options = raw.get(config_key)
    if raw_options is None:
        raw_options = raw.get(kind)
    if isinstance(raw_options, dict) and "output_dir" in raw_options:
        return str(effective[config_key]["output_dir"])
    return unambiguous_static_parent(effective[config_key]["include"])


def resolve_source_output_dir(
    kind: str,
    *,
    project_root: Path,
    explicit: Path | str | None = None,
    source_config: dict[str, Any] | None = None,
) -> Path:
    """Resolve sync output precedence before any Canvas context is constructed."""
    if explicit is not None:
        return Path(explicit).resolve()
    root = project_root.resolve()
    if source_config is None:
        source_config = load_project_config(root).get("sources") or {}
    relative = source_output_dir_value(kind, source_config)
    if relative is None:
        config_key = SOURCE_CONFIG_KEYS[kind]
        raise SystemExit(
            f"sources.{config_key}.output_dir is required because "
            f"sources.{config_key}.include does not have one unambiguous static parent."
        )
    return (root / relative).resolve()


def unambiguous_static_parent(patterns: list[str]) -> str | None:
    parents: set[str] = set()
    for pattern in patterns:
        parent = Path(pattern).parent
        parent_text = parent.as_posix()
        if any(character in parent_text for character in _GLOB_CHARS):
            return None
        parents.add(parent_text)
    if len(parents) != 1:
        return None
    return next(iter(parents))


def patterns_from_config(value: Any, *, default: list[str], label: str) -> list[str]:
    patterns: list[str]
    if value is None:
        patterns = list(default)
    elif isinstance(value, str):
        patterns = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        patterns = [str(item) for item in value]
    else:
        raise SystemExit(f"{label} must be a string or list of strings.")
    for pattern in patterns:
        _require_project_relative_path(pattern, label=label)
    return patterns


def output_dir_from_config(value: Any, *, default: str | None, label: str) -> str | None:
    if value is None:
        output_dir = default
    elif isinstance(value, str):
        output_dir = value
    else:
        raise SystemExit(f"{label} must be a string.")
    if output_dir is None:
        return None
    _require_project_relative_path(output_dir, label=label)
    if any(character in output_dir for character in _GLOB_CHARS):
        raise SystemExit(f"{label} must not contain glob syntax.")
    return output_dir


def bool_from_config(value: Any, *, default: bool, label: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SystemExit(f"{label} must be true or false.")
    return value


def _reject_unknown_source_keys(raw: dict[str, Any]) -> None:
    allowed = {"layout", *SOURCE_KINDS, *SOURCE_CONFIG_KEYS.values()}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise SystemExit(f"Unknown source configuration key: sources.{unknown[0]}")


def _validate_kind_table(kind: str, table_name: str, raw_options: Any) -> None:
    if not isinstance(raw_options, dict):
        raise SystemExit(f"[sources.{table_name}] must be a TOML table.")
    allowed = set(_COMMON_KIND_KEYS)
    if kind == "assignment":
        allowed.add("require_assignment_metadata")
    if kind in _OUTPUT_KINDS:
        allowed.add("output_dir")
    unknown = sorted(set(raw_options) - allowed)
    if unknown:
        raise SystemExit(
            f"Unknown source configuration key: sources.{table_name}.{unknown[0]}"
        )


def _require_project_relative_path(value: str, *, label: str) -> None:
    if not value:
        raise SystemExit(f"{label} must not be empty.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"{label} must be a relative path inside the course root.")
