from pathlib import Path

import pytest

from danvas.assignments import load_assignment_markdown, resolve_format


def test_load_assignment_markdown_accepts_yaml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
title: YAML Assignment
points_possible: 10
grading_type: points
submission_types:
  - online_upload
published: false
---

# YAML Assignment

Submit the report.
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert payload["name"] == "YAML Assignment"
    assert payload["points_possible"] == 10
    assert payload["submission_types"] == ["online_upload"]
    assert payload["published"] is False
    assert "<h1>YAML Assignment</h1>" in payload["description"]


def test_load_assignment_markdown_still_accepts_toml_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """+++
title = "TOML Assignment"
points_possible = 5
grading_type = "points"
submission_types = ["online_text_entry"]
+++

# TOML Assignment
""",
        encoding="utf-8",
    )

    payload = load_assignment_markdown(source)

    assert payload["name"] == "TOML Assignment"
    assert payload["submission_types"] == ["online_text_entry"]
    assert payload["published"] is False


def test_resolve_format_infers_from_extension() -> None:
    assert resolve_format(Path("assignments.json"), "auto") == "json"
    assert resolve_format(Path("assignments.csv"), "auto") == "csv"
    assert resolve_format(Path("assignments-md"), "auto") == "markdown"
    assert resolve_format(Path("assignments.md"), "csv") == "csv"


def test_resolve_format_rejects_ambiguous_extension() -> None:
    with pytest.raises(SystemExit, match="Cannot infer assignments export format"):
        resolve_format(Path("assignments.md"), "auto")


def test_load_assignment_markdown_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    source = tmp_path / "assignment.md"
    source.write_text(
        """---
- title
---

# Bad Assignment
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="must be a mapping"):
        load_assignment_markdown(source)
