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

from danvas.asset_state import (
    AssetDestination,
    AssetItem,
    AssetPlan,
    AssetPublicEvidence,
    AssetRuntime,
    AssetTransitionResult,
    AssetVerification,
)
from danvas.canvas_links import (
    canvas_file_reference,
    current_course_root_relative_url,
    extract_canvas_file_references,
    sensitive_query_names,
    stable_course_file_url,
)
from danvas.files import (
    content_type_for,
    files_inventory_ignore_patterns,
    plan_upload_rows,
    resolve_upload_folder,
    should_skip_local,
    upload_result_row,
    validate_upload_destination,
)
from danvas.project_config import find_config_dir, load_project_config
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
) -> AssetPlan | None:
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
    require_source_in_project(source, root)
    scan = scan_authored_assets(
        html,
        source=source,
        project_root=root,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    plan = initial_asset_plan(
        html,
        source=source,
        project_root=root,
        course_id=course_id,
        canvas_origin=canvas_origin,
        scan=scan,
        canvas=canvas,
        course=course,
    )
    if plan.status == "blocked":
        return plan

    source_map = validated_plan_source_map(root, course_id)
    canvas, course = resolve_plan_course(plan, canvas_loader)
    resolved_folder = resolve_plan_destination(
        plan,
        canvas=canvas,
        course=course,
        folder=folder,
        folder_id=folder_id,
    )
    upload_candidates = [
        row
        for asset in plan.assets
        if (
            row := plan_asset_item(
                asset,
                source_map=source_map,
                course=course,
                course_id=course_id,
                resolved_folder=resolved_folder,
                verify_only=verify_only,
                on_duplicate=on_duplicate,
            )
        )
        is not None
    ]
    apply_upload_plan(plan, upload_candidates, resolved_folder, on_duplicate=on_duplicate)
    finalize_asset_plan(plan, html, course_id=course_id, canvas_origin=canvas_origin)
    return plan


def require_source_in_project(source: Path, project_root: Path) -> None:
    try:
        source.resolve().relative_to(project_root)
    except ValueError as exc:
        raise SystemExit("Asset-enabled assignment source must be inside the course project.") from exc


def initial_asset_plan(
    html: str,
    *,
    source: Path,
    project_root: Path,
    course_id: int,
    canvas_origin: str,
    scan: dict[str, Any],
    canvas: Any | None,
    course: Any | None,
) -> AssetPlan:
    return AssetPlan(
        evidence_schema=ASSET_EVIDENCE_SCHEMA,
        status="blocked" if scan["blocked"] else "planned",
        course_id=course_id,
        source=source_path_key(source, project_root),
        source_body_sha256=sha256_text(html),
        assets=[AssetItem.from_scan_record(row) for row in scan["assets"]],
        blocked=scan["blocked"],
        runtime=AssetRuntime(
            source_html=html,
            source_path=source.resolve(),
            project_root=project_root,
            source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            canvas_origin=canvas_origin,
            canvas=canvas,
            course=course,
        ),
    )


def resolve_plan_course(
    plan: AssetPlan,
    canvas_loader: Callable[[], tuple[Any, Any]] | None,
) -> tuple[Any | None, Any]:
    canvas = plan.runtime.canvas
    course = plan.runtime.course
    if course is None:
        if canvas_loader is None:
            raise SystemExit("Canvas course access is required to plan local assignment assets.")
        canvas, course = canvas_loader()
        plan.runtime.canvas = canvas
        plan.runtime.course = course
    return canvas, course


def validated_plan_source_map(project_root: Path, course_id: int) -> dict[str, Any]:
    require_asset_project(project_root, course_id)
    source_map = load_source_map(project_root)
    mapped_course_id = source_map.get("course_id")
    if mapped_course_id is not None and int(mapped_course_id) != int(course_id):
        raise SystemExit(
            f"Source-map course {mapped_course_id} does not match target course {course_id}."
        )
    return source_map


def resolve_plan_destination(
    plan: AssetPlan,
    *,
    canvas: Any | None,
    course: Any,
    folder: str | None,
    folder_id: int | None,
) -> Any | None:
    if not folder and folder_id is None:
        return None
    validate_upload_destination(folder, folder_id)
    if canvas is None:
        raise SystemExit("Canvas access is required to resolve the asset folder.")
    resolved = resolve_upload_folder(
        canvas,
        course,
        folder=folder,
        folder_id=folder_id,
    )
    plan.destination = safe_folder_record(resolved)
    plan.runtime.folder = resolved
    return resolved


def plan_asset_item(
    asset: AssetItem,
    *,
    source_map: dict[str, Any],
    course: Any,
    course_id: int,
    resolved_folder: Any | None,
    verify_only: bool,
    on_duplicate: str,
) -> dict[str, Any] | None:
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
            return None
        if checked["status"] != "not_found":
            asset.update({"status": "conflict", "reason": checked["reason"]})
            return None
    elif mapped["status"] not in {"missing", "hash_changed"}:
        asset.update({"status": "conflict", "reason": mapped["reason"]})
        return None

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
        return None
    if resolved_folder is None:
        asset.update({"status": "blocked", "reason": "asset_destination_required"})
        return None
    if mapped["status"] == "hash_changed" and on_duplicate != "rename":
        asset.update({"status": "conflict", "reason": "local_hash_changed"})
        return None
    return asset_upload_row(asset)


def apply_upload_plan(
    plan: AssetPlan,
    upload_candidates: list[dict[str, Any]],
    resolved_folder: Any | None,
    *,
    on_duplicate: str,
) -> None:
    if not upload_candidates or resolved_folder is None:
        return
    rows = plan_upload_rows(
        upload_candidates,
        resolved_folder,
        on_duplicate=on_duplicate,
    )
    by_path = {str(row["relative_path"]): row for row in rows}
    for asset in plan.assets:
        row = by_path.get(asset.local.path)
        if row is None:
            continue
        asset["status"] = {
            "would_create": "would_upload",
            "would_rename": "would_rename",
        }.get(row["status"], "conflict")
        asset["reason"] = str(row.get("reason") or "")
        asset["existing_canvas_ids"] = list(row.get("existing_canvas_ids") or [])


def finalize_asset_plan(
    plan: AssetPlan,
    html: str,
    *,
    course_id: int,
    canvas_origin: str,
) -> None:
    if any(asset.status in {"blocked", "conflict"} for asset in plan.assets):
        plan["status"] = "blocked"
        return
    if all(asset.status == "would_reuse" for asset in plan.assets):
        plan["status"] = "would_reuse"
        rewritten = rewrite_authored_html(html, plan.assets, course_id, canvas_origin)
        plan.rewritten_html = rewritten
        plan.deployed_body_sha256 = sha256_text(rewritten)


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
    plan: AssetPlan,
    *,
    folder: Any,
    course_id: int,
    canvas_origin: str,
    command: str,
    project_root: Path,
    on_duplicate: str,
) -> AssetPlan:
    """Upload planned assets, recording each identity before the next mutation."""
    if not planned_source_is_current(
        plan,
        course_id=course_id,
        canvas_origin=canvas_origin,
    ):
        mark_stale_plan(plan)
        return plan

    plan.mutation_status = "in_progress"
    plan.evidence_status = "in_progress"
    for asset in plan.assets:
        transition = execute_asset_item(
            plan,
            asset,
            folder=folder,
            course_id=course_id,
            canvas_origin=canvas_origin,
            command=command,
            project_root=project_root,
            on_duplicate=on_duplicate,
        )
        if transition.stop:
            return plan
    finalize_deployed_plan(plan, course_id=course_id, canvas_origin=canvas_origin)
    return plan


def planned_source_is_current(
    plan: AssetPlan,
    *,
    course_id: int,
    canvas_origin: str,
) -> bool:
    try:
        current_source_sha256 = hashlib.sha256(plan.runtime.source_path.read_bytes()).hexdigest()
    except OSError:
        current_source_sha256 = ""
    rescanned = scan_authored_assets(
        plan.runtime.source_html,
        source=plan.runtime.source_path,
        project_root=plan.runtime.project_root,
        current_course_id=course_id,
        canvas_origin=canvas_origin,
    )
    return (
        current_source_sha256 == plan.runtime.source_file_sha256
        and not rescanned["blocked"]
        and asset_plan_signature(rescanned["assets"]) == asset_plan_signature(plan.assets)
    )


def mark_stale_plan(plan: AssetPlan) -> None:
    plan["status"] = "failed"
    plan.mutation_status = "not_started"
    plan.evidence_status = "complete"
    plan.recovery_guidance = (
        "Local source or asset bytes changed after planning. Re-run the command to build "
        "a fresh plan."
    )


def execute_asset_item(
    plan: AssetPlan,
    asset: AssetItem,
    *,
    folder: Any,
    course_id: int,
    canvas_origin: str,
    command: str,
    project_root: Path,
    on_duplicate: str,
) -> AssetTransitionResult:
    if asset.status == "would_reuse":
        asset["status"] = "reused"
        return AssetTransitionResult(stop=False)
    if not current_asset_matches(asset):
        mark_changed_asset(plan, asset)
        return AssetTransitionResult(stop=True, reason=asset.reason)

    latest = plan_upload_rows(
        [asset_upload_row(asset)],
        folder,
        on_duplicate=on_duplicate,
    )[0]
    expected = "would_rename" if asset.status == "would_rename" else "would_create"
    if latest["status"] != expected:
        mark_changed_destination(plan, asset, latest)
        return AssetTransitionResult(stop=True, reason=asset.reason)

    result = upload_one_asset(
        asset,
        folder=folder,
        course_id=course_id,
        canvas_origin=canvas_origin,
    )
    asset["mutation_status"] = result["mutation_status"]
    asset["evidence_status"] = result["evidence_status"]
    if result["mutation_status"] != "succeeded":
        mark_upload_failure(plan, asset, result)
        return AssetTransitionResult(stop=True, reason=asset.reason)

    returned_name = str(result.get("display_name") or result.get("filename") or "")
    unexpected_rename = on_duplicate == "error" and returned_name != asset.local.name
    record_uploaded_identity(asset, result, course_id=course_id, returned_name=returned_name)
    provenance_error = record_asset_provenance(
        asset,
        course_id=course_id,
        command=command,
        project_root=project_root,
    )
    if provenance_error:
        mark_provenance_failure(plan, asset, provenance_error)
        return AssetTransitionResult(stop=True, reason=asset.reason)
    if result["evidence_status"] != "complete":
        mark_incomplete_upload_evidence(plan, asset, result)
        return AssetTransitionResult(stop=True, reason=asset.reason)
    if unexpected_rename:
        asset["reason"] = "unexpected_rename_after_race"
        plan["status"] = "failed"
        plan.mutation_status = "partial"
        plan.evidence_status = "complete"
        return AssetTransitionResult(stop=True, reason=asset.reason)
    return AssetTransitionResult(stop=False)


def mark_changed_asset(plan: AssetPlan, asset: AssetItem) -> None:
    asset.update(
        {
            "status": "failed",
            "mutation_status": "not_started",
            "evidence_status": "complete",
            "reason": "local_asset_changed_after_plan",
        }
    )
    plan["status"] = "failed"
    plan.mutation_status = "partial" if any_mutated(plan) else "not_started"
    plan.evidence_status = "complete"
    plan.recovery_guidance = "Re-run the command to build a fresh asset plan."


def mark_changed_destination(
    plan: AssetPlan,
    asset: AssetItem,
    latest: dict[str, Any],
) -> None:
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
    plan.mutation_status = "partial" if any_mutated(plan) else "not_started"
    plan.evidence_status = "complete"


def upload_one_asset(
    asset: AssetItem,
    *,
    folder: Any,
    course_id: int,
    canvas_origin: str,
) -> dict[str, Any]:
    try:
        ok, response = folder.upload(
            str(asset.local.source_path),
            on_duplicate="rename",
            content_type=asset.local.content_type,
        )
    except Exception as exc:  # noqa: BLE001 - retained evidence is sanitized.
        ok = False
        response = {"error": sanitize_error(f"{type(exc).__name__}: {exc}")}
    return upload_result_row(
        asset_upload_row(asset),
        ok=bool(ok),
        response=response,
        folder=folder,
        course_id=course_id,
        canvas_origin=canvas_origin,
    )


def mark_upload_failure(
    plan: AssetPlan,
    asset: AssetItem,
    result: dict[str, Any],
) -> None:
    asset["status"] = str(result["status"])
    asset["reason"] = str(result.get("error") or "upload_failed")
    plan["status"] = str(result["status"])
    plan["mutation_status"] = "partial" if any_mutated(plan) else str(result["status"])
    plan["evidence_status"] = str(result["evidence_status"])
    if result["mutation_status"] == "indeterminate":
        plan.recovery_guidance = (
            "Verify Canvas Files before retrying; the upload outcome is indeterminate."
        )


def record_uploaded_identity(
    asset: AssetItem,
    result: dict[str, Any],
    *,
    course_id: int,
    returned_name: str,
) -> None:
    asset["status"] = (
        "renamed"
        if result["status"] == "uploaded" and returned_name != asset.local.name
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


def record_asset_provenance(
    asset: AssetItem,
    *,
    course_id: int,
    command: str,
    project_root: Path,
) -> str | None:
    assert asset.canvas is not None
    try:
        write_source_map_entry(
            kind="file",
            source=asset.local.source_path,
            course_id=course_id,
            canvas=asset.canvas.to_dict(),
            command=command,
            fields={
                "sha256": asset.local.sha256,
                "size": asset.local.size,
                "content_type": asset.local.content_type,
                "upload_name": asset.canvas.display_name,
            },
            project_root=project_root,
        )
    except Exception as exc:  # noqa: BLE001 - identity is still retained in memory.
        return type(exc).__name__
    return None


def mark_provenance_failure(
    plan: AssetPlan,
    asset: AssetItem,
    error_type: str,
) -> None:
    asset["evidence_status"] = "failed"
    asset["reason"] = f"source_map_write_{error_type}"
    plan["status"] = "failed"
    plan.mutation_status = "partial"
    plan.evidence_status = "failed"
    plan.recovery_guidance = (
        "Do not retry the upload. Preserve the reported Canvas file identity and "
        "repair source-map evidence first."
    )


def mark_incomplete_upload_evidence(
    plan: AssetPlan,
    asset: AssetItem,
    result: dict[str, Any],
) -> None:
    asset["reason"] = "stable_file_evidence_incomplete"
    plan["status"] = "indeterminate"
    plan.mutation_status = "partial"
    plan["evidence_status"] = str(result["evidence_status"])
    plan.recovery_guidance = (
        "Do not retry the upload. Reconstruct stable evidence from the recorded file ID."
    )


def finalize_deployed_plan(
    plan: AssetPlan,
    *,
    course_id: int,
    canvas_origin: str,
) -> None:
    rewritten = rewrite_authored_html(
        plan.runtime.source_html,
        plan.assets,
        course_id,
        canvas_origin,
    )
    plan.rewritten_html = rewritten
    plan.deployed_body_sha256 = sha256_text(rewritten)
    plan["status"] = "deployed"
    plan.mutation_status = "succeeded" if any_mutated(plan) else "not_needed"
    plan.evidence_status = "complete"


def rewrite_authored_html(
    html: str,
    assets: list[AssetItem] | list[dict[str, Any]],
    course_id: int,
    canvas_origin: str,
) -> str:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    by_occurrence: dict[int, tuple[Any, Any]] = {}
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
    assets: list[AssetItem] | list[dict[str, Any]],
    canvas_html: str,
    *,
    expected_html: str,
    course: Any,
    course_id: int,
    canvas_origin: str,
) -> AssetVerification:
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
        if (canvas := asset.get("canvas")) is not None
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
    return AssetVerification(
        status="mismatch" if mismatch else "matches",
        expected=counter_rows(expected),
        actual=counter_rows(actual),
        invalid=[safe_reference(row) for row in invalid],
        expected_invalid=[safe_reference(row) for row in expected_invalid],
        files=files,
    )


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
    source_map: dict[str, Any], asset: AssetItem, *, course_id: int
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


def safe_folder_record(folder: Any) -> AssetDestination:
    folder_id = getattr(folder, "id", None)
    return AssetDestination(
        id=int(folder_id) if folder_id is not None else None,
        full_name=str(getattr(folder, "full_name", "") or ""),
    )


def asset_upload_row(asset: AssetItem | dict[str, Any]) -> dict[str, Any]:
    return {
        "source": str(asset["source_path"]),
        "relative_path": str(asset["path"]),
        "name": str(asset["name"]),
        "size": int(asset["size"]),
        "content_type": str(asset["content_type"]),
    }


def any_mutated(plan: AssetPlan) -> bool:
    return any(
        asset.get("mutation_status") == "succeeded"
        or asset.get("status") in {"uploaded", "renamed"}
        for asset in plan.get("assets") or []
    )


def asset_plan_signature(
    assets: list[AssetItem] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return local intent fields that must remain stable between plan and mutation."""
    return [
        asset.signature_dict()
        if isinstance(asset, AssetItem)
        else {
            "path": asset.get("path"),
            "sha256": asset.get("sha256"),
            "size": asset.get("size"),
            "content_type": asset.get("content_type"),
            "name": asset.get("name"),
            "occurrences": asset.get("occurrences") or [],
        }
        for asset in assets
    ]


def current_asset_matches(asset: AssetItem | dict[str, Any]) -> bool:
    try:
        payload = Path(str(asset["source_path"])).read_bytes()
    except OSError:
        return False
    return len(payload) == int(asset["size"]) and hashlib.sha256(payload).hexdigest() == str(
        asset["sha256"]
    )


def asset_associations(plan: AssetPlan | None) -> list[dict[str, Any]]:
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


def public_asset_evidence(plan: AssetPlan | None) -> AssetPublicEvidence | None:
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
    return AssetPublicEvidence({
        "evidence_schema": ASSET_EVIDENCE_SCHEMA,
        "status": plan["status"],
        "course_id": plan["course_id"],
        "source": plan["source"],
        "source_body_sha256": plan["source_body_sha256"],
        "deployed_body_sha256": plan.get("deployed_body_sha256"),
        "deployed_body_status": deployed_body_status,
        "destination": plan.destination.to_dict() if plan.destination else None,
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
    })


def safe_asset_row(asset: AssetItem) -> dict[str, Any]:
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
    if asset.canvas is not None:
        row["canvas"] = asset.canvas.to_dict()
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
    if isinstance(value, AssetVerification):
        return value.to_dict()
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
