"""Panopto recording/caption operations through Canvas LTI launch."""

from __future__ import annotations

import csv
import io
import json as jsonlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from danvas.artifacts import (
    ensure_private_directory,
    private_file_sha256,
    resolve_private_path,
    warn_if_external_private_path,
    write_private_json,
    write_private_pair,
    write_private_text,
)
from danvas.auth import announce_canvas_credential, resolve_canvas_credential
from danvas.project_config import load_project_config


class HttpSession(Protocol):
    """requests.Session-style GET interface; lets tests substitute fakes."""

    def get(
        self,
        url: str,
        *,
        params: Any = ...,
        timeout: Any = ...,
        allow_redirects: bool = ...,
    ) -> Any: ...


class WebSession(HttpSession, Protocol):
    def post(
        self,
        url: str,
        *,
        data: Any = ...,
        json: Any = ...,
        headers: Any = ...,
        timeout: Any = ...,
        allow_redirects: bool = ...,
    ) -> Any: ...


class HttpResponse(Protocol):
    @property
    def headers(self) -> Any: ...


CAPTION_MANIFEST_FIELDS = [
    "session_id",
    "name",
    "created_date",
    "duration",
    "folder_id",
    "folder_name",
    "has_caption",
    "caption_path",
    "status",
]
PANOPTO_CONFIG_KEYS = {"caption_language", "tool_name", "tool_id", "base_url"}
DEFAULT_CAPTION_LANGUAGE = "English_USA"


@dataclass(frozen=True)
class PanoptoSettings:
    caption_language: str
    tool_name: str | None
    tool_id: int | None
    base_url: str | None

    def manifest_record(self) -> dict[str, Any]:
        return {
            "caption_language": self.caption_language,
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "base_url": self.base_url,
        }


@dataclass(frozen=True)
class CaptionPair:
    session_id: str
    path: Path
    sidecar: Path


def command_panopto_captions(args: Any) -> None:
    resolved = resolve_private_path(
        explicit=getattr(args, "output_dir", None),
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        default_relative="recordings/panopto-captions",
        option_name="--output-dir",
    )
    warn_if_external_private_path(resolved)
    preflight_caption_bundle(resolved.path, overwrite=bool(getattr(args, "overwrite", False)))
    settings = resolve_panopto_settings(args)
    credential = resolve_canvas_credential(args)
    announce_canvas_credential(credential)
    canvas_session = requests.Session()
    canvas_session.headers.update({"Authorization": f"Bearer {credential.value}"})
    panopto_tool = discover_panopto_tool(
        canvas_session,
        args.api_url,
        args.course_id,
        tool_name=settings.tool_name,
        tool_id=settings.tool_id,
    )
    panopto_base_url = normalize_panopto_base_url(
        settings.base_url or panopto_tool.get("domain") or panopto_tool.get("url")
    )
    web = establish_lti_session(
        canvas_session,
        args.api_url,
        course_id=args.course_id,
        tool_id=panopto_tool.get("id"),
    )
    sessions = collect_lti_sessions(
        web,
        panopto_base_url,
        folder_id=args.folder_id,
        session_ids=args.session_id,
        limit=args.limit,
    )
    write_caption_outputs(
        web,
        sessions,
        panopto_base_url,
        output_dir=resolved.path,
        dry_run=args.dry_run,
        language=settings.caption_language,
        course_id=args.course_id,
        panopto_tool=panopto_tool,
        integration_settings={
            "caption_language": settings.caption_language,
            "tool_name": panopto_tool.get("name"),
            "tool_id": panopto_tool.get("id"),
            "base_url": panopto_base_url,
        },
        overwrite=bool(getattr(args, "overwrite", False)),
    )


def resolve_panopto_settings(args: Any) -> PanoptoSettings:
    """Resolve non-secret integration settings before authentication or LTI launch."""
    project_root = getattr(args, "project_root", None)
    config = load_project_config(Path(project_root) if project_root else None)
    integrations = config.get("integrations") or {}
    if not isinstance(integrations, dict):
        raise SystemExit("[integrations] must be a TOML table.")
    raw = integrations.get("panopto") or {}
    if not isinstance(raw, dict):
        raise SystemExit("[integrations.panopto] must be a TOML table.")
    unknown = sorted(set(raw) - PANOPTO_CONFIG_KEYS)
    if unknown:
        raise SystemExit(f"Unknown Panopto configuration key: integrations.panopto.{unknown[0]}")

    config_language = optional_nonempty_string(
        raw.get("caption_language"), label="integrations.panopto.caption_language"
    )
    config_name = optional_nonempty_string(
        raw.get("tool_name"), label="integrations.panopto.tool_name"
    )
    config_id = optional_positive_int(raw.get("tool_id"), label="integrations.panopto.tool_id")
    config_base_url = optional_panopto_origin(
        raw.get("base_url"), label="integrations.panopto.base_url"
    )
    if config_name is not None and config_id is not None:
        raise SystemExit(
            "Configure either integrations.panopto.tool_name or "
            "integrations.panopto.tool_id, not both."
        )

    explicit_language = optional_nonempty_string(
        getattr(args, "caption_language", None), label="--caption-language"
    )
    explicit_name = optional_nonempty_string(
        getattr(args, "panopto_tool_name", None), label="--panopto-tool-name"
    )
    explicit_id = optional_positive_int(
        getattr(args, "panopto_tool_id", None), label="--panopto-tool-id"
    )
    explicit_base_url = optional_panopto_origin(
        getattr(args, "panopto_base_url", None), label="--panopto-base-url"
    )
    if explicit_name is not None and explicit_id is not None:
        raise SystemExit("Use either --panopto-tool-name or --panopto-tool-id, not both.")

    if explicit_name is not None or explicit_id is not None:
        tool_name, tool_id = explicit_name, explicit_id
    else:
        tool_name, tool_id = config_name, config_id
    return PanoptoSettings(
        caption_language=explicit_language or config_language or DEFAULT_CAPTION_LANGUAGE,
        tool_name=tool_name,
        tool_id=tool_id,
        base_url=explicit_base_url or config_base_url,
    )


def optional_nonempty_string(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{label} must be a non-empty string.")
    return value.strip()


def optional_positive_int(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SystemExit(f"{label} must be a positive integer.")
    return value


def optional_panopto_origin(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"{label} must be an HTTPS origin string.")
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SystemExit(
            f"{label} must be an HTTPS origin without credentials, path, query, or fragment."
        )
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"https://{parsed.hostname}{port}"


def discover_panopto_tool(
    canvas: HttpSession,
    canvas_api_url: str,
    course_id: int,
    *,
    tool_name: str | None = None,
    tool_id: int | None = None,
) -> dict[str, Any]:
    tools = canvas_get_paginated(
        canvas,
        canvas_api_url,
        f"api/v1/courses/{course_id}/external_tools/visible_course_nav_tools",
    )
    configured = tool_name is not None or tool_id is not None
    if configured:
        # An explicit selector is never widened by the substring heuristic; an
        # unmatched selector continues to the tabs listing, which raises.
        tool_matches = configured_tool_matches(tools, tool_name=tool_name, tool_id=tool_id)
        if len(tool_matches) > 1:
            raise SystemExit("Configured Panopto tool selector is ambiguous in Canvas navigation.")
        if len(tool_matches) == 1:
            return tool_matches[0]
    else:
        for tool in tools:
            text = " ".join(str(tool.get(key) or "") for key in ("name", "url", "domain")).lower()
            if "panopto" in text:
                return tool

    tabs = canvas_get_paginated(canvas, canvas_api_url, f"api/v1/courses/{course_id}/tabs")
    if configured:
        normalized_tabs = [
            {
                "id": external_tool_id(tab),
                "name": tab.get("label"),
                "url": tab.get("url") or tab.get("html_url"),
            }
            for tab in tabs
        ]
        tab_matches = configured_tool_matches(
            normalized_tabs, tool_name=tool_name, tool_id=tool_id
        )
        if len(tab_matches) > 1:
            raise SystemExit("Configured Panopto tool selector is ambiguous in Canvas tabs.")
        if len(tab_matches) == 1:
            return tab_matches[0]
        selector = f"name {tool_name!r}" if tool_name is not None else f"ID {tool_id}"
        raise SystemExit(f"Configured Panopto tool {selector} was not found for course {course_id}.")
    for tab in tabs:
        text = " ".join(str(tab.get(key) or "") for key in ("label", "url", "html_url")).lower()
        if "panopto" in text:
            return {"id": external_tool_id(tab), "name": tab.get("label"), "url": tab.get("url")}

    raise SystemExit(f"No Panopto course navigation tool found for Canvas course {course_id}.")


def configured_tool_matches(
    tools: list[dict[str, Any]], *, tool_name: str | None, tool_id: int | None
) -> list[dict[str, Any]]:
    if tool_id is not None:
        return [tool for tool in tools if str(tool.get("id") or "") == str(tool_id)]
    expected = str(tool_name or "").casefold()
    return [tool for tool in tools if str(tool.get("name") or "").casefold() == expected]


def external_tool_id(tab: dict[str, Any]) -> int | str | None:
    tab_id = str(tab.get("id") or "")
    match = re.search(r"context_external_tool_(\d+)", tab_id)
    return int(match.group(1)) if match else tab.get("id")


def canvas_get_paginated(
    session: HttpSession, canvas_api_url: str, path: str
) -> list[dict[str, Any]]:
    url = urljoin(canvas_api_url.rstrip("/") + "/", path)
    rows: list[dict[str, Any]] = []
    while url:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Expected Canvas list response for {path}")
        rows.extend(payload)
        url = response.links.get("next", {}).get("url")
    return rows


def normalize_panopto_base_url(value: str | None) -> str:
    if not value:
        raise SystemExit("Could not determine Panopto base URL.")
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        raise SystemExit(f"Invalid Panopto URL/domain: {value}")
    return f"{parsed.scheme}://{parsed.netloc}"


def establish_lti_session(
    canvas: HttpSession,
    canvas_api_url: str,
    *,
    course_id: int,
    tool_id: Any,
) -> requests.Session:
    if not tool_id:
        raise SystemExit("Panopto LTI tool ID was not available from Canvas discovery.")
    launch = canvas.get(
        urljoin(
            canvas_api_url.rstrip("/") + "/",
            f"api/v1/courses/{course_id}/external_tools/sessionless_launch",
        ),
        params={"id": str(tool_id), "launch_type": "course_navigation"},
        timeout=30,
    )
    launch.raise_for_status()
    launch_url = launch.json().get("url")
    if not launch_url:
        raise SystemExit("Canvas sessionless_launch did not return a URL.")

    web = requests.Session()
    response = web.get(str(launch_url), timeout=30, allow_redirects=True)
    response.raise_for_status()
    for _ in range(3):
        if any(cookie.name == ".ASPXAUTH" for cookie in web.cookies):
            return web
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        if form is None:
            break
        action_value = form.get("action")
        action = urljoin(response.url, action_value if isinstance(action_value, str) else "")
        data = {}
        for input_tag in form.find_all("input"):
            name = input_tag.get("name")
            if isinstance(name, str):
                value = input_tag.get("value", "")
                data[name] = value if isinstance(value, str) else ""
        method_value = form.get("method")
        method = (method_value if isinstance(method_value, str) else "get").lower()
        if method == "post":
            response = web.post(action, data=data, timeout=30, allow_redirects=True)
        else:
            response = web.get(action, params=data, timeout=30, allow_redirects=True)
        response.raise_for_status()

    if not any(cookie.name == ".ASPXAUTH" for cookie in web.cookies):
        raise SystemExit("Canvas/Panopto LTI launch did not establish a Panopto session cookie.")
    return web


def collect_lti_sessions(
    web: WebSession,
    panopto_base_url: str,
    *,
    folder_id: str | None,
    session_ids: Iterable[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    listed: set[str] = set()
    wanted = set(session_ids or [])
    page = 0
    while len(rows) < limit:
        query: dict[str, Any] = {
            "query": None,
            "sortColumn": 1,
            "sortAscending": False,
            "maxResults": min(max(limit, 1), 50),
            "page": page,
            "startDate": None,
            "endDate": None,
        }
        if folder_id:
            query["folderID"] = folder_id
        payload = lti_get_sessions(web, panopto_base_url, query)
        page_rows = payload.get("Results") or []
        if not page_rows:
            break
        page_ids = {str(row.get("SessionID") or "") for row in page_rows}
        if page_ids <= listed:
            break
        listed |= page_ids
        for row in page_rows:
            session_id = str(row.get("SessionID") or "")
            if wanted and session_id not in wanted:
                continue
            if session_id and session_id not in seen:
                rows.append(row)
                seen.add(session_id)
                if len(rows) >= limit:
                    break
        if wanted and wanted.issubset(seen):
            break
        page += 1
    return rows[:limit]


def lti_get_sessions(
    web: WebSession, panopto_base_url: str, query_parameters: dict[str, Any]
) -> dict[str, Any]:
    endpoint = urljoin(
        panopto_base_url.rstrip("/") + "/Panopto/",
        "Services/Data.svc/GetSessions",
    )
    response = web.post(
        endpoint,
        json={"queryParameters": query_parameters},
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("d", payload)
    if not isinstance(data, dict):
        raise ValueError("Expected Panopto GetSessions object response.")
    return data


def write_caption_outputs(
    web: WebSession,
    sessions: list[dict[str, Any]],
    panopto_base_url: str,
    *,
    output_dir: Path,
    dry_run: bool,
    language: str,
    course_id: int,
    panopto_tool: dict[str, Any],
    integration_settings: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> None:
    if not sessions:
        raise SystemExit("No Panopto sessions found.")

    ensure_private_directory(output_dir)
    interrupted_bundle = not (output_dir / "artifact-manifest.json").exists()
    preflight_caption_bundle(output_dir, overwrite=overwrite)
    existing_pairs = inventory_interrupted_caption_pairs(output_dir)
    requested_ids = {
        str(session.get("SessionID") or "")
        for session in sessions
        if session.get("HasCaptions")
    }
    unexpected_sessions = sorted(set(existing_pairs) - requested_ids)
    if unexpected_sessions:
        raise SystemExit(
            "Incomplete Panopto bundle contains caption pairs for sessions outside "
            "the requested result set. Move the bundle aside and retry."
        )
    rows: list[dict[str, Any]] = []
    for session in sessions:
        record = lti_session_record(session)
        record["has_caption"] = bool(session.get("HasCaptions"))
        record["caption_path"] = ""
        record["status"] = "caption_available" if record["has_caption"] else "no_caption"
        session_id = str(record["session_id"])
        if record["has_caption"] and session_id in existing_pairs:
            record["caption_path"] = existing_pairs[session_id].path.name
            record["status"] = (
                "reused_after_interruption" if interrupted_bundle else "reused_verified"
            )
        elif record["has_caption"] and not dry_run:
            caption_path = download_lti_caption(
                web,
                panopto_base_url,
                session,
                output_dir=output_dir,
                language=language,
                overwrite=overwrite,
            )
            record["caption_path"] = caption_path.name
            record["status"] = "downloaded"
        rows.append(record)

    write_manifest(
        output_dir,
        course_id,
        panopto_base_url,
        panopto_tool,
        dry_run,
        rows,
        integration_settings=integration_settings,
        overwrite=overwrite,
    )
    downloaded = sum(row["status"] == "downloaded" for row in rows)
    reused = sum(str(row["status"]).startswith("reused_") for row in rows)
    available = sum(bool(row["has_caption"]) for row in rows)
    print(
        f"Sessions: {len(rows)}; captions available: {available}; "
        f"downloaded: {downloaded}; reused: {reused}"
    )
    print(f"Private artifact bundle: {output_dir}")


def lti_session_record(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("SessionID") or "",
        "name": session.get("SessionName") or "",
        "created_date": parse_panopto_date(session.get("StartTime")),
        "duration": session.get("Duration") or "",
        "folder_id": session.get("FolderID") or "",
        "folder_name": session.get("FolderName") or "",
    }


def download_lti_caption(
    web: WebSession,
    panopto_base_url: str,
    session: dict[str, Any],
    *,
    output_dir: Path,
    language: str,
    overwrite: bool = False,
) -> Path:
    delivery_id = session.get("DeliveryID")
    if not delivery_id:
        raise SystemExit(f"Session lacks DeliveryID: {session.get('SessionID')}")
    url = urljoin(
        panopto_base_url.rstrip("/") + "/Panopto/",
        "Pages/Transcription/GenerateSRT.ashx",
    )
    response = web.get(
        url,
        params={"id": delivery_id, "language": language, "clean": "true"},
        timeout=60,
    )
    response.raise_for_status()
    filename = caption_filename_from_response(response) or "captions.txt"
    prefix = parse_panopto_date(session.get("StartTime")) or str(session.get("SessionID") or "")
    target = output_dir / safe_filename(f"{prefix}-{filename}")
    try:
        write_private_pair(
            target,
            response.content,
            command="recordings panopto-captions",
            overwrite=overwrite,
            sidecar_fields={"session_id": session.get("SessionID") or ""},
        )
    except FileExistsError as exc:
        raise SystemExit(
            "Panopto caption filename collision inside the private bundle; "
            "danvas will not create a suffixed duplicate."
        ) from exc
    return target


def caption_filename_from_response(response: HttpResponse) -> str | None:
    disposition = response.headers.get("content-disposition", "")
    encoded_match = re.search(r"filename\*=UTF-8''([^;]+)", disposition, flags=re.IGNORECASE)
    if encoded_match:
        return unquote(encoded_match.group(1))
    match = re.search(r'filename="?([^";]+)"?', disposition)
    return unquote(match.group(1)) if match else None


def parse_panopto_date(value: Any) -> str:
    if not value:
        return ""
    match = re.search(r"/Date\(([-0-9]+)\)/", str(value))
    if not match:
        return str(value)
    timestamp_ms = int(match.group(1))
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return str(value)


def safe_filename(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    value = re.sub(r"-+", "-", value).strip("-. ")
    return value[:180]


def write_manifest(
    output_dir: Path,
    course_id: int,
    panopto_base_url: str,
    panopto_tool: dict[str, Any],
    dry_run: bool,
    rows: list[dict[str, Any]],
    *,
    integration_settings: dict[str, Any] | None,
    overwrite: bool,
) -> None:
    validate_caption_manifest_pairs(output_dir, rows)
    files = ["manifest.csv"]
    for row in rows:
        caption_path = str(row.get("caption_path") or "")
        if caption_path:
            files.extend([caption_path, f"{caption_path}.artifact.json"])
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "course_id": course_id,
        "panopto_base_url": panopto_base_url,
        "panopto_tool": {
            "id": panopto_tool.get("id"),
            "name": panopto_tool.get("name"),
        },
        "integration_settings": integration_settings or {
            "caption_language": DEFAULT_CAPTION_LANGUAGE,
            "tool_name": None,
            "tool_id": None,
            "base_url": None,
        },
        "dry_run": dry_run,
        "sessions": rows,
        "files": files,
    }
    manifest_path = output_dir / "artifact-manifest.json"
    csv_path = output_dir / "manifest.csv"
    write_private_text(
        csv_path,
        render_caption_csv(rows),
        overwrite=overwrite,
    )
    write_private_json(
        manifest_path,
        manifest,
        command="recordings panopto-captions",
        overwrite=overwrite,
    )


def render_caption_csv(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CAPTION_MANIFEST_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def preflight_caption_bundle(output_dir: Path, *, overwrite: bool) -> None:
    if output_dir.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink: {output_dir}")
    manifest_path = output_dir / "artifact-manifest.json"
    csv_path = output_dir / "manifest.csv"
    if manifest_path.is_symlink() or csv_path.is_symlink():
        raise SystemExit(f"Refusing private artifact symlink in caption bundle: {output_dir}")
    if (manifest_path.exists() and not manifest_path.is_file()) or (
        csv_path.exists() and not csv_path.is_file()
    ):
        raise SystemExit(f"Invalid manifest target in private caption bundle: {output_dir}")
    if manifest_path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing private caption bundle: {output_dir}")
    if csv_path.exists() and not manifest_path.exists():
        raise SystemExit(
            f"Incomplete Panopto bundle contains manifest.csv without its commit marker: "
            f"{output_dir}. Move the bundle aside and retry."
        )
    inventory_interrupted_caption_pairs(output_dir)


def inventory_interrupted_caption_pairs(output_dir: Path) -> dict[str, CaptionPair]:
    """Validate caption/sidecar pairs without downloading or deleting anything."""
    if not output_dir.exists():
        return {}
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise SystemExit(f"Invalid private Panopto bundle directory: {output_dir}")
    reserved = {"artifact-manifest.json", "manifest.csv"}
    entries = [entry for entry in sorted(output_dir.iterdir()) if entry.name not in reserved]
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise SystemExit("Unexpected artifact in incomplete Panopto bundle.")

    sidecars = {entry.name.removesuffix(".artifact.json"): entry for entry in entries if entry.name.endswith(".artifact.json")}
    data_files = {entry.name: entry for entry in entries if not entry.name.endswith(".artifact.json")}
    missing_sidecars = sorted(set(data_files) - set(sidecars))
    orphan_sidecars = sorted(set(sidecars) - set(data_files))
    if missing_sidecars or orphan_sidecars:
        raise SystemExit(
            "Incomplete Panopto bundle has a missing data file or sidecar; "
            "danvas will not delete or rename around it."
        )

    pairs: dict[str, CaptionPair] = {}
    for name, path in data_files.items():
        sidecar = sidecars[name]
        try:
            payload = jsonlib.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, jsonlib.JSONDecodeError) as exc:
            raise SystemExit("Invalid Panopto caption sidecar in private bundle.") from exc
        session_id = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
        valid = (
            isinstance(payload, dict)
            and payload.get("artifact_class") == "private"
            and payload.get("command") == "recordings panopto-captions"
            and payload.get("sha256") == private_file_sha256(path)
            and bool(session_id)
        )
        if not valid:
            raise SystemExit("Panopto caption pair failed integrity validation.")
        if session_id in pairs:
            raise SystemExit("Incomplete Panopto bundle contains duplicate session identity.")
        pairs[session_id] = CaptionPair(session_id=session_id, path=path, sidecar=sidecar)
    return pairs


def validate_caption_manifest_pairs(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    pairs = inventory_interrupted_caption_pairs(output_dir)
    for row in rows:
        caption_path = str(row.get("caption_path") or "")
        if not caption_path:
            continue
        session_id = str(row.get("session_id") or "")
        pair = pairs.get(session_id)
        if pair is None or pair.path.name != caption_path:
            raise SystemExit(
                "Panopto caption bundle changed before manifest commit; refusing completion."
            )
