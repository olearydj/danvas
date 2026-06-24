import json
from pathlib import Path

import pytest

from danvas.source_map import (
    load_source_map,
    resolve_source_canvas_id,
    source_map_path,
    source_path_key,
    write_source_map_entry,
)


def write_config(root: Path) -> None:
    config_dir = root / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )


def test_source_map_path_and_source_key_use_project_config(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("---\ntitle: Case\n---\n\nBody\n", encoding="utf-8")

    assert source_map_path(source) == tmp_path / ".danvas" / "source-map.json"
    assert source_path_key(source, source) == "content/case.md"


def test_resolve_source_canvas_id_prefers_explicit_id(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("", encoding="utf-8")
    write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=101,
        canvas={"id": 20, "url": "https://canvas.example/20"},
        command="assignments update",
        fields={"title": "Case"},
        project_root=tmp_path,
    )

    resolved = resolve_source_canvas_id(
        kind="assignment",
        source=source,
        explicit_id=30,
        frontmatter_id=10,
        project_root=tmp_path,
    )

    assert resolved["id"] == 30
    assert resolved["source"] == "cli"


def test_resolve_source_canvas_id_rejects_frontmatter_source_map_conflict(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("", encoding="utf-8")
    write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=101,
        canvas={"id": 20, "url": "https://canvas.example/20"},
        command="assignments update",
        fields={"title": "Case"},
        project_root=tmp_path,
    )

    with pytest.raises(SystemExit, match="conflicts with source-map ID 20"):
        resolve_source_canvas_id(
            kind="assignment",
            source=source,
            explicit_id=None,
            frontmatter_id=10,
            project_root=tmp_path,
        )


def test_write_source_map_entry_replaces_same_kind_and_path(tmp_path: Path) -> None:
    write_config(tmp_path)
    source = tmp_path / "content" / "case.md"
    source.parent.mkdir()
    source.write_text("", encoding="utf-8")

    write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=101,
        canvas={"id": 20, "url": "https://canvas.example/20"},
        command="assignments update",
        fields={"title": "Old"},
        body_sha256="old",
        project_root=tmp_path,
    )
    path = write_source_map_entry(
        kind="assignment",
        source=source,
        course_id=101,
        canvas={"id": 21, "url": "https://canvas.example/21"},
        command="assignments update",
        fields={"title": "New"},
        body_sha256="new",
        project_root=tmp_path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["canvas"]["id"] == 21
    assert payload["sources"][0]["last_posted"]["fields"]["title"] == "New"
    assert payload["sources"][0]["last_posted"]["body_sha256"] == "new"


def test_load_source_map_rejects_bad_schema(tmp_path: Path) -> None:
    write_config(tmp_path)
    path = tmp_path / ".danvas" / "source-map.json"
    path.write_text('{"schema_version": 2, "sources": []}', encoding="utf-8")

    with pytest.raises(SystemExit, match="Unsupported source map schema_version"):
        load_source_map(tmp_path)
