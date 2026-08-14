#!/usr/bin/env python3
"""Exercise source-layout onboarding through an installed danvas package."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from danvas.config import write_project_config
from danvas.source_layouts import (
    LEGACY_SOURCE_PATTERNS,
    materialize_source_config,
    resolve_source_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    return parser.parse_args()


def require_empty_workspace(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.exists() and any(resolved.iterdir()):
        raise SystemExit(f"quickstart fixture workspace must be empty: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def render_standard_project(workspace: Path) -> None:
    project = workspace / "new-project"
    config_path = project / ".danvas" / "config.toml"
    standard = materialize_source_config({"layout": "standard-v1"})
    write_project_config(
        config_path,
        course_snapshot={
            "course": {"id": 101, "name": "Example Course"},
            "assignment_groups": [],
        },
        api_url="https://canvas.example.edu/",
        timezone="America/New_York",
        profile="example-university",
        source_config=standard,
    )
    rendered = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if rendered.get("sources") != standard:
        raise SystemExit("quickstart fixture did not materialize standard-v1")
    if (project / "content").exists():
        raise SystemExit("quickstart fixture unexpectedly created authored content")


def verify_existing_legacy_project(workspace: Path) -> None:
    project = workspace / "existing-project"
    config_path = project / ".danvas" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[canvas]\n"
        "api_url = 'https://canvas.example.edu/'\n"
        "course_id = 101\n"
        "timezone = 'America/New_York'\n",
        encoding="utf-8",
    )
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    effective = resolve_source_config(parsed.get("sources"))
    if effective["layout"] != "legacy-v1":
        raise SystemExit("source-less existing project did not retain legacy-v1")
    if effective["assignments"]["include"] != LEGACY_SOURCE_PATTERNS["assignment"]:
        raise SystemExit("existing assignment discovery did not retain legacy-v1")
    if effective["quizzes"]["include"] != LEGACY_SOURCE_PATTERNS["quiz"]:
        raise SystemExit("existing quiz discovery did not retain legacy-v1")


def main() -> None:
    workspace = require_empty_workspace(parse_args().workspace)
    render_standard_project(workspace)
    verify_existing_legacy_project(workspace)
    print("public beta quickstart fixtures passed")


if __name__ == "__main__":
    main()
