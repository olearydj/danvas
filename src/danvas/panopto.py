"""Panopto recording/caption operations through Canvas LTI launch."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from danvas.auth import resolve_api_key
from danvas.utils import write_rows

CAPTION_MANIFEST_FIELDS = [
    "session_id",
    "name",
    "created_date",
    "duration",
    "folder_id",
    "folder_name",
    "viewer_url",
    "has_caption",
    "caption_path",
    "status",
]


def command_panopto_captions(args: Any) -> None:
    api_key, provider_name = resolve_api_key(
        provider=args.secret_provider,
        op_reference=args.op_reference,
        env_var=args.api_key_env,
    )
    print(f"Using API key from: {provider_name}")
    canvas_session = requests.Session()
    canvas_session.headers.update({"Authorization": f"Bearer {api_key}"})
    panopto_tool = discover_panopto_tool(canvas_session, args.api_url, args.course_id)
    panopto_base_url = normalize_panopto_base_url(
        args.panopto_base_url or panopto_tool.get("domain") or panopto_tool.get("url")
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
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
        language=args.caption_language,
        course_id=args.course_id,
        panopto_tool=panopto_tool,
    )


def discover_panopto_tool(
    canvas: requests.Session, canvas_api_url: str, course_id: int
) -> dict[str, Any]:
    tools = canvas_get_paginated(
        canvas,
        canvas_api_url,
        f"api/v1/courses/{course_id}/external_tools/visible_course_nav_tools",
    )
    for tool in tools:
        text = " ".join(str(tool.get(key) or "") for key in ("name", "url", "domain")).lower()
        if "panopto" in text:
            return tool

    tabs = canvas_get_paginated(canvas, canvas_api_url, f"api/v1/courses/{course_id}/tabs")
    for tab in tabs:
        text = " ".join(str(tab.get(key) or "") for key in ("label", "url", "html_url")).lower()
        if "panopto" in text:
            return {"id": external_tool_id(tab), "name": tab.get("label"), "url": tab.get("url")}

    raise SystemExit(f"No Panopto course navigation tool found for Canvas course {course_id}.")


def external_tool_id(tab: dict[str, Any]) -> int | str | None:
    tab_id = str(tab.get("id") or "")
    match = re.search(r"context_external_tool_(\d+)", tab_id)
    return int(match.group(1)) if match else tab.get("id")


def canvas_get_paginated(
    session: requests.Session, canvas_api_url: str, path: str
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
    canvas: requests.Session,
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
        action = urljoin(response.url, form.get("action") or "")
        data = {
            input_tag.get("name"): input_tag.get("value", "")
            for input_tag in form.find_all("input")
            if input_tag.get("name")
        }
        method = (form.get("method") or "get").lower()
        if method == "post":
            response = web.post(action, data=data, timeout=30, allow_redirects=True)
        else:
            response = web.get(action, params=data, timeout=30, allow_redirects=True)
        response.raise_for_status()

    if not any(cookie.name == ".ASPXAUTH" for cookie in web.cookies):
        raise SystemExit("Canvas/Panopto LTI launch did not establish a Panopto session cookie.")
    return web


def collect_lti_sessions(
    web: requests.Session,
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
    web: requests.Session, panopto_base_url: str, query_parameters: dict[str, Any]
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
    web: requests.Session,
    sessions: list[dict[str, Any]],
    panopto_base_url: str,
    *,
    output_dir: Path,
    dry_run: bool,
    language: str,
    course_id: int,
    panopto_tool: dict[str, Any],
) -> None:
    if not sessions:
        raise SystemExit("No Panopto sessions found.")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for session in sessions:
        record = lti_session_record(session)
        record["has_caption"] = bool(session.get("HasCaptions"))
        record["caption_path"] = ""
        record["status"] = "caption_available" if record["has_caption"] else "no_caption"
        if record["has_caption"] and not dry_run:
            caption_path = download_lti_caption(
                web,
                panopto_base_url,
                session,
                output_dir=output_dir,
                language=language,
            )
            record["caption_path"] = caption_path.as_posix()
            record["status"] = "downloaded"
        rows.append(record)
        print(f"{record['status']}: {record['name']} ({record['session_id']})")

    write_manifest(output_dir, course_id, panopto_base_url, panopto_tool, dry_run, rows)


def lti_session_record(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("SessionID") or "",
        "name": session.get("SessionName") or "",
        "created_date": parse_panopto_date(session.get("StartTime")),
        "duration": session.get("Duration") or "",
        "folder_id": session.get("FolderID") or "",
        "folder_name": session.get("FolderName") or "",
        "viewer_url": session.get("ViewerUrl") or "",
    }


def download_lti_caption(
    web: requests.Session,
    panopto_base_url: str,
    session: dict[str, Any],
    *,
    output_dir: Path,
    language: str,
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
    target = unique_path(output_dir / safe_filename(f"{prefix}-{filename}"))
    target.write_bytes(response.content)
    return target


def caption_filename_from_response(response: requests.Response) -> str | None:
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
    return datetime.fromtimestamp(timestamp_ms / 1000).isoformat(timespec="seconds")


def safe_filename(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    value = re.sub(r"-+", "-", value).strip("-. ")
    return value[:180]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def write_manifest(
    output_dir: Path,
    course_id: int,
    panopto_base_url: str,
    panopto_tool: dict[str, Any],
    dry_run: bool,
    rows: list[dict[str, Any]],
) -> None:
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "course_id": course_id,
        "panopto_base_url": panopto_base_url,
        "panopto_tool": {
            "id": panopto_tool.get("id"),
            "name": panopto_tool.get("name"),
            "domain": panopto_tool.get("domain"),
            "url": panopto_tool.get("url"),
        },
        "dry_run": dry_run,
        "sessions": rows,
    }
    manifest_path = output_dir / "manifest.json"
    csv_path = output_dir / "manifest.csv"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    write_rows(csv_path, rows, CAPTION_MANIFEST_FIELDS)
    print(f"Wrote {manifest_path}")
    print(f"Wrote {csv_path}")
