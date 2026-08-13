from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from danvas.panopto import (
    caption_filename_from_response,
    collect_lti_sessions,
    command_panopto_captions,
    discover_panopto_tool,
    download_lti_caption,
    normalize_panopto_base_url,
    parse_panopto_date,
    write_caption_outputs,
)


class FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        *,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        links: dict[str, Any] | None = None,
        status_code: int = 200,
        url: str = "https://example.test/",
    ) -> None:
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self.links = links or {}
        self.status_code = status_code
        self.url = url

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} response")


class FakeCanvasSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.get_calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


class FakePanoptoSession:
    def __init__(
        self,
        pages: list[list[dict[str, Any]]] | None = None,
        *,
        caption_content: bytes = b"",
        caption_headers: dict[str, str] | None = None,
    ) -> None:
        self.pages = pages or []
        self.caption_content = caption_content
        self.caption_headers = caption_headers or {}
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        page = self.pages.pop(0) if self.pages else []
        return FakeResponse({"d": {"Results": page}})

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse(content=self.caption_content, headers=self.caption_headers)


def test_command_uses_profile_secret_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_resolve_api_key(**kwargs: str) -> tuple[str, str]:
        captured.update(kwargs)
        return "token", "test"

    def stop_after_auth(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("stop after authentication")

    monkeypatch.setattr("danvas.panopto.resolve_api_key", fake_resolve_api_key)
    monkeypatch.setattr("danvas.panopto.discover_panopto_tool", stop_after_auth)

    with pytest.raises(RuntimeError, match="stop after authentication"):
        command_panopto_captions(
            SimpleNamespace(
                secret_provider="env",
                op_reference="",
                api_key_env="INSTITUTION_TOKEN",
                secret_name="canvas-institution",
                api_url="https://canvas.example/",
                course_id=101,
                output_dir=str(tmp_path / "captions"),
                project_root=None,
                overwrite=False,
            )
        )

    assert captured == {
        "provider": "env",
        "op_reference": "",
        "env_var": "INSTITUTION_TOKEN",
        "secret_name": "canvas-institution",
    }


def test_parse_panopto_date_preserves_out_of_range_value() -> None:
    value = "/Date(99999999999999999)/"

    assert parse_panopto_date(value) == value


def test_discover_panopto_tool_from_visible_course_nav() -> None:
    canvas = FakeCanvasSession(
        [
            FakeResponse(
                [
                    {"id": 11, "name": "Grades", "domain": ""},
                    {
                        "id": 448843,
                        "name": "Panopto Video",
                        "domain": "auburn.hosted.panopto.com",
                    },
                ]
            )
        ]
    )

    tool = discover_panopto_tool(canvas, "https://canvas.example/", 101)

    assert tool["id"] == 448843
    assert canvas.get_calls[0]["url"].endswith(
        "/api/v1/courses/101/external_tools/visible_course_nav_tools"
    )


def test_normalize_panopto_base_url_accepts_domains_and_lti_urls() -> None:
    assert (
        normalize_panopto_base_url("auburn.hosted.panopto.com/Panopto/LTI/LTI.aspx")
        == "https://auburn.hosted.panopto.com"
    )
    assert (
        normalize_panopto_base_url("https://auburn.hosted.panopto.com/Panopto/Pages/Home.aspx")
        == "https://auburn.hosted.panopto.com"
    )


def test_collect_lti_sessions_filters_deduplicates_and_pages() -> None:
    lecture_one = {
        "SessionID": "session-one",
        "SessionName": "Lecture 1",
        "HasCaptions": True,
    }
    lecture_two = {
        "SessionID": "session-two",
        "SessionName": "Lecture 2",
        "HasCaptions": True,
    }
    web = FakePanoptoSession(pages=[[lecture_one, lecture_one], [lecture_two], []])

    sessions = collect_lti_sessions(
        web,
        "https://panopto.example",
        folder_id="folder-guid",
        session_ids=["session-two"],
        limit=5,
    )

    assert sessions == [lecture_two]
    assert web.post_calls[0]["json"]["queryParameters"]["folderID"] == "folder-guid"
    assert [call["json"]["queryParameters"]["page"] for call in web.post_calls] == [0, 1]


def test_collect_lti_sessions_stops_when_server_repeats_pages() -> None:
    lecture = {"SessionID": "session-one", "SessionName": "Lecture 1", "HasCaptions": True}
    web = FakePanoptoSession(pages=[[lecture], [lecture], [lecture]])

    sessions = collect_lti_sessions(
        web,
        "https://panopto.example",
        folder_id=None,
        session_ids=None,
        limit=5,
    )

    assert sessions == [lecture]
    assert len(web.post_calls) == 2


def test_caption_filename_from_response_handles_encoded_filename() -> None:
    response = FakeResponse(
        headers={"content-disposition": "attachment; filename*=UTF-8''Lecture%201.txt"}
    )

    assert caption_filename_from_response(response) == "Lecture 1.txt"


def test_download_lti_caption_writes_sanitized_caption_file(tmp_path: Path) -> None:
    web = FakePanoptoSession(
        caption_content=b"caption text\n",
        caption_headers={"content-disposition": 'attachment; filename="Lecture: One?.txt"'},
    )
    session = {
        "SessionID": "session-one",
        "DeliveryID": "delivery-one",
        "StartTime": "2026-06-01T18:00:00",
    }

    target = download_lti_caption(
        web,
        "https://panopto.example",
        session,
        output_dir=tmp_path,
        language="English_USA",
    )

    assert target.read_bytes() == b"caption text\n"
    assert target.with_name(f"{target.name}.artifact.json").is_file()
    assert target.stat().st_mode & 0o077 == 0
    assert ":" not in target.name
    assert "Lecture" in target.name
    assert web.get_calls[0]["params"] == {
        "id": "delivery-one",
        "language": "English_USA",
        "clean": "true",
    }


def test_write_caption_outputs_dry_run_writes_manifests_without_downloading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakePanoptoSession(caption_content=b"caption text\n")
    sessions = [
        {
            "SessionID": "session-one",
            "SessionName": "Lecture 1",
            "DeliveryID": "delivery-one",
            "HasCaptions": True,
            "StartTime": "2026-06-01T18:00:00",
            "FolderID": "folder-guid",
            "FolderName": "INSY 6600",
            "ViewerUrl": "https://panopto.example/viewer",
        }
    ]

    write_caption_outputs(
        web,
        sessions,
        "https://panopto.example",
        output_dir=tmp_path,
        dry_run=True,
        language="English_USA",
        course_id=101,
        panopto_tool={"id": 448843, "name": "Panopto Video"},
    )

    manifest_path = tmp_path / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(manifest["generated_at"]).tzinfo is not None
    assert manifest["dry_run"] is True
    assert manifest["artifact_class"] == "private"
    assert manifest["sessions"][0]["status"] == "caption_available"
    assert manifest["sessions"][0]["caption_path"] == ""
    assert "viewer" not in json.dumps(manifest).lower()
    assert "ViewerUrl" not in (tmp_path / "manifest.csv").read_text(encoding="utf-8")
    assert (tmp_path / "manifest.csv").is_file()
    assert manifest_path.stat().st_mode & 0o077 == 0
    assert (tmp_path / "manifest.csv").stat().st_mode & 0o077 == 0
    assert web.get_calls == []
    terminal = capsys.readouterr().out
    assert "Lecture 1" not in terminal
    assert "session-one" not in terminal
    assert "viewer" not in terminal.lower()


def test_panopto_requires_private_destination_before_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**kwargs: str) -> tuple[str, str]:
        raise AssertionError("credentials must not resolve before private path")

    monkeypatch.setattr("danvas.panopto.resolve_api_key", fail)

    with pytest.raises(SystemExit, match="Pass --output-dir"):
        command_panopto_captions(
            SimpleNamespace(
                output_dir=None,
                project_root=str(tmp_path),
                overwrite=False,
                secret_provider="env",
                op_reference="",
                api_key_env="TOKEN",
                secret_name="canvas",
            )
        )
