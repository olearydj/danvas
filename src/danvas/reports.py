"""Generated report-run helpers."""

from __future__ import annotations

import datetime as dt
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from danvas import __version__
from danvas.utils import slugify, write_json, write_rows

CONFIG_DIR_NAME = ".danvas"
CONFIG_FILE_NAME = "config.toml"
REPORTS_DIR_NAME = "reports"
URLISH_RE = re.compile(r"https?://\S+|[A-Za-z]+://\S+")
SENSITIVE_VALUE_RE = re.compile(r"(?i)\b(verifier|token|secret)=([^&\s]+)")


@dataclass
class ReportRun:
    path: Path
    slug: str
    created_at: dt.datetime
    manifest: dict[str, Any]
    _files: list[str] = field(default_factory=list)

    def record_file(self, path: Path) -> None:
        try:
            name = path.relative_to(self.path).as_posix()
        except ValueError:
            name = str(path)
        if name not in self._files:
            self._files.append(name)

    def write_json(self, filename: str, payload: dict[str, Any]) -> Path:
        path = self.path / filename
        write_json(path, payload)
        self.record_file(path)
        return path

    def write_rows(self, filename: str, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
        path = self.path / filename
        write_rows(path, rows, fieldnames)
        self.record_file(path)
        return path

    def write_text(self, filename: str, text: str) -> Path:
        path = self.path / filename
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
    root = project_root.resolve() if project_root else (config_dir.parent if config_dir else None)
    created_at = now_for_config(config_dir)
    report_date = created_at.date().isoformat()
    report_slug = slugify(slug, "report")

    if report_dir:
        path = report_dir
        path.mkdir(parents=True, exist_ok=False)
    else:
        if report_root:
            base = report_root
        elif config_dir:
            base = config_dir / REPORTS_DIR_NAME
        else:
            raise SystemExit(
                "No .danvas project found for report output. Pass --report-root or --report-dir."
            )
        path = create_sequenced_run_dir(base, report_date, report_slug)

    manifest = {
        "command": command,
        "argv": sys.argv,
        "generated_at": created_at.isoformat(timespec="seconds"),
        "report_date": report_date,
        "report_slug": report_slug,
        "run_directory": str(path),
        "danvas_version": __version__,
        "course_id": course_id,
        "project_root": str(root) if root else None,
        "input_paths": [str(path) for path in input_paths or []],
        "snapshot_timestamp": snapshot_timestamp,
        "may_contain_private_student_data": private_data,
        "status": "running",
        "files": [],
    }
    return ReportRun(path=path, slug=report_slug, created_at=created_at, manifest=manifest)


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


def create_sequenced_run_dir(root: Path, report_date: str, slug: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sequence = next_sequence(root, report_date)
    while True:
        path = root / f"{report_date}-{sequence:03d}-{slug}"
        try:
            path.mkdir(parents=True, exist_ok=False)
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


def find_config_dir(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        path = candidate / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if path.is_file():
            return path.parent
    return None


def now_for_config(config_dir: Path | None) -> dt.datetime:
    timezone = None
    if config_dir:
        data = tomllib.loads((config_dir / CONFIG_FILE_NAME).read_text(encoding="utf-8"))
        timezone = (data.get("canvas") or {}).get("timezone")
    if timezone:
        try:
            return dt.datetime.now(ZoneInfo(str(timezone)))
        except ZoneInfoNotFoundError:
            pass
    return dt.datetime.now().astimezone()


def safe_error(error: str) -> str:
    text = " ".join(str(error).split())
    text = SENSITIVE_VALUE_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    return URLISH_RE.sub("[url]", text)
