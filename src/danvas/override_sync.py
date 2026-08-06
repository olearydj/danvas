"""Dry-run-first synchronization of private assignment override files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from danvas.auth import canvas_from_args
from danvas.frontmatter import parse_frontmatter
from danvas.overrides import load_local_override_file, normalize_scalar, override_id, value
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.source_map import resolve_source_canvas_id
from danvas.utils import print_mutation_banner

WINDOW_FIELDS = ("due_at", "unlock_at", "lock_at")


def command_assignments_overrides_sync(args: Any) -> None:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"Assignment Markdown source not found: {source}")
    dry_run = bool(getattr(args, "dry_run", True))
    confirm = str(getattr(args, "confirm", "") or "").strip()
    if not dry_run and confirm != "apply":
        raise SystemExit("Live override sync requires --live --confirm apply.")

    project_root = Path(getattr(args, "project_root", ".")).resolve()
    metadata, _ = parse_frontmatter(
        source.read_text(encoding="utf-8-sig"), source, "Assignment"
    )
    reference = str(metadata.get("availability_overrides_ref") or "").strip()
    if not reference:
        raise SystemExit("Assignment front matter must include availability_overrides_ref.")
    frontmatter_id = metadata.get(
        "assignment_id", metadata.get("canvas_id", metadata.get("id"))
    )
    resolved = resolve_source_canvas_id(
        kind="assignment",
        source=source,
        explicit_id=getattr(args, "assignment_id", None),
        frontmatter_id=int(frontmatter_id) if frontmatter_id not in {None, ""} else None,
        project_root=project_root,
    )
    assignment_id = resolved["id"]
    if assignment_id is None:
        raise SystemExit(
            "Override sync requires --assignment-id, assignment_id front matter, or a source-map ID."
        )

    payload, error = load_local_override_file(project_root, reference)
    if error:
        raise SystemExit(error)
    assert payload is not None
    desired = validate_override_payload(payload, int(assignment_id))

    canvas = canvas_from_args(args)
    assignment = canvas.get_course(args.course_id).get_assignment(int(assignment_id))
    current = list(assignment.get_overrides())
    plan = plan_override_sync(desired, current)
    report = build_override_sync_report(
        source=source,
        reference=reference,
        assignment_id=int(assignment_id),
        resolved=resolved,
        plan=plan,
        dry_run=dry_run,
    )
    report_run = make_override_sync_report_run(args, report, project_root)
    print_override_sync_summary(report)
    if plan["errors"]:
        write_override_sync_report_run(report_run, report)
        raise SystemExit(1)
    if dry_run or not (plan["creates"] or plan["updates"]):
        write_override_sync_report_run(report_run, report)
        return

    print_mutation_banner(
        "sync assignment overrides",
        {
            "course": args.course_id,
            "assignment_id": assignment_id,
            "creates": len(plan["creates"]),
            "updates": len(plan["updates"]),
            "source": source,
        },
    )
    apply_override_sync(assignment, plan)
    verification = plan_override_sync(desired, list(assignment.get_overrides()))
    report["verification"] = summarize_plan(verification)
    report["status"] = "applied" if not verification["errors"] and not (
        verification["creates"] or verification["updates"]
    ) else "verification_failed"
    write_override_sync_report_run(report_run, report)
    print_override_sync_summary(report)
    if report["status"] != "applied":
        raise SystemExit(1)


def validate_override_payload(payload: dict[str, Any], assignment_id: int) -> list[dict[str, Any]]:
    file_assignment_id = payload.get("assignment_id")
    if file_assignment_id not in {None, ""} and int(file_assignment_id) != assignment_id:
        raise SystemExit("Override file assignment_id does not match the target assignment.")
    rows = payload.get("overrides")
    if not isinstance(rows, list):
        raise SystemExit("Override file must contain an overrides list.")
    desired: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    idless_titles: set[str] = set()
    for index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            raise SystemExit(f"Override row {index} must be a mapping.")
        row = cast(dict[str, Any], raw_row)
        title = str(row.get("title") or "").strip()
        if not title:
            raise SystemExit(f"Override row {index} must include a title.")
        missing = [field for field in WINDOW_FIELDS if field not in row]
        if missing:
            raise SystemExit(
                f"Override row {index} must explicitly include {', '.join(missing)}."
            )
        raw_id = row.get("canvas_override_id", row.get("id"))
        canvas_override_id = int(raw_id) if raw_id not in {None, ""} else None
        if canvas_override_id is not None:
            if canvas_override_id in seen_ids:
                raise SystemExit(f"Duplicate Canvas override ID in row {index}.")
            seen_ids.add(canvas_override_id)
        elif title.casefold() in idless_titles:
            raise SystemExit(f"ID-less override titles must be unique; duplicate in row {index}.")
        else:
            idless_titles.add(title.casefold())
        target = validate_assignees(row.get("assignees"), index)
        desired.append(
            {
                "canvas_override_id": canvas_override_id,
                "title": title,
                **{field: row.get(field) for field in WINDOW_FIELDS},
                "target": target,
            }
        )
    return desired


def validate_assignees(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SystemExit(f"Override row {index} must include an assignees mapping.")
    user_ids_raw = raw.get("canvas_user_ids") or []
    if not isinstance(user_ids_raw, list):
        raise SystemExit(f"Override row {index} canvas_user_ids must be a list.")
    user_ids = sorted({int(item) for item in user_ids_raw if item not in {None, ""}})
    selected: list[tuple[str, Any]] = []
    if user_ids:
        selected.append(("canvas_user_ids", user_ids))
    for kind in ("course_section_id", "group_id"):
        target = raw.get(kind)
        if target not in {None, ""}:
            selected.append((kind, target))
    if len(selected) != 1:
        raise SystemExit(
            f"Override row {index} must target exactly one of canvas_user_ids, "
            "course_section_id, or group_id."
        )
    kind, target = selected[0]
    if kind == "canvas_user_ids":
        return {"kind": kind, "value": target}
    return {"kind": kind, "value": int(target)}


def canvas_override_record(row: Any) -> dict[str, Any]:
    target: dict[str, Any]
    student_ids = sorted(int(item) for item in (value(row, "student_ids", []) or []))
    if student_ids:
        target = {"kind": "canvas_user_ids", "value": student_ids}
    elif value(row, "course_section_id") not in {None, ""}:
        target = {"kind": "course_section_id", "value": int(value(row, "course_section_id"))}
    elif value(row, "group_id") not in {None, ""}:
        target = {"kind": "group_id", "value": int(value(row, "group_id"))}
    else:
        target = {"kind": "unknown", "value": None}
    return {
        "canvas_override_id": override_id(row),
        "title": str(value(row, "title", "") or "").strip(),
        **{field: value(row, field) for field in WINDOW_FIELDS},
        "target": target,
        "object": row,
    }


def plan_override_sync(
    desired: list[dict[str, Any]], current_rows: list[Any]
) -> dict[str, list[dict[str, Any]]]:
    current = [canvas_override_record(row) for row in current_rows]
    by_id = {
        row["canvas_override_id"]: row
        for row in current
        if row["canvas_override_id"] is not None
    }
    claimed_ids = {
        row["canvas_override_id"]
        for row in desired
        if row["canvas_override_id"] is not None
    }
    used: set[int] = set()
    plan: dict[str, list[dict[str, Any]]] = {
        "creates": [],
        "updates": [],
        "unchanged": [],
        "unmanaged": [],
        "errors": [],
    }
    for local in desired:
        match: dict[str, Any] | None = None
        local_id = local["canvas_override_id"]
        if local_id is not None:
            match = by_id.get(local_id)
            if match is None:
                plan["errors"].append(
                    safe_plan_row(local, "error", detail="override ID not found in Canvas")
                )
                continue
        else:
            title_matches = [
                row
                for row in current
                if row["canvas_override_id"] not in used
                and row["canvas_override_id"] not in claimed_ids
                and row["title"].casefold() == local["title"].casefold()
            ]
            if len(title_matches) > 1:
                plan["errors"].append(
                    safe_plan_row(local, "error", detail="title matches multiple Canvas overrides")
                )
                continue
            match = title_matches[0] if title_matches else None
        if match is None:
            plan["creates"].append(safe_plan_row(local, "create", desired=local))
            continue
        assert match["canvas_override_id"] is not None
        used.add(match["canvas_override_id"])
        changes = changed_fields(local, match)
        row = safe_plan_row(
            local,
            "update" if changes else "unchanged",
            canvas_override_id=match["canvas_override_id"],
            changed=changes,
            desired=local,
            canvas_object=match["object"],
        )
        plan["updates" if changes else "unchanged"].append(row)
    plan["unmanaged"] = [
        safe_plan_row(row, "unmanaged", canvas_override_id=row["canvas_override_id"])
        for row in current
        if row["canvas_override_id"] not in used
    ]
    return plan


def changed_fields(local: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changed = []
    if local["title"] != current["title"]:
        changed.append("title")
    changed.extend(
        field
        for field in WINDOW_FIELDS
        if normalize_scalar(local.get(field)) != normalize_scalar(current.get(field))
    )
    if local["target"] != current["target"]:
        changed.append("assignees")
    return changed


def safe_plan_row(
    row: dict[str, Any],
    action: str,
    *,
    canvas_override_id: int | None = None,
    changed: list[str] | None = None,
    detail: str = "",
    desired: dict[str, Any] | None = None,
    canvas_object: Any | None = None,
) -> dict[str, Any]:
    target = row.get("target") or {}
    value_ = target.get("value")
    count = (
        len(value_)
        if target.get("kind") == "canvas_user_ids" and isinstance(value_, list)
        else int(value_ is not None)
    )
    result = {
        "action": action,
        "canvas_override_id": canvas_override_id or row.get("canvas_override_id"),
        "title": row.get("title", ""),
        "assignee_type": target.get("kind", "unknown"),
        "assignee_count": count,
        "changed_fields": changed or [],
        "detail": detail,
    }
    if desired is not None:
        result["_desired"] = desired
    if canvas_object is not None:
        result["_canvas_object"] = canvas_object
    return result


def canvas_override_payload(desired: dict[str, Any]) -> dict[str, Any]:
    payload = {"title": desired["title"], **{field: desired.get(field) for field in WINDOW_FIELDS}}
    target = desired["target"]
    key = "student_ids" if target["kind"] == "canvas_user_ids" else target["kind"]
    payload[key] = target["value"]
    return payload


def apply_override_sync(assignment: Any, plan: dict[str, list[dict[str, Any]]]) -> None:
    for row in plan["updates"]:
        row["_canvas_object"].edit(
            assignment_override=canvas_override_payload(row["_desired"])
        )
    for row in plan["creates"]:
        assignment.create_override(
            assignment_override=canvas_override_payload(row["_desired"])
        )


def summarize_plan(plan: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {key: len(value_) for key, value_ in plan.items()}


def build_override_sync_report(
    *,
    source: Path,
    reference: str,
    assignment_id: int,
    resolved: dict[str, Any],
    plan: dict[str, list[dict[str, Any]]],
    dry_run: bool,
) -> dict[str, Any]:
    safe_rows = [
        {key: value_ for key, value_ in row.items() if not key.startswith("_")}
        for group in plan.values()
        for row in group
    ]
    status = "error" if plan["errors"] else (
        "would_apply" if plan["creates"] or plan["updates"] else "no_change"
    )
    return {
        "command": "assignments overrides-sync",
        "status": status,
        "dry_run": dry_run,
        "source": str(source),
        "override_reference": reference,
        "assignment_id": assignment_id,
        "id_resolution": {key: value_ for key, value_ in resolved.items() if key != "source_map_entry"},
        "summary": summarize_plan(plan),
        "rows": safe_rows,
    }


def make_override_sync_report_run(
    args: Any, report: dict[str, Any], project_root: Path
) -> ReportRun | None:
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=False,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="assignments overrides-sync",
        slug=report_slug or "assignments-overrides-sync",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=getattr(args, "course_id", None),
        input_paths=[Path(report["source"]), project_root / report["override_reference"]],
        private_data=True,
    )


def write_override_sync_report_run(report_run: ReportRun | None, report: dict[str, Any]) -> None:
    if report_run is None:
        return
    json_path = report_run.write_json("assignments-overrides-sync.json", report)
    md_path = report_run.write_text(
        "assignments-overrides-sync.md", render_override_sync_markdown(report)
    )
    success = report["status"] in {"would_apply", "no_change", "applied"}
    manifest_path = report_run.finish("success" if success else "failed")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {manifest_path}")
    print(f"Report directory: {report_run.path}")


def render_override_sync_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Assignment override sync",
        "",
        f"- Status: {report['status']}",
        f"- Assignment ID: {report['assignment_id']}",
        f"- Private override reference: `{report['override_reference']}`",
        f"- Create: {summary['creates']}",
        f"- Update: {summary['updates']}",
        f"- Unchanged: {summary['unchanged']}",
        f"- Canvas-only (preserved): {summary['unmanaged']}",
        f"- Errors: {summary['errors']}",
        "",
        "Student identifiers are intentionally omitted; assignee counts are shown instead.",
    ]
    return "\n".join(lines) + "\n"


def print_override_sync_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Assignment override sync: {report['status']}")
    print(f"  Assignment ID: {report['assignment_id']}")
    print(f"  Create: {summary['creates']}")
    print(f"  Update: {summary['updates']}")
    print(f"  Unchanged: {summary['unchanged']}")
    print(f"  Canvas-only preserved: {summary['unmanaged']}")
    print(f"  Errors: {summary['errors']}")
