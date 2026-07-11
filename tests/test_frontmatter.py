from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from danvas.frontmatter import normalize_canvas_value, parse_frontmatter


def test_parse_frontmatter_requires_closing_delimiter(tmp_path: Path) -> None:
    source = tmp_path / "missing.md"

    with pytest.raises(SystemExit, match="missing closing"):
        parse_frontmatter("---\ntitle: Missing\n", source, "Page")


def test_parse_frontmatter_requires_yaml_mapping(tmp_path: Path) -> None:
    source = tmp_path / "list.md"

    with pytest.raises(SystemExit, match="must be a mapping"):
        parse_frontmatter("---\n- one\n- two\n---\nBody\n", source, "Page")


def test_parse_toml_frontmatter_round_trips_body(tmp_path: Path) -> None:
    source = tmp_path / "page.md"

    metadata, body = parse_frontmatter(
        '+++\ntitle = "Example"\npublished = false\n+++\nBody\n',
        source,
        "Page",
    )

    assert metadata == {"title": "Example", "published": False}
    assert body == "Body\n"


def test_normalize_canvas_value_recurses_through_dates_and_collections() -> None:
    value = {
        "date": dt.date(2026, 7, 10),
        "items": [dt.time(12, 30), {1: dt.datetime(2026, 7, 10, 12, 30)}],
    }

    assert normalize_canvas_value(value) == {
        "date": "2026-07-10",
        "items": ["12:30:00", {"1": "2026-07-10T12:30:00"}],
    }
