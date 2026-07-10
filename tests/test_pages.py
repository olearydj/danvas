from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from danvas.pages import (
    COMPATIBILITY_PROFILE,
    build_pages_sync_plan,
    canonicalize_page_html,
    check_and_inline_css,
    command_pages_create,
    command_pages_export,
    command_pages_sync,
    command_pages_update,
    command_pages_verify,
    install_source_no_clobber,
    load_page_source,
    normalize_html_fragment,
    page_target_plan,
    render_synced_page_source,
)


def write_source(path: Path, body: str, *, published: bool = False, extra: str = "") -> Path:
    path.write_text(
        f"---\ntitle: Example Page\npublished: {str(published).lower()}\n{extra}---\n{body}\n",
        encoding="utf-8",
    )
    return path


class FakePage:
    def __init__(self, course: FakeCourse, **values: object):
        self.course = course
        self.page_id = 0
        self.url = ""
        for key, value in values.items():
            setattr(self, key, value)

    def edit(self, **kwargs: object) -> FakePage:
        payload = cast(dict[str, Any], kwargs["wiki_page"])
        for key, value in payload.items():
            if key != "notify_of_update":
                setattr(self, key, value)
        self.course.edits.append(payload)
        return self


class FakeCourse:
    id = 42

    def __init__(self) -> None:
        self.pages: dict[str, FakePage] = {}
        self.edits: list[dict[str, object]] = []

    def create_page(self, payload: dict[str, object]) -> FakePage:
        page = FakePage(
            self,
            page_id=101,
            url="example-page",
            front_page=payload.get("front_page", False),
            editing_roles=payload.get("editing_roles", "teachers"),
            publish_at=payload.get("publish_at"),
            **{key: value for key, value in payload.items() if key != "front_page"},
        )
        self.pages[page.url] = page
        return page

    def get_page(self, identity: object) -> FakePage:
        if str(identity) in self.pages:
            return self.pages[str(identity)]
        for page in self.pages.values():
            if str(page.page_id) == str(identity):
                return page
        raise AssertionError(f"unknown page {identity}")

    def get_pages(self) -> list[FakePage]:
        return list(self.pages.values())


class FakeCanvas:
    def __init__(self, course: FakeCourse):
        self.course = course

    def get_course(self, course_id: int) -> FakeCourse:
        assert course_id == 42
        return self.course


def args(source: Path, root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "source": str(source),
        "project_root": str(root),
        "course_id": 42,
        "page_id": None,
        "dry_run": False,
        "no_report": True,
        "report_root": None,
        "report_dir": None,
        "report_slug": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_markdown_render_is_fragment_with_stable_anchors_and_matching_h1(tmp_path: Path) -> None:
    source = write_source(
        tmp_path / "page.md",
        "# Example Page\n\n## Install\n\n[Jump](#install)\n\n## Install",
    )
    local = load_page_source(source)
    assert "<html" not in local.html
    assert "<h1" not in local.html
    assert '<h2 id="install">Install</h2>' in local.html
    assert '<h2 id="install_1">Install</h2>' in local.html
    assert local.matching_h1_removed is True
    assert local.local_links == ["install"]


def test_restricted_css_is_parsed_and_inlined_deterministically(tmp_path: Path) -> None:
    css = tmp_path / "page.canvas.css"
    css.write_text(".callout { color: #123456; padding: 1rem; }\n", encoding="utf-8")
    report, html = check_and_inline_css(css, '<p class="callout">Note</p>')
    assert report["profile"] == COMPATIBILITY_PROFILE
    assert report["errors"] == []
    assert normalize_html_fragment(html) == (
        '<p class="callout" style="color: #123456; padding: 1rem">Note</p>'
    )


def test_style_normalization_accepts_common_canvas_equivalents() -> None:
    expected = normalize_html_fragment('<p style="margin: 0px; color: #fff">Text</p>')
    actual = normalize_html_fragment(
        '<p style="color: rgb(255, 255, 255); margin: 0rem">Text</p>'
    )
    assert actual == expected


def test_page_url_canonicalization_removes_canvas_verifiers_and_blocks_external_signatures() -> None:
    canvas = canonicalize_page_html(
        '<a href="https://canvas.test/courses/42/files/7/download?verifier=secret&wrap=1">File</a>',
        course_id=42,
    )
    assert canvas["body_hash_status"] == "available"
    assert "secret" not in canvas["html"]
    assert 'href="/courses/42/files/7/download?wrap=1"' in canvas["html"]

    external = canonicalize_page_html(
        '<img src="https://cdn.test/image?X-Amz-Signature=secret">', course_id=42
    )
    assert external["body_hash_status"] == "blocked_volatile_url"
    assert external["body_sha256"] is None
    assert external["volatile_url_count"] == 1


@pytest.mark.parametrize(
    "css",
    [
        "@media (max-width: 600px) { p { color: red } }",
        "p::before { color: red }",
        "p { position: fixed }",
        "p { background-image: url(https://example.test/a.png) }",
    ],
)
def test_restricted_css_rejects_unsupported_constructs(tmp_path: Path, css: str) -> None:
    path = tmp_path / "bad.css"
    path.write_text(css, encoding="utf-8")
    report, _ = check_and_inline_css(path, "<p>Hello</p>")
    assert report["errors"]


def test_page_source_rejects_unsafe_html_and_local_assets(tmp_path: Path) -> None:
    unsafe = write_source(tmp_path / "unsafe.html", '<p onclick="go()">No</p>')
    with pytest.raises(SystemExit, match="Event-handler"):
        load_page_source(unsafe)
    asset = write_source(tmp_path / "asset.md", "![Local](image.png)")
    assert load_page_source(asset).unresolved_assets == ["image.png"]


def test_create_reads_back_then_writes_source_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_source(tmp_path / "page.md", "# Example Page\n\nHello")
    course = FakeCourse()
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    command_pages_create(args(source, tmp_path))
    source_map = json.loads((tmp_path / ".danvas" / "source-map.json").read_text())
    assert source_map["sources"][0]["kind"] == "page"
    assert source_map["sources"][0]["canvas"]["id"] == 101
    assert source_map["sources"][0]["last_posted"]["body_sha256"]


def test_update_changes_only_body_and_publication_then_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path / "page.md", "# Example Page\n\nNew body", published=True)
    course = FakeCourse()
    course.pages["example-page"] = FakePage(
        course,
        page_id=101,
        url="example-page",
        title="Example Page",
        body="<p>Old body</p>",
        published=False,
        front_page=False,
    )
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    command_pages_update(args(source, tmp_path, page_id="example-page"))
    assert course.edits == [
        {"body": "<p>New body</p>", "published": True, "notify_of_update": False}
    ]
    command_pages_verify(args(source, tmp_path, page_id="example-page"))


def test_update_refuses_title_or_front_page_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path / "page.md", "Body")
    course = FakeCourse()
    course.pages["wrong"] = FakePage(
        course,
        page_id=101,
        url="wrong",
        title="Different",
        body="<p>Body</p>",
        published=False,
        front_page=False,
    )
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    with pytest.raises(SystemExit, match="title/slug"):
        command_pages_update(args(source, tmp_path, page_id="wrong"))


def sync_args(root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "project_root": str(root),
        "course_id": 42,
        "output_dir": str(root / "content/pages"),
        "format": "markdown",
        "page_id": None,
        "url": None,
        "dry_run": False,
        "no_report": True,
        "report_root": None,
        "report_dir": None,
        "report_slug": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def canvas_record(**overrides: object) -> dict[str, Any]:
    body = str(
        overrides.pop(
            "body",
            '<h2 id="install">Install</h2><p>Hello <strong>world</strong>. '
            '<a href="#install">Jump</a></p><ul><li>One</li><li>Two</li></ul>',
        )
    )
    canonical = canonicalize_page_html(body, course_id=42)
    values: dict[str, Any] = {
        "page_id": 101,
        "url": "example-page",
        "title": "Example Page",
        "published": False,
        "front_page": False,
        "editing_roles": "teachers",
        "body": canonical["html"],
        **canonical,
    }
    values.update(overrides)
    return values


def test_synced_markdown_roundtrips_ids_links_lists_and_styles() -> None:
    record = canvas_record()
    rendered = render_synced_page_source(record, "markdown")

    assert rendered["status"] == "ready"
    assert "## Install {#install}" in rendered["source"]
    assert "[Jump](#install)" in rendered["source"]
    assert rendered["body_sha256"] == record["body_sha256"]

    styled = canvas_record(body='<p style="color: #123456">Styled</p>')
    styled_render = render_synced_page_source(styled, "markdown")
    assert styled_render["status"] == "ready"
    assert '<p style="color: #123456">Styled</p>' in styled_render["source"]

    table = canvas_record(
        body="<table><thead><tr><th>Item</th></tr></thead>"
        "<tbody><tr><td>One</td></tr></tbody></table>"
    )
    assert render_synced_page_source(table, "markdown")["status"] == "ready"


def test_synced_source_blocks_unresolved_signed_urls() -> None:
    record = canvas_record(body='<a href="https://cdn.test/x?X-Amz-Signature=secret">X</a>')

    rendered = render_synced_page_source(record, "html")

    assert rendered["status"] == "conversion_blocked"
    assert "secret" not in rendered["reason"]


def test_page_target_plan_is_inventory_wide_and_cross_platform(tmp_path: Path) -> None:
    first = canvas_record(page_id=101, url="Page", title="One")
    second = canvas_record(page_id=102, url="page", title="Two")

    targets = page_target_plan([first, second], tmp_path, "markdown")
    targeted = build_pages_sync_plan(
        inventory=[first, second],
        selected=[first],
        output_dir=tmp_path,
        fmt="markdown",
        project_root=tmp_path,
        dry_run=True,
    )

    assert targets["101"].name == "Page--page-101.md"
    assert targets["102"].name == "page--page-102.md"
    assert Path(targeted["actions"][0]["target_path"]) == targets["101"]

    reserved = canvas_record(page_id=103, url="CON", title="Reserved")
    trailing = canvas_record(page_id=104, url="trailing. ", title="Trailing")
    special_targets = page_target_plan([reserved, trailing], tmp_path, "html")
    assert special_targets["103"].name == "CON--page-103.html"
    assert special_targets["104"].name == "trailing.html"


def test_no_clobber_install_preserves_destination_created_during_race(tmp_path: Path) -> None:
    target = tmp_path / "page.md"
    target.write_text("other writer\n", encoding="utf-8")

    assert install_source_no_clobber(target, "generated\n") is False
    assert target.read_text(encoding="utf-8") == "other writer\n"


def test_pages_sync_creates_source_and_provenance_then_skips_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    course = FakeCourse()
    record = canvas_record()
    course.pages["example-page"] = FakePage(course, **record)
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))

    command_pages_sync(sync_args(tmp_path))

    source = tmp_path / "content/pages/example-page.md"
    assert source.is_file()
    source_map = json.loads((tmp_path / ".danvas/source-map.json").read_text())
    assert source_map["sources"][0]["canvas"]["id"] == 101

    command_pages_sync(sync_args(tmp_path))
    assert "skipped_known_local" in capsys.readouterr().out


def test_pages_sync_recovers_missing_provenance_without_rewriting_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse()
    record = canvas_record()
    course.pages["example-page"] = FakePage(course, **record)
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    real_write = __import__("danvas.pages", fromlist=["write_source_map_entry"]).write_source_map_entry
    monkeypatch.setattr(
        "danvas.pages.write_source_map_entry",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("simulated")),
    )

    with pytest.raises(SystemExit):
        command_pages_sync(sync_args(tmp_path))
    source = tmp_path / "content/pages/example-page.md"
    before = source.read_bytes()

    monkeypatch.setattr("danvas.pages.write_source_map_entry", real_write)
    command_pages_sync(sync_args(tmp_path))

    assert source.read_bytes() == before
    assert (tmp_path / ".danvas/source-map.json").is_file()


def test_pages_export_supports_targeted_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse()
    record = canvas_record()
    course.pages["example-page"] = FakePage(course, **record)
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    output = tmp_path / "export.md"
    export_args = SimpleNamespace(
        course_id=42,
        output=str(output),
        format="markdown",
        page_id="101",
        url=None,
        overwrite=False,
    )

    command_pages_export(export_args)

    assert "page_id: 101" in output.read_text(encoding="utf-8")
    assert "## Install {#install}" in output.read_text(encoding="utf-8")


def test_pages_sync_report_excludes_full_bodies_and_internal_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = FakeCourse()
    record = canvas_record()
    course.pages["example-page"] = FakePage(course, **record)
    monkeypatch.setattr("danvas.pages.canvas_from_args", lambda _args: FakeCanvas(course))
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas/config.toml").write_text(
        "[canvas]\ncourse_id = 42\n", encoding="utf-8"
    )
    report_dir = tmp_path / "report"

    command_pages_sync(
        sync_args(
            tmp_path,
            dry_run=True,
            no_report=False,
            report_dir=str(report_dir),
        )
    )

    report_text = (report_dir / "pages-sync.json").read_text(encoding="utf-8")
    assert "Hello" not in report_text
    assert '"_source"' not in report_text
    assert '"body_sha256"' in report_text
