"""Generated report-run helpers."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from danvas import __version__
from danvas.artifacts import (
    PRIVATE_DIR_NAME,
    ArtifactClass,
    ensure_private_directory,
    write_private_json,
    write_private_text,
)
from danvas.project_config import (
    configured_course_id,
    configured_timezone,
    find_config_dir,
)
from danvas.sanitize import sanitize_error
from danvas.utils import slugify, write_json, write_rows

REPORTS_DIR_NAME = "reports"
REPORT_MANIFEST_SCHEMA_VERSION = 2
REPORT_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(\d{3})-(.+)$")


@dataclass
class ReportRun:
    path: Path
    slug: str
    created_at: dt.datetime
    manifest: dict[str, Any]
    private_data: bool = False
    _files: list[str] = field(default_factory=list)

    def record_file(self, path: Path) -> None:
        try:
            name = path.resolve().relative_to(self.path.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"Report file is outside its run directory: {path}") from exc
        if name not in self._files:
            self._files.append(name)

    def write_json(self, filename: str, payload: dict[str, Any]) -> Path:
        path = self.path / filename
        if self.private_data:
            write_private_json(
                path,
                payload,
                command=str(self.manifest["command"]),
                classify=False,
            )
        else:
            write_json(path, payload)
        self.record_file(path)
        return path

    def write_rows(self, filename: str, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
        path = self.path / filename
        if self.private_data:
            # Report manifests classify every file in the private bundle, so a
            # per-CSV artifact sidecar would be redundant.
            import csv
            import io

            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            write_private_text(path, stream.getvalue())
        else:
            write_rows(path, rows, fieldnames)
        self.record_file(path)
        return path

    def write_text(self, filename: str, text: str) -> Path:
        path = self.path / filename
        if self.private_data:
            write_private_text(path, text)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.record_file(path)
        return path

    def finish(self, status: str = "success", *, error: str | None = None) -> Path:
        self.manifest["status"] = status
        if error:
            self.manifest["error"] = safe_error(error)
        self.manifest["files"] = list(self._files)
        path = self.path / "manifest.json"
        if self.private_data:
            write_private_json(
                path,
                self.manifest,
                command=str(self.manifest["command"]),
                classify=False,
            )
        else:
            write_json(path, self.manifest)
        return path


def create_report_run(
    *,
    command: str,
    slug: str,
    project_root: Path | None = None,
    report_root: Path | None = None,
    report_dir: Path | None = None,
    course_id: int | None = None,
    input_paths: list[Path] | None = None,
    snapshot_timestamp: str | None = None,
    private_data: bool = False,
) -> ReportRun:
    if report_root and report_dir:
        raise SystemExit("Use either --report-root or --report-dir, not both.")

    config_dir = find_config_dir(project_root)
    root = config_dir.parent if config_dir else (project_root.resolve() if project_root else None)
    created_at = now_for_config(config_dir)
    report_date = created_at.date().isoformat()
    report_slug = slugify(slug, "report")
    resolved_course_id = course_id if course_id is not None else course_id_for_config(config_dir)

    if report_dir:
        path = report_dir
        if private_data:
            ensure_private_directory(path, exist_ok=False)
        else:
            path.mkdir(parents=True, exist_ok=False)
    else:
        if report_root:
            base = report_root
        elif config_dir:
            if private_data:
                private_root = config_dir / PRIVATE_DIR_NAME
                ensure_private_directory(private_root, tighten_existing=True)
                base = private_root / REPORTS_DIR_NAME
            else:
                base = config_dir / REPORTS_DIR_NAME
        else:
            raise SystemExit(
                "No .danvas project found for report output. Pass --report-root or --report-dir."
            )
        if private_data:
            ensure_private_directory(base, tighten_existing=not bool(report_root))
        path = create_sequenced_run_dir(
            base,
            report_date,
            report_slug,
            mode=0o700 if private_data else 0o777,
        )

    manifest = {
        "manifest_schema_version": REPORT_MANIFEST_SCHEMA_VERSION,
        "artifact_class": (
            ArtifactClass.PRIVATE.value
            if private_data
            else ArtifactClass.COURSE_INTERNAL.value
        ),
        "command": command,
        "generated_at": created_at.isoformat(timespec="seconds"),
        "report_date": report_date,
        "report_slug": report_slug,
        "danvas_version": __version__,
        "course_id": resolved_course_id,
        "inputs": [_report_input_reference(item, root) for item in input_paths or []],
        "snapshot_timestamp": snapshot_timestamp,
        "may_contain_private_student_data": private_data,
        "status": "running",
        "files": [],
    }
    return ReportRun(
        path=path,
        slug=report_slug,
        created_at=created_at,
        manifest=manifest,
        private_data=private_data,
    )


def should_write_report_run(
    *,
    no_report: bool,
    legacy_output: bool,
    report_root: Path | None,
    report_dir: Path | None,
    report_slug: str | None,
    project_root: Path | None,
) -> bool:
    report_option = bool(report_root or report_dir or report_slug)
    if no_report and report_option:
        raise SystemExit("Use either --no-report or report output options, not both.")
    if no_report:
        return False
    if report_option:
        return True
    if legacy_output:
        return False
    return find_config_dir(project_root) is not None


def resolve_reports_root(
    *, project_root: Path | None = None, report_root: Path | None = None
) -> Path:
    if report_root:
        return report_root
    config_dir = find_config_dir(project_root)
    if not config_dir:
        raise SystemExit(
            "No .danvas project found for report discovery. Pass --project-root or --report-root."
        )
    return config_dir / REPORTS_DIR_NAME


def discover_report_runs(
    *, project_root: Path | None = None, report_root: Path | None = None
) -> list[dict[str, Any]]:
    roots = _report_discovery_roots(project_root=project_root, report_root=report_root)
    rows: list[dict[str, Any]] = []
    for storage_scope, root in roots:
        if not root.exists():
            continue
        if not root.is_dir():
            raise SystemExit(f"Reports root is not a directory: {root}")
        rows.extend(
            report_run_summary(path, storage_scope=storage_scope)
            for path in root.iterdir()
            if path.is_dir()
        )
    rows.sort(key=lambda row: (row["name"], row["storage_scope"]), reverse=True)
    return rows


def latest_report_run(
    *,
    slug: str | None = None,
    project_root: Path | None = None,
    report_root: Path | None = None,
) -> dict[str, Any] | None:
    wanted = slugify(slug, "") if slug else None
    rows = [
        row
        for row in discover_report_runs(project_root=project_root, report_root=report_root)
        if row["manifest_status"] == "valid"
        and (not wanted or row["report_slug"] == wanted)
    ]
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            row["generated_at"] or row["name"],
            row["storage_scope"],
            row["name"],
        ),
    )


def report_run_summary(path: Path, *, storage_scope: str = "explicit") -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    base = {
        "name": path.name,
        "storage_scope": storage_scope,
        "relative_run_directory": path.name,
        "path": path.name,
        "manifest_path": f"{path.name}/manifest.json",
        "manifest_status": "missing",
        "manifest_schema_version": None,
        "artifact_class": None,
        "command": "",
        "generated_at": "",
        "report_date": "",
        "report_slug": slug_from_report_dir(path.name),
        "status": "",
        "course_id": None,
        "danvas_version": "",
        "may_contain_private_student_data": None,
        "files": [],
        "error": "",
    }
    if not manifest_path.is_file():
        return base
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base["manifest_status"] = "invalid"
        base["error"] = safe_error(str(exc))
        return base
    if not isinstance(manifest, dict):
        base["manifest_status"] = "invalid"
        base["error"] = "Manifest is not a JSON object."
        return base
    files = manifest.get("files") or []
    if not isinstance(files, list):
        files = []
    base.update(
        {
            "manifest_status": "valid",
            "manifest_schema_version": manifest.get("manifest_schema_version", 1),
            "artifact_class": manifest.get("artifact_class")
            or (
                ArtifactClass.PRIVATE.value
                if manifest.get("may_contain_private_student_data") is True
                else ArtifactClass.COURSE_INTERNAL.value
            ),
            "command": str(manifest.get("command") or ""),
            "generated_at": str(manifest.get("generated_at") or ""),
            "report_date": str(manifest.get("report_date") or ""),
            "report_slug": str(manifest.get("report_slug") or base["report_slug"]),
            "status": str(manifest.get("status") or ""),
            "course_id": manifest.get("course_id"),
            "danvas_version": str(manifest.get("danvas_version") or ""),
            "may_contain_private_student_data": manifest.get(
                "may_contain_private_student_data"
            ),
            "files": [str(item) for item in files],
            "error": str(manifest.get("error") or ""),
        }
    )
    return base


def slug_from_report_dir(name: str) -> str:
    match = REPORT_DIR_RE.match(name)
    return match.group(2) if match else ""


def create_sequenced_run_dir(
    root: Path, report_date: str, slug: str, *, mode: int = 0o777
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sequence = next_sequence(root, report_date)
    while True:
        path = root / f"{report_date}-{sequence:03d}-{slug}"
        try:
            path.mkdir(mode=mode, parents=True, exist_ok=False)
            if mode & 0o077 == 0:
                path.chmod(mode)
            return path
        except FileExistsError:
            sequence += 1


def next_sequence(root: Path, report_date: str) -> int:
    prefix = f"{report_date}-"
    highest = 0
    if root.exists():
        for path in root.iterdir():
            if not path.is_dir() or not path.name.startswith(prefix):
                continue
            sequence_text = path.name.removeprefix(prefix).split("-", 1)[0]
            if sequence_text.isdigit():
                highest = max(highest, int(sequence_text))
    return highest + 1


def now_for_config(config_dir: Path | None) -> dt.datetime:
    timezone = configured_timezone(config_dir)
    if timezone:
        try:
            return dt.datetime.now(ZoneInfo(str(timezone)))
        except ZoneInfoNotFoundError:
            pass
    return dt.datetime.now().astimezone()


def course_id_for_config(config_dir: Path | None) -> int | None:
    return configured_course_id(config_dir)


def safe_error(error: str) -> str:
    """Compatibility export for the shared public error sanitizer."""
    return sanitize_error(error)


def _report_input_reference(path: Path, project_root: Path | None) -> dict[str, str]:
    if project_root is not None:
        try:
            relative = path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            pass
        else:
            return {"scope": "project", "path": relative}
    return {"scope": "external"}


def _report_discovery_roots(
    *, project_root: Path | None, report_root: Path | None
) -> list[tuple[str, Path]]:
    if report_root:
        return [("explicit", report_root)]
    config_dir = find_config_dir(project_root)
    if not config_dir:
        raise SystemExit(
            "No .danvas project found for report discovery. Pass --project-root or --report-root."
        )
    return [
        ("reports", config_dir / REPORTS_DIR_NAME),
        ("private", config_dir / PRIVATE_DIR_NAME / REPORTS_DIR_NAME),
    ]
