"""Verified local-asset deployment for authored Canvas HTML."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
from canvasapi.exceptions import ResourceDoesNotExist

from danvas.canvas_links import (
    canvas_file_reference,
    current_course_root_relative_url,
    extract_canvas_file_references,
    sensitive_query_names,
    stable_course_file_url,
)
from danvas.config import find_config_dir, load_project_config
from danvas.files import (
    content_type_for,
    files_inventory_ignore_patterns,
    plan_upload_rows,
    resolve_upload_folder,
    should_skip_local,
    upload_result_row,
    validate_upload_destination,
)
from danvas.sanitize import sanitize_error
from danvas.source_map import (
    load_source_map,
    source_path_key,
    write_source_map_entry,
)
from danvas.utils import canvas_object_to_dict

ASSET_EVIDENCE_SCHEMA = "authored-assets-v1"
ASSET_SOURCE_SUFFIXES = {".cjs", ".css", ".htm", ".html", ".js", ".markdown", ".md", ".mjs"}
IMAGE_CONTENT_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/webp",
}
SAFE_EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel"}
UNSAFE_SCHEMES = {"data", "javascript", "vbscript"}
URL_ATTRIBUTES = (
    "href",
    "src",
    "srcset",
    "poster",
    "data",
    "action",
    "formaction",
    "cite",
    "background",
    "data-api-endpoint",
    "data-download-url",
)


def prepare_asset_plan(
    html: str,
    *,
    source: Path,
    project_root: Path,
    course_id: int,
    canvas_origin: str,
    course: Any | None,
    canvas: Any | None,
    folder: str | None,
    folder_id: int | None,
    on_duplicate: str,
    verify_only: bool = False,
    canvas_loader: Callable[[], tuple[Any, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build a complete local-asset plan, or return None when no local intent exists."""
    candidates = local_intent_candidates(
        html,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    asset_options = bool(folder or folder_id is not None or on_duplicate != "error")
    if not candidates:
        if asset_options:
            raise SystemExit("Asset options were supplied, but the assignment has no local assets.")
        return None

    root = project_root.resolve()
    try:
        source.resolve().relative_to(root)
    except ValueError as exc:
        raise SystemExit("Asset-enabled assignment source must be inside the course project.") from exc
    scan = scan_authored_assets(
        html,
        source=source,
        project_root=root,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    plan: dict[str, Any] = {
        "evidence_schema": ASSET_EVIDENCE_SCHEMA,
        "status": "blocked" if scan["blocked"] else "planned",
        "course_id": course_id,
        "source": source_path_key(source, root),
        "source_body_sha256": sha256_text(html),
        "deployed_body_sha256": None,
        "destination": None,
        "assets": scan["assets"],
        "blocked": scan["blocked"],
        "rewritten_html": None,
        "mutation_status": "not_started",
        "content_mutation_status": "not_started",
        "evidence_status": "not_started",
        "verification_status": "not_checked",
        "_source_html": html,
        "_source_path": source.resolve(),
        "_project_root": root,
        "_source_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    if scan["blocked"]:
        return plan
    require_asset_project(root, course_id)
    if course is None:
        if canvas_loader is None:
            raise SystemExit("Canvas course access is required to plan local assignment assets.")
        canvas, course = canvas_loader()
        plan["_resolved_canvas"] = canvas
        plan["_resolved_course"] = course

    source_map = load_source_map(root)
    mapped_course_id = source_map.get("course_id")
    if mapped_course_id is not None and int(mapped_course_id) != int(course_id):
        raise SystemExit(
            f"Source-map course {mapped_course_id} does not match target course {course_id}."
        )
    resolved_folder = None
    if folder or folder_id is not None:
        validate_upload_destination(folder, folder_id)
        if canvas is None:
            raise SystemExit("Canvas access is required to resolve the asset folder.")
        resolved_folder = resolve_upload_folder(
            canvas,
            course,
            folder=folder,
            folder_id=folder_id,
        )
        plan["destination"] = safe_folder_record(resolved_folder)
        plan["_folder"] = resolved_folder

    upload_candidates: list[dict[str, Any]] = []
    for asset in plan["assets"]:
        mapped = mapped_file_record(source_map, asset, course_id=course_id)
        asset["mapping"] = mapped
        if mapped["status"] == "valid":
            checked = validate_mapped_file(
                course,
                mapped,
                expected_folder_id=(
                    int(resolved_folder.id) if resolved_folder is not None else None
                ),
            )
            if checked["status"] == "valid":
                asset.update(
                    {
                        "status": "would_reuse",
                        "reason": "mapped_identity_and_local_hash_match",
                        "canvas": checked["canvas"],
                    }
                )
                continue
            if checked["status"] != "not_found":
                asset.update({"status": "conflict", "reason": checked["reason"]})
                continue
        elif mapped["status"] not in {"missing", "hash_changed"}:
            asset.update({"status": "conflict", "reason": mapped["reason"]})
            continue

        if verify_only:
            asset.update(
                {
                    "status": "conflict",
                    "reason": (
                        "local_hash_changed"
                        if mapped["status"] == "hash_changed"
                        else "asset_identity_not_available"
                    ),
                }
            )
            continue
        if resolved_folder is None:
            asset.update({"status": "blocked", "reason": "asset_destination_required"})
            continue
        if mapped["status"] == "hash_changed" and on_duplicate != "rename":
            asset.update({"status": "conflict", "reason": "local_hash_changed"})
            continue
        upload_candidates.append(asset_upload_row(asset))

    if upload_candidates and resolved_folder is not None:
        rows = plan_upload_rows(
            upload_candidates,
            resolved_folder,
            on_duplicate=on_duplicate,
        )
        by_path = {str(row["relative_path"]): row for row in rows}
        for asset in plan["assets"]:
            row = by_path.get(str(asset["path"]))
            if row is None:
                continue
            status = row["status"]
            asset["status"] = {
                "would_create": "would_upload",
                "would_rename": "would_rename",
            }.get(status, "conflict")
            asset["reason"] = str(row.get("reason") or "")
            asset["existing_canvas_ids"] = list(row.get("existing_canvas_ids") or [])

    failing = [asset for asset in plan["assets"] if asset.get("status") in {"blocked", "conflict"}]
    if failing:
        plan["status"] = "blocked"
        return plan
    if all(asset.get("status") == "would_reuse" for asset in plan["assets"]):
        plan["status"] = "would_reuse"
        rewritten = rewrite_authored_html(html, plan["assets"], course_id, canvas_origin)
        plan["rewritten_html"] = rewritten
        plan["deployed_body_sha256"] = sha256_text(rewritten)
    return plan


def local_intent_candidates(
    html: str,
    *,
    current_course_id: int,
    canvas_origin: str,
) -> list[dict[str, str]]:
    """Return URL-bearing elements that require local-asset classification."""
    soup = BeautifulSoup(str(html or ""), "html.parser")
    rows: list[dict[str, str]] = []
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attribute in URL_ATTRIBUTES:
            raw = tag.get(attribute)
            if not isinstance(raw, str) or not raw.strip():
                continue
            if url_needs_local_classification(
                raw,
                current_course_id=current_course_id,
                canvas_origin=canvas_origin,
            ):
                rows.append({"tag": str(tag.name), "attribute": attribute, "value": raw})
    return rows


def url_needs_local_classification(
    value: str,
    *,
    current_course_id: int,
    canvas_origin: str,
) -> bool:
    parsed_file = canvas_file_reference(
        value,
        current_course_id=current_course_id,
        canvas_origin=canvas_origin,
    )
    if parsed_file is not None:
        return parsed_file.get("status") != "valid" or bool(
            parsed_file.get("volatile_query_present")
        )
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return True
    scheme = parsed.scheme.casefold()
    if parsed.username or parsed.password or sensitive_query_names(parsed.query):
        return True
    if scheme in SAFE_EXTERNAL_SCHEMES:
        return not (scheme not in {"http", "https"} or bool(parsed.netloc))
    if scheme:
        return True
    if parsed.netloc:
        return False
    if not parsed.path:
        return False
    if current_course_root_relative_url(value, current_course_id=current_course_id):
        return False
    return not bool(scheme)


def scan_authored_assets(
    html: str,
    *,
    source: Path,
    project_root: Path,
    current_course_id: int,
    canvas_origin: str,
) -> dict[str, Any]:
    """Resolve every local assignment URL structurally and fail closed."""
    soup = BeautifulSoup(str(html or ""), "html.parser")
    assets_by_path: dict[str, dict[str, Any]] = {}
    blocked: list[dict[str, Any]] = []
    url_position = 0
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attribute in URL_ATTRIBUTES:
            raw = tag.get(attribute)
            if not isinstance(raw, str) or not raw.strip():
                continue
            url_position += 1
            if not url_needs_local_classification(
                raw,
                current_course_id=current_course_id,
                canvas_origin=canvas_origin,
            ):
                continue
            classified = classify_local_reference(
                raw,
                tag=str(tag.name),
                attribute=attribute,
                source=source,
                project_root=project_root,
                occurrence=url_position,
                current_course_id=current_course_id,
                canvas_origin=canvas_origin,
            )
            if classified["status"] != "local_asset":
                blocked.append(classified)
                continue
            path_key = str(classified["path"])
            asset = assets_by_path.get(path_key)
            if asset is None:
                asset = {
                    key: classified[key]
                    for key in (
                        "path",
                        "source_path",
                        "sha256",
                        "size",
                        "content_type",
                        "name",
                    )
                }
                asset["occurrences"] = []
                assets_by_path[path_key] = asset
            asset["occurrences"].append(
                {
                    "occurrence": classified["occurrence"],
                    "tag": classified["tag"],
                    "attribute": classified["attribute"],
                    "fragment": classified.get("fragment") or "",
                }
            )
    assets = sorted(assets_by_path.values(), key=lambda row: str(row["path"]))
    for asset in assets:
        asset["occurrence_count"] = len(asset["occurrences"])
    return {"assets": assets, "blocked": blocked}


def classify_local_reference(
    value: str,
    *,
    tag: str,
    attribute: str,
    source: Path,
    project_root: Path,
    occurrence: int,
    current_course_id: int,
    canvas_origin: str,
) -> dict[str, Any]:
    base = {
        "tag": tag,
        "attribute": attribute,
        "occurrence": occurrence,
        "value_sha256": sha256_text(value),
    }
    parsed_file = canvas_file_reference(
        value,
        current_course_id=current_course_id,
        canvas_origin=canvas_origin,
    )
    if parsed_file is not None:
        if parsed_file.get("volatile_query_present"):
            return {
                **base,
                "status": "blocked",
                "reason": "volatile_canvas_file_url",
            }
        return {
            **base,
            "status": "blocked",
            "reason": str(parsed_file.get("reason") or parsed_file.get("status")),
        }
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return {**base, "status": "blocked", "reason": "malformed_url"}
    scheme = parsed.scheme.casefold()
    if (
        parsed.username
        or parsed.password
        or sensitive_query_names(parsed.query)
        or scheme in UNSAFE_SCHEMES
        or (scheme and scheme not in SAFE_EXTERNAL_SCHEMES)
        or (scheme in {"http", "https"} and not parsed.netloc)
    ):
        return {**base, "status": "blocked", "reason": "unsafe_url_scheme"}
    if parsed.path.startswith("/"):
        return {**base, "status": "blocked", "reason": "blocked_root_relative"}
    if parsed.query:
        return {**base, "status": "blocked", "reason": "local_query_not_supported"}
    if (
        tag not in {"a", "img"}
        or (tag == "a" and attribute != "href")
        or (tag == "img" and attribute != "src")
    ):
        return {**base, "status": "blocked", "reason": "unsupported_local_attribute"}
    candidate = (source.parent / unquote(parsed.path)).resolve()
    try:
        relative = candidate.relative_to(project_root.resolve())
    except ValueError:
        return {**base, "status": "blocked", "reason": "path_outside_project"}
    if should_skip_local(
        candidate,
        project_root.resolve(),
        ignore_patterns=files_inventory_ignore_patterns(project_root),
    ):
        return {**base, "status": "blocked", "reason": "private_or_ignored_path"}
    if not candidate.exists():
        return {
            **base,
            "status": "blocked",
            "reason": "asset_missing",
            "path": relative.as_posix(),
        }
    if not candidate.is_file():
        return {**base, "status": "blocked", "reason": "asset_not_regular_file"}
    try:
        payload = candidate.read_bytes()
    except OSError:
        return {**base, "status": "blocked", "reason": "asset_not_readable"}
    if candidate.suffix.casefold() in ASSET_SOURCE_SUFFIXES:
        return {
            **base,
            "status": "blocked",
            "reason": "authored_source_not_uploadable",
            "path": relative.as_posix(),
        }
    content_type = content_type_for(candidate)
    if tag == "img" and content_type not in IMAGE_CONTENT_TYPES:
        return {
            **base,
            "status": "blocked",
            "reason": "image_content_type_not_supported",
            "path": relative.as_posix(),
        }
    return {
        **base,
        "status": "local_asset",
        "reason": "",
        "path": relative.as_posix(),
        "source_path": str(candidate),
        "name": candidate.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "content_type": content_type,
        "fragment": parsed.fragment,
    }


def execute_asset_plan(
    plan: dict[str, Any],
    *,
    folder: Any,
    course_id: int,
    canvas_origin: str,
    command: str,
    project_root: Path,
    on_duplicate: str,
) -> dict[str, Any]:
    """Upload planned assets, recording each identity before the next mutation."""
    source_path = Path(str(plan["_source_path"]))
    try:
        current_source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    except OSError:
        current_source_sha256 = ""
    rescanned = scan_authored_assets(
        str(plan["_source_html"]),
        source=source_path,
        project_root=Path(str(plan["_project_root"])),
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    if (
        current_source_sha256 != plan["_source_file_sha256"]
        or rescanned["blocked"]
        or asset_plan_signature(rescanned["assets"])
        != asset_plan_signature(plan["assets"])
    ):
        plan["status"] = "failed"
        plan["mutation_status"] = "not_started"
        plan["evidence_status"] = "complete"
        plan["recovery_guidance"] = (
            "Local source or asset bytes changed after planning. Re-run the command to build "
            "a fresh plan."
        )
        return plan
    plan["mutation_status"] = "in_progress"
    plan["evidence_status"] = "in_progress"
    for asset in plan["assets"]:
        if asset["status"] == "would_reuse":
            asset["status"] = "reused"
            continue
        if not current_asset_matches(asset):
            asset.update(
                {
                    "status": "failed",
                    "mutation_status": "not_started",
                    "evidence_status": "complete",
                    "reason": "local_asset_changed_after_plan",
                }
            )
            plan["status"] = "failed"
            plan["mutation_status"] = "partial" if any_mutated(plan) else "not_started"
            plan["evidence_status"] = "complete"
            plan["recovery_guidance"] = "Re-run the command to build a fresh asset plan."
            return plan
        latest = plan_upload_rows(
            [asset_upload_row(asset)],
            folder,
            on_duplicate=on_duplicate,
        )[0]
        expected = "would_rename" if asset["status"] == "would_rename" else "would_create"
        if latest["status"] != expected:
            asset.update(
                {
                    "status": "failed",
                    "mutation_status": "not_started",
                    "evidence_status": "complete",
                    "reason": "destination_changed_after_plan",
                    "existing_canvas_ids": latest.get("existing_canvas_ids") or [],
                }
            )
            plan["status"] = "failed"
            plan["mutation_status"] = "partial" if any_mutated(plan) else "not_started"
            plan["evidence_status"] = "complete"
            return plan
        upload_mode = "rename"
        try:
            ok, response = folder.upload(
                str(asset["source_path"]),
                on_duplicate=upload_mode,
                content_type=str(asset["content_type"]),
            )
        except Exception as exc:  # noqa: BLE001 - retained evidence is sanitized.
            ok = False
            response = {"error": sanitize_error(f"{type(exc).__name__}: {exc}")}
        result = upload_result_row(
            asset_upload_row(asset),
            ok=bool(ok),
            response=response,
            folder=folder,
            course_id=course_id,
            canvas_origin=canvas_origin,
        )
        asset["mutation_status"] = result["mutation_status"]
        asset["evidence_status"] = result["evidence_status"]
        if result["mutation_status"] != "succeeded":
            asset["status"] = str(result["status"])
            asset["reason"] = str(result.get("error") or "upload_failed")
            plan["status"] = str(result["status"])
            plan["mutation_status"] = "partial" if any_mutated(plan) else str(result["status"])
            plan["evidence_status"] = str(result["evidence_status"])
            if result["mutation_status"] == "indeterminate":
                plan["recovery_guidance"] = (
                    "Verify Canvas Files before retrying; the upload outcome is indeterminate."
                )
            return plan
        returned_name = str(result.get("display_name") or result.get("filename") or "")
        unexpected_rename = on_duplicate == "error" and returned_name != str(asset["name"])
        asset["status"] = (
            "renamed"
            if result["status"] == "uploaded" and returned_name != str(asset["name"])
            else "uploaded"
        )
        asset["canvas"] = {
            "course_id": course_id,
            "id": int(result["canvas_id"]),
            "folder_id": result.get("folder_id"),
            "path": result.get("canvas_path") or "",
            "url": result.get("canvas_url") or "",
            "display_name": returned_name,
        }
        try:
            write_source_map_entry(
                kind="file",
                source=Path(str(asset["source_path"])),
                course_id=course_id,
                canvas=asset["canvas"],
                command=command,
                fields={
                    "sha256": asset["sha256"],
                    "size": asset["size"],
                    "content_type": asset["content_type"],
                    "upload_name": returned_name,
                },
                project_root=project_root,
            )
        except Exception as exc:  # noqa: BLE001 - identity is still retained in memory.
            asset["evidence_status"] = "failed"
            asset["reason"] = f"source_map_write_{type(exc).__name__}"
            plan["status"] = "failed"
            plan["mutation_status"] = "partial"
            plan["evidence_status"] = "failed"
            plan["recovery_guidance"] = (
                "Do not retry the upload. Preserve the reported Canvas file identity and "
                "repair source-map evidence first."
            )
            return plan
        if result["evidence_status"] != "complete":
            asset["reason"] = "stable_file_evidence_incomplete"
            plan["status"] = "indeterminate"
            plan["mutation_status"] = "partial"
            plan["evidence_status"] = str(result["evidence_status"])
            plan["recovery_guidance"] = (
                "Do not retry the upload. Reconstruct stable evidence from the recorded file ID."
            )
            return plan
        if unexpected_rename:
            asset["reason"] = "unexpected_rename_after_race"
            plan["status"] = "failed"
            plan["mutation_status"] = "partial"
            plan["evidence_status"] = "complete"
            return plan

    rewritten = rewrite_authored_html(
        str(plan["_source_html"]), plan["assets"], course_id, canvas_origin
    )
    plan["rewritten_html"] = rewritten
    plan["deployed_body_sha256"] = sha256_text(rewritten)
    plan["status"] = "deployed"
    plan["mutation_status"] = "succeeded" if any_mutated(plan) else "not_needed"
    plan["evidence_status"] = "complete"
    return plan


def rewrite_authored_html(
    html: str,
    assets: list[dict[str, Any]],
    course_id: int,
    canvas_origin: str,
) -> str:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    by_occurrence: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for asset in assets:
        for occurrence in asset.get("occurrences") or []:
            by_occurrence[int(occurrence["occurrence"])] = (asset, occurrence)
    current = 0
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attribute in URL_ATTRIBUTES:
            raw = tag.get(attribute)
            if not isinstance(raw, str) or not raw.strip():
                continue
            current += 1
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
                continue
            item = by_occurrence.get(current)
            if item is None:
                continue
            asset, occurrence = item
            canvas = asset.get("canvas") or {}
            file_id = int(canvas["id"])
            fragment = str(occurrence.get("fragment") or "")
            if tag.name == "img" and attribute == "src":
                target = f"/courses/{course_id}/files/{file_id}/preview"
            else:
                target = stable_course_file_url(canvas_origin, course_id, file_id)
            tag[attribute] = (
                urlunsplit(("", "", target, "", fragment))
                if target.startswith("/")
                else (target + (f"#{fragment}" if fragment else ""))
            )
    return str(soup)


def verify_asset_readback(
    assets: list[dict[str, Any]],
    canvas_html: str,
    *,
    expected_html: str,
    course: Any,
    course_id: int,
    canvas_origin: str,
) -> dict[str, Any]:
    expected_references = extract_canvas_file_references(
        expected_html,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    expected = Counter(
        (int(row["file_id"]), str(row["tag"]))
        for row in expected_references
        if row.get("status") == "valid" and row.get("file_id") is not None
    )
    expected_invalid = [
        row
        for row in expected_references
        if row.get("status") != "valid" or row.get("volatile_query_present")
    ]
    extracted = extract_canvas_file_references(
        canvas_html,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    actual = Counter(
        (int(row["file_id"]), str(row["tag"]))
        for row in extracted
        if row.get("status") == "valid" and row.get("file_id") is not None
    )
    invalid = [
        row
        for row in extracted
        if row.get("status") != "valid" or row.get("volatile_query_present")
    ]
    files = []
    mismatch = expected != actual or bool(invalid) or bool(expected_invalid)
    expected_folders = {
        int(canvas["id"]): int(canvas["folder_id"])
        for asset in assets
        if isinstance((canvas := asset.get("canvas")), dict)
        and canvas.get("id") is not None
        and canvas.get("folder_id") is not None
    }
    for file_id in sorted({key[0] for key in expected}):
        try:
            file_obj = course.get_file(file_id)
        except ResourceDoesNotExist:
            files.append({"file_id": file_id, "status": "not_found"})
            mismatch = True
        except Exception as exc:  # noqa: BLE001 - bounded sanitized readback evidence.
            files.append(
                {
                    "file_id": file_id,
                    "status": "indeterminate",
                    "reason": sanitize_error(type(exc).__name__),
                }
            )
            mismatch = True
        else:
            payload = canvas_object_to_dict(file_obj)
            folder_id = payload.get("folder_id", getattr(file_obj, "folder_id", None))
            status = "exists"
            if file_id in expected_folders and (
                folder_id is None or int(folder_id) != expected_folders[file_id]
            ):
                status = "folder_mismatch"
                mismatch = True
            files.append(
                {
                    "file_id": file_id,
                    "status": status,
                    "folder_id": folder_id,
                }
            )
    return {
        "status": "mismatch" if mismatch else "matches",
        "expected": counter_rows(expected),
        "actual": counter_rows(actual),
        "invalid": [safe_reference(row) for row in invalid],
        "expected_invalid": [safe_reference(row) for row in expected_invalid],
        "files": files,
        "remote_bytes_match": "not_checked",
    }


def require_asset_project(project_root: Path, course_id: int) -> Path:
    root = project_root.resolve()
    config_dir = find_config_dir(root)
    if config_dir is None or config_dir.parent != root:
        raise SystemExit(
            "Local asset deployment requires an initialized .danvas project at "
            f"{root}. Pass --project-root for the course project."
        )
    configured = (load_project_config(root).get("canvas") or {}).get("course_id")
    if configured is None or int(configured) != int(course_id):
        raise SystemExit(
            f"Asset project course {configured!r} does not match target course {course_id}."
        )
    return root


def mapped_file_record(
    source_map: dict[str, Any], asset: dict[str, Any], *, course_id: int
) -> dict[str, Any]:
    entries = [
        entry
        for entry in source_map.get("sources") or []
        if isinstance(entry, dict)
        and entry.get("kind") == "file"
        and entry.get("path") == str(asset["path"])
    ]
    if not entries:
        return {"status": "missing", "reason": "file_source_map_entry_missing"}
    if len(entries) != 1:
        return {"status": "invalid", "reason": "duplicate_file_source_map_entries"}
    entry = entries[0]
    canvas = entry.get("canvas") if isinstance(entry, dict) else None
    posted = entry.get("last_posted") if isinstance(entry, dict) else None
    fields = posted.get("fields") if isinstance(posted, dict) else None
    if not isinstance(canvas, dict) or not isinstance(fields, dict):
        return {"status": "invalid", "reason": "file_source_map_entry_malformed"}
    if canvas.get("course_id") is None:
        return {"status": "invalid", "reason": "file_entry_course_id_missing"}
    if int(canvas["course_id"]) != int(course_id):
        return {"status": "invalid", "reason": "file_entry_course_mismatch"}
    if str(fields.get("sha256") or "") != str(asset["sha256"]):
        return {"status": "hash_changed", "reason": "local_hash_changed", "canvas": canvas}
    if canvas.get("id") is None:
        return {"status": "invalid", "reason": "file_entry_canvas_id_missing"}
    return {"status": "valid", "reason": "", "canvas": canvas, "fields": fields}


def validate_mapped_file(
    course: Any,
    mapped: dict[str, Any],
    *,
    expected_folder_id: int | None,
) -> dict[str, Any]:
    canvas = dict(mapped["canvas"])
    try:
        file_obj = course.get_file(int(canvas["id"]))
    except ResourceDoesNotExist:
        return {"status": "not_found", "reason": "mapped_canvas_file_not_found"}
    except Exception as exc:  # noqa: BLE001 - bounded lookup classification.
        return {
            "status": "indeterminate",
            "reason": sanitize_error(f"mapped_file_lookup_{type(exc).__name__}"),
        }
    payload = canvas_object_to_dict(file_obj)
    folder_id = payload.get("folder_id", getattr(file_obj, "folder_id", None))
    if expected_folder_id is not None and (
        folder_id is None or int(folder_id) != int(expected_folder_id)
    ):
        return {"status": "conflict", "reason": "mapped_file_folder_mismatch"}
    canvas["folder_id"] = folder_id
    return {"status": "valid", "reason": "", "canvas": canvas}


def safe_folder_record(folder: Any) -> dict[str, Any]:
    return {
        "id": getattr(folder, "id", None),
        "full_name": str(getattr(folder, "full_name", "") or ""),
    }


def asset_upload_row(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": str(asset["source_path"]),
        "relative_path": str(asset["path"]),
        "name": str(asset["name"]),
        "size": int(asset["size"]),
        "content_type": str(asset["content_type"]),
    }


def any_mutated(plan: dict[str, Any]) -> bool:
    return any(
        asset.get("mutation_status") == "succeeded"
        or asset.get("status") in {"uploaded", "renamed"}
        for asset in plan.get("assets") or []
    )


def asset_plan_signature(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return local intent fields that must remain stable between plan and mutation."""
    return [
        {
            "path": asset.get("path"),
            "sha256": asset.get("sha256"),
            "size": asset.get("size"),
            "content_type": asset.get("content_type"),
            "name": asset.get("name"),
            "occurrences": asset.get("occurrences") or [],
        }
        for asset in assets
    ]


def current_asset_matches(asset: dict[str, Any]) -> bool:
    try:
        payload = Path(str(asset["source_path"])).read_bytes()
    except OSError:
        return False
    return len(payload) == int(asset["size"]) and hashlib.sha256(payload).hexdigest() == str(
        asset["sha256"]
    )


def asset_associations(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not plan:
        return []
    rows = []
    for asset in plan.get("assets") or []:
        canvas = asset.get("canvas") or {}
        if canvas.get("id") is None:
            continue
        rows.append(
            {
                "path": asset["path"],
                "sha256": asset["sha256"],
                "canvas_file_id": int(canvas["id"]),
                "course_id": int(canvas["course_id"]),
                "occurrences": [
                    {
                        "tag": row["tag"],
                        "attribute": row["attribute"],
                        "link_profile": (
                            "image_preview"
                            if row["tag"] == "img" and row["attribute"] == "src"
                            else "course_file_view"
                        ),
                        "fragment": row.get("fragment") or "",
                    }
                    for row in asset.get("occurrences") or []
                ],
                "occurrence_count": int(asset.get("occurrence_count") or 0),
            }
        )
    return rows


def public_asset_evidence(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return None
    deployed_body_status = (
        "pending_canvas_file_ids"
        if plan.get("rewritten_html") is None
        and any(
            asset.get("status") in {"would_upload", "would_rename"}
            for asset in plan.get("assets") or []
        )
        else "available"
        if plan.get("rewritten_html") is not None
        else "not_available"
    )
    return {
        "evidence_schema": ASSET_EVIDENCE_SCHEMA,
        "status": plan["status"],
        "course_id": plan["course_id"],
        "source": plan["source"],
        "source_body_sha256": plan["source_body_sha256"],
        "deployed_body_sha256": plan.get("deployed_body_sha256"),
        "deployed_body_status": deployed_body_status,
        "destination": plan.get("destination"),
        "mutation_status": plan.get("mutation_status"),
        "content_mutation_status": plan.get("content_mutation_status"),
        "evidence_status": plan.get("evidence_status"),
        "verification_status": plan.get("verification_status"),
        "verification": safe_verification(plan.get("verification")),
        "content_error": plan.get("content_error"),
        "verification_error": plan.get("verification_error"),
        "recovery_guidance": plan.get("recovery_guidance"),
        "assets": [safe_asset_row(asset) for asset in plan.get("assets") or []],
        "blocked": [safe_reference(row) for row in plan.get("blocked") or []],
    }


def safe_asset_row(asset: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "path",
        "sha256",
        "size",
        "content_type",
        "name",
        "occurrence_count",
        "status",
        "reason",
        "existing_canvas_ids",
        "mutation_status",
        "evidence_status",
        "canvas",
    }
    row = {key: asset[key] for key in allowed if key in asset}
    row["occurrences"] = [
        {
            "tag": item["tag"],
            "attribute": item["attribute"],
            "fragment": item.get("fragment") or "",
        }
        for item in asset.get("occurrences") or []
    ]
    return row


def safe_reference(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "status",
            "reason",
            "path",
            "tag",
            "attribute",
            "occurrence",
            "value_sha256",
            "volatile_query_present",
            "volatile_query_names",
        )
        if key in row
    }


def safe_verification(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value[key]
        for key in (
            "status",
            "expected",
            "actual",
            "invalid",
            "expected_invalid",
            "files",
            "remote_bytes_match",
        )
        if key in value
    }


def counter_rows(counter: Counter[tuple[int, str]]) -> list[dict[str, Any]]:
    return [
        {"file_id": file_id, "tag": tag, "count": count}
        for (file_id, tag), count in sorted(counter.items())
    ]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
