"""Markdown front matter parsing shared by Canvas write commands."""

from __future__ import annotations

import datetime as dt
import tomllib
from pathlib import Path
from typing import Any

import yaml


def parse_frontmatter(text: str, source: Path, label: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines:
        raise SystemExit(f"{label} source must start with front matter: {source}")
    delimiter = lines[0].strip()
    if delimiter not in {"+++", "---"}:
        raise SystemExit(
            f"{label} source must start with YAML (---) or TOML (+++) front matter: {source}"
        )
    close = next(
        (idx for idx, line in enumerate(lines[1:], start=1) if line.strip() == delimiter), None
    )
    if close is None:
        raise SystemExit(f"{label} source missing closing {delimiter}: {source}")
    metadata_text = "".join(lines[1:close])
    if delimiter == "+++":
        metadata = tomllib.loads(metadata_text)
    else:
        metadata = yaml.safe_load(metadata_text) or {}
        if not isinstance(metadata, dict):
            raise SystemExit(f"{label} YAML front matter must be a mapping: {source}")
    body = "".join(lines[close + 1 :])
    return {str(key): value for key, value in metadata.items()}, body


def normalize_canvas_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_canvas_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_canvas_value(item) for key, item in value.items()}
    return value


def markdown_to_html(body: str) -> str:
    import markdown as markdown_lib

    return markdown_lib.markdown(body, extensions=["extra", "sane_lists"])
