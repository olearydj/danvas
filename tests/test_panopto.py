from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from danvas.artifacts import write_private_pair
from danvas.credentials import (
    CredentialInput,
    CredentialKind,
    ResolvedCredential,
    SelectionSource,
)
from danvas.panopto import (
    caption_filename_from_response,
    collect_lti_sessions,
    command_panopto_captions,
    discover_panopto_tool,
    download_lti_caption,
    normalize_panopto_base_url,
    parse_panopto_date,
    resolve_panopto_settings,
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


def test_command_uses_shared_canvas_credential_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_resolve_canvas_credential(args: Any) -> ResolvedCredential:
        captured.update(
            kind=args.credential_input.kind.value,
            locator=args.credential_input.locator,
        )
        return ResolvedCredential(value="token", source_kind=CredentialKind.ENVIRONMENT)

    def stop_after_auth(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("stop after authentication")

    monkeypatch.setattr(
        "danvas.panopto.resolve_canvas_credential", fake_resolve_canvas_credential
    )
    monkeypatch.setattr("danvas.panopto.discover_panopto_tool", stop_after_auth)

    with pytest.raises(RuntimeError, match="stop after authentication"):
        command_panopto_captions(
            SimpleNamespace(
                credential_input=CredentialInput(
                    CredentialKind.ENVIRONMENT,
                    "INSTITUTION_TOKEN",
                    SelectionSource.USER_PROFILE,
                ),
                api_url="https://canvas.example/",
                course_id=101,
                output_dir=str(tmp_path / "captions"),
                project_root=None,
                overwrite=False,
            )
        )

    assert captured == {
        "kind": "environment",
        "locator": "INSTITUTION_TOKEN",
    }


def test_panopto_neutral_environment_is_removed_before_http_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    variable = "DANVAS_TEST_PANOPTO_TOKEN"
    token = "panopto-credential-sentinel"
    monkeypatch.setenv(variable, token)
    observed: dict[str, Any] = {}

    def stop_after_auth(session: requests.Session, *args: Any, **kwargs: Any) -> dict[str, Any]:
        observed["authorization"] = session.headers.get("Authorization")
        observed["variable_absent"] = variable not in os.environ
        raise RuntimeError("stop after authentication")

    monkeypatch.setattr("danvas.panopto.discover_panopto_tool", stop_after_auth)

    with pytest.raises(RuntimeError, match="stop after authentication"):
        command_panopto_captions(
            SimpleNamespace(
                credential_input=CredentialInput(
                    CredentialKind.ENVIRONMENT,
                    variable,
                    SelectionSource.CLI,
                ),
                credential_project_root=None,
                api_url="https://canvas.example/",
                course_id=101,
                output_dir=str(tmp_path / "captions"),
                project_root=None,
                overwrite=False,
            )
        )

    assert observed == {
        "authorization": f"Bearer {token}",
        "variable_absent": True,
    }


def test_parse_panopto_date_preserves_out_of_range_value() -> None:
    value = "/Date(99999999999999999)/"

    assert parse_panopto_date(value) == value


@pytest.fixture
def operator_timezone() -> Iterator[Callable[[str], None]]:
    original = os.environ.get("TZ")

    def apply(zone: str) -> None:
        os.environ["TZ"] = zone
        time.tzset()

    try:
        yield apply
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


@pytest.mark.parametrize("zone", ["America/Chicago", "Europe/Berlin", "UTC", "Pacific/Auckland"])
def test_parse_panopto_date_renders_utc_instant_regardless_of_operator_timezone(
    zone: str, operator_timezone: Callable[[str], None]
) -> None:
    operator_timezone(zone)

    assert parse_panopto_date("/Date(1700000000000)/") == "2023-11-14T22:13:20+00:00"


def test_discover_panopto_tool_from_visible_course_nav() -> None:
    canvas = FakeCanvasSession(
        [
            FakeResponse(
                [
                    {"id": 11, "name": "Grades", "domain": ""},
                    {
                        "id": 202,
                        "name": "Panopto Video",
                        "domain": "media.example.edu",
                    },
                ]
            )
        ]
    )

    tool = discover_panopto_tool(canvas, "https://canvas.example/", 101)

    assert tool["id"] == 202
    assert canvas.get_calls[0]["url"].endswith(
        "/api/v1/courses/101/external_tools/visible_course_nav_tools"
    )


def test_normalize_panopto_base_url_accepts_domains_and_lti_urls() -> None:
    assert (
        normalize_panopto_base_url("media.example.edu/Panopto/LTI/LTI.aspx")
        == "https://media.example.edu"
    )
    assert (
        normalize_panopto_base_url("https://media.example.edu/Panopto/Pages/Home.aspx")
        == "https://media.example.edu"
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


def test_interrupted_bundle_reuses_valid_pair_without_network_or_suffix(tmp_path: Path) -> None:
    web = FakePanoptoSession(
        caption_content=b"caption text\n",
        caption_headers={"content-disposition": 'attachment; filename="Lecture One.txt"'},
    )
    session = {
        "SessionID": "session-one",
        "SessionName": "Lecture 1",
        "DeliveryID": "delivery-one",
        "HasCaptions": True,
        "StartTime": "2026-06-01T18:00:00",
    }

    interrupted_path = download_lti_caption(
        web,
        "https://panopto.example",
        session,
        output_dir=tmp_path,
        language="English_USA",
    )
    assert not (tmp_path / "artifact-manifest.json").exists()

    write_caption_outputs(
        web,
        [session],
        "https://panopto.example",
        output_dir=tmp_path,
        dry_run=False,
        language="English_USA",
        course_id=101,
        panopto_tool={"id": 303, "name": "Panopto Video"},
    )

    manifest = json.loads((tmp_path / "artifact-manifest.json").read_text(encoding="utf-8"))
    retried_name = manifest["sessions"][0]["caption_path"]
    assert retried_name == interrupted_path.name
    assert manifest["sessions"][0]["status"] == "reused_after_interruption"
    assert interrupted_path.name in manifest["files"]
    assert retried_name in manifest["files"]
    assert len(web.get_calls) == 1


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
        panopto_tool={"id": 202, "name": "Panopto Video"},
    )

    manifest_path = tmp_path / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(manifest["generated_at"]).tzinfo is not None
    assert manifest["dry_run"] is True
    assert manifest["artifact_class"] == "private"
    assert manifest["sessions"][0]["status"] == "caption_available"
    assert manifest["sessions"][0]["caption_path"] == ""
    assert manifest["integration_settings"]["caption_language"] == "English_USA"
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


def test_completed_caption_bundle_is_no_clobber_by_default(tmp_path: Path) -> None:
    session = {"SessionID": "session-one", "HasCaptions": False}
    web = FakePanoptoSession()
    write_caption_outputs(
        web,
        [session],
        "https://panopto.example",
        output_dir=tmp_path,
        dry_run=True,
        language="English_USA",
        course_id=101,
        panopto_tool={"id": 202},
    )

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        write_caption_outputs(
            web,
            [session],
            "https://panopto.example",
            output_dir=tmp_path,
            dry_run=True,
            language="English_USA",
            course_id=101,
            panopto_tool={"id": 202},
        )

    assert web.get_calls == []


def test_manifest_records_effective_non_authorizing_integration_settings(
    tmp_path: Path,
) -> None:
    settings = {
        "caption_language": "French_FRA",
        "tool_name": "Panopto Video",
        "tool_id": 202,
        "base_url": "https://media.example.edu",
    }
    write_caption_outputs(
        FakePanoptoSession(),
        [{"SessionID": "session-one", "HasCaptions": False}],
        "https://media.example.edu",
        output_dir=tmp_path,
        dry_run=True,
        language="French_FRA",
        course_id=101,
        panopto_tool={"id": 202, "name": "Panopto Video"},
        integration_settings=settings,
    )

    manifest = json.loads((tmp_path / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["integration_settings"] == settings
    assert "launch" not in json.dumps(manifest).lower()
    assert "signed" not in json.dumps(manifest).lower()


def test_panopto_settings_use_cli_then_project_then_fallback(tmp_path: Path) -> None:
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[canvas]\ncourse_id = 101\n\n"
        "[integrations.panopto]\n"
        "caption_language = 'French_FRA'\n"
        "tool_name = 'Panopto Video'\n"
        "base_url = 'https://media.example.edu/'\n",
        encoding="utf-8",
    )

    configured = resolve_panopto_settings(SimpleNamespace(project_root=str(tmp_path)))
    explicit = resolve_panopto_settings(
        SimpleNamespace(
            project_root=str(tmp_path),
            caption_language="German_DEU",
            panopto_tool_name=None,
            panopto_tool_id=303,
            panopto_base_url="https://video.example.edu",
        )
    )
    fallback_root = tmp_path.parent / f"{tmp_path.name}-fallback"
    fallback_root.mkdir()
    fallback = resolve_panopto_settings(SimpleNamespace(project_root=str(fallback_root)))

    assert configured.caption_language == "French_FRA"
    assert configured.tool_name == "Panopto Video"
    assert configured.base_url == "https://media.example.edu"
    assert explicit.caption_language == "German_DEU"
    assert explicit.tool_name is None
    assert explicit.tool_id == 303
    assert explicit.base_url == "https://video.example.edu"
    assert fallback.caption_language == "English_USA"


@pytest.mark.parametrize(
    ("panopto_toml", "message"),
    [
        ("unknown = 'value'", "integrations.panopto.unknown"),
        ("caption_language = 4", "caption_language must be a non-empty string"),
        (
            "tool_name = 'Panopto'\ntool_id = 202",
            "either integrations.panopto.tool_name",
        ),
        ("base_url = 'http://media.example.edu'", "must be an HTTPS origin"),
        ("base_url = 'https://user@media.example.edu'", "must be an HTTPS origin"),
        ("base_url = 'https://media.example.edu/path'", "must be an HTTPS origin"),
    ],
)
def test_invalid_panopto_config_fails_before_secret_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    panopto_toml: str,
    message: str,
) -> None:
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[canvas]\ncourse_id = 101\napi_url = 'https://canvas.example.edu/'\n\n"
        f"[integrations.panopto]\n{panopto_toml}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "danvas.panopto.resolve_canvas_credential",
        lambda args: pytest.fail("credential resolution must not run"),
    )

    with pytest.raises(SystemExit, match=message):
        command_panopto_captions(
            SimpleNamespace(
                project_root=str(tmp_path),
                output_dir=str(tmp_path / "captions"),
                overwrite=False,
            )
        )


def test_configured_tool_name_is_exact_case_insensitive_and_ambiguity_rejected() -> None:
    canvas = FakeCanvasSession(
        [
            FakeResponse(
                [
                    {"id": 201, "name": "Panopto Archive", "domain": "old.example.edu"},
                    {"id": 202, "name": "Panopto Video", "domain": "media.example.edu"},
                ]
            )
        ]
    )

    tool = discover_panopto_tool(
        canvas,
        "https://canvas.example.edu/",
        101,
        tool_name="panopto video",
    )

    assert tool["id"] == 202

    ambiguous = FakeCanvasSession(
        [
            FakeResponse(
                [
                    {"id": 201, "name": "Panopto Video"},
                    {"id": 202, "name": "PANOPTO VIDEO"},
                ]
            )
        ]
    )
    with pytest.raises(SystemExit, match="ambiguous"):
        discover_panopto_tool(
            ambiguous,
            "https://canvas.example.edu/",
            101,
            tool_name="Panopto Video",
        )


def test_unmatched_configured_tool_name_does_not_fall_back_to_substring_match() -> None:
    canvas = FakeCanvasSession(
        [
            FakeResponse(
                [
                    {"id": 201, "name": "Panopto Recordings", "domain": "old.example.edu"},
                    {"id": 202, "name": "Panopto Video (Beta)", "domain": "media.example.edu"},
                ]
            ),
            FakeResponse([]),
        ]
    )

    with pytest.raises(SystemExit, match="'Panopto Video' was not found"):
        discover_panopto_tool(
            canvas,
            "https://canvas.example.edu/",
            101,
            tool_name="Panopto Video",
        )


def test_configured_tool_absent_from_nav_still_resolves_from_tabs() -> None:
    canvas = FakeCanvasSession(
        [
            FakeResponse([{"id": 11, "name": "Grades", "domain": ""}]),
            FakeResponse(
                [
                    {"id": "context_external_tool_202", "label": "Panopto Video"},
                ]
            ),
        ]
    )

    tool = discover_panopto_tool(
        canvas,
        "https://canvas.example.edu/",
        101,
        tool_name="Panopto Video",
    )

    assert tool["id"] == 202
    assert canvas.get_calls[1]["url"].endswith("/api/v1/courses/101/tabs")


def test_configured_tool_id_unknown_is_truthfully_rejected() -> None:
    canvas = FakeCanvasSession([FakeResponse([]), FakeResponse([])])

    with pytest.raises(SystemExit, match="ID 303 was not found"):
        discover_panopto_tool(
            canvas,
            "https://canvas.example.edu/",
            101,
            tool_id=303,
        )


@pytest.mark.parametrize("damage", ["missing_sidecar", "tampered", "orphan_sidecar"])
def test_interrupted_bundle_rejects_invalid_pairs_without_redownload(
    tmp_path: Path, damage: str
) -> None:
    web = FakePanoptoSession(
        caption_content=b"caption text\n",
        caption_headers={"content-disposition": 'attachment; filename="Lecture.txt"'},
    )
    session = {
        "SessionID": "session-one",
        "SessionName": "Lecture",
        "DeliveryID": "delivery-one",
        "HasCaptions": True,
        "StartTime": "2026-06-01T18:00:00",
    }
    target = download_lti_caption(
        web,
        "https://panopto.example",
        session,
        output_dir=tmp_path,
        language="English_USA",
    )
    sidecar = target.with_name(f"{target.name}.artifact.json")
    if damage == "missing_sidecar":
        sidecar.unlink()
    elif damage == "tampered":
        target.write_bytes(b"changed")
    else:
        target.unlink()

    with pytest.raises(SystemExit):
        write_caption_outputs(
            web,
            [session],
            "https://panopto.example",
            output_dir=tmp_path,
            dry_run=False,
            language="English_USA",
            course_id=101,
            panopto_tool={"id": 202, "name": "Panopto Video"},
        )

    assert len(web.get_calls) == 1
    assert not (tmp_path / "artifact-manifest.json").exists()


def test_interrupted_bundle_rejects_duplicate_session_sidecars(tmp_path: Path) -> None:
    write_private_pair(
        tmp_path / "one.txt",
        b"one",
        command="recordings panopto-captions",
        sidecar_fields={"session_id": "session-one"},
    )
    write_private_pair(
        tmp_path / "two.txt",
        b"two",
        command="recordings panopto-captions",
        sidecar_fields={"session_id": "session-one"},
    )

    with pytest.raises(SystemExit, match="duplicate session identity"):
        write_caption_outputs(
            FakePanoptoSession(),
            [{"SessionID": "session-one", "HasCaptions": True}],
            "https://panopto.example",
            output_dir=tmp_path,
            dry_run=False,
            language="English_USA",
            course_id=101,
            panopto_tool={"id": 202},
        )


def test_cross_session_filename_collision_blocks_without_suffix_or_manifest(
    tmp_path: Path,
) -> None:
    web = FakePanoptoSession(
        caption_content=b"caption text\n",
        caption_headers={"content-disposition": 'attachment; filename="Lecture.txt"'},
    )
    first = {
        "SessionID": "session-one",
        "DeliveryID": "delivery-one",
        "HasCaptions": True,
        "StartTime": "2026-06-01T18:00:00",
    }
    second = {**first, "SessionID": "session-two", "DeliveryID": "delivery-two"}
    target = download_lti_caption(
        web,
        "https://panopto.example",
        first,
        output_dir=tmp_path,
        language="English_USA",
    )

    with pytest.raises(SystemExit, match="will not create a suffixed duplicate"):
        write_caption_outputs(
            web,
            [first, second],
            "https://panopto.example",
            output_dir=tmp_path,
            dry_run=False,
            language="English_USA",
            course_id=101,
            panopto_tool={"id": 202},
        )

    assert target.is_file()
    assert not any(path.stem.endswith("-2") for path in tmp_path.iterdir())
    assert not (tmp_path / "artifact-manifest.json").exists()


def test_panopto_requires_private_destination_before_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(args: Any) -> ResolvedCredential:
        raise AssertionError("credentials must not resolve before private path")

    monkeypatch.setattr("danvas.panopto.resolve_canvas_credential", fail)

    with pytest.raises(SystemExit, match="Pass --output-dir"):
        command_panopto_captions(
            SimpleNamespace(
                output_dir=None,
                project_root=str(tmp_path),
                overwrite=False,
            )
        )
