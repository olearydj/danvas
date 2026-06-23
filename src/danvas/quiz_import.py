"""Canvas QTI package import, quiz shell configuration, and verification."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from danvas.auth import canvas_from_args
from danvas.reports import ReportRun, create_report_run, should_write_report_run
from danvas.status import normalize_title, values_equal
from danvas.utils import print_mutation_banner, write_json

SETTING_FIELDS = [
    "title",
    "assignment_group_id",
    "due_at",
    "unlock_at",
    "lock_at",
    "time_limit",
    "allowed_attempts",
]
MISSING = object()


def command_quiz_import_qti(args: Any) -> None:
    package = Path(args.package)
    if not package.is_file():
        raise SystemExit(f"QTI package not found: {package}")
    settings = quiz_settings_from_args(args)
    report_run = make_quiz_import_report_run(args, package)
    if args.dry_run:
        report = {
            "status": "dry-run",
            "package": str(package),
            "course_id": args.course_id,
            "settings": settings,
        }
        print("Dry run - no QTI import performed.")
        print(f"Package: {package} ({package.stat().st_size} bytes)")
        print(f"Course: {args.course_id}")
        print("Quiz settings to apply after import:")
        print(json.dumps(settings, indent=2))
        if args.output:
            write_json(Path(args.output), report)
            print(f"Wrote {args.output}")
        write_quiz_import_report_run(report_run, report)
        return
    print_mutation_banner(
        "import QTI quiz package",
        {
            "course": args.course_id,
            "package": package.name,
            "size_bytes": package.stat().st_size,
            "settings": ", ".join(sorted(settings)) or "none",
        },
    )
    try:
        canvas = canvas_from_args(args)
        course = canvas.get_course(args.course_id)
        existing_ids = {quiz.id for quiz in course.get_quizzes()}
        migration = start_qti_migration(course, package)
        print(f"Created content migration {migration.id}; uploading {package.name}")
        wait_for_migration(
            course,
            migration.id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        print(f"Migration {migration.id} completed.")
        quiz = find_imported_quiz(course, existing_ids, match_title=args.match_title)
        if settings:
            quiz.edit(quiz=settings)
        report = verification_report(course, quiz.id, settings)
        report["package"] = str(package)
        report["course_id"] = args.course_id
        report["migration_id"] = migration.id
        for line in render_verification_lines(report):
            print(line)
        if args.output:
            write_json(Path(args.output), report)
            print(f"Wrote {args.output}")
        write_quiz_import_report_run(report_run, report)
        report_run = None
        if report["status"] != "verified":
            raise SystemExit(1)
    except BaseException as exc:
        if report_run is not None:
            report_run.finish("failed", error=str(exc))
            print(f"Wrote {report_run.path / 'manifest.json'}")
            print(f"Report directory: {report_run.path}")
        raise


def make_quiz_import_report_run(args: Any, package: Path) -> ReportRun | None:
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None
    report_root = Path(args.report_root) if getattr(args, "report_root", None) else None
    report_dir = Path(args.report_dir) if getattr(args, "report_dir", None) else None
    report_slug = getattr(args, "report_slug", None)
    if not should_write_report_run(
        no_report=bool(getattr(args, "no_report", False)),
        legacy_output=bool(getattr(args, "output", None)),
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        return None
    return create_report_run(
        command="quiz import-qti",
        slug=report_slug or "quiz-import-qti",
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        course_id=args.course_id,
        input_paths=[package],
        private_data=False,
    )


def write_quiz_import_report_run(report_run: ReportRun | None, report: dict[str, Any]) -> None:
    if report_run is None:
        return
    json_path = report_run.write_json("quiz-import-qti.json", report)
    status = "success" if report["status"] in {"verified", "dry-run"} else "failed"
    manifest_path = report_run.finish(status)
    print(f"Wrote {json_path}")
    print(f"Wrote {manifest_path}")
    print(f"Report directory: {report_run.path}")


def quiz_settings_from_args(args: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for field in SETTING_FIELDS:
        value = getattr(args, field, None)
        if value is not None:
            settings[field] = value
    publish = getattr(args, "publish", None)
    if publish is not None:
        settings["published"] = publish
    return settings


def start_qti_migration(course: Any, package: Path) -> Any:
    migration = course.create_content_migration(
        migration_type="qti_converter",
        pre_attachment={"name": package.name, "size": package.stat().st_size},
    )
    pre_attachment = getattr(migration, "pre_attachment", None) or {}
    upload_url = pre_attachment.get("upload_url")
    if not upload_url:
        raise SystemExit("Canvas did not return an upload URL for the QTI package.")
    with package.open("rb") as handle:
        response = requests.post(
            upload_url,
            data=pre_attachment.get("upload_params") or {},
            files={"file": (package.name, handle)},
            timeout=300,
        )
    if response.status_code >= 400:
        raise SystemExit(f"QTI package upload failed with HTTP {response.status_code}.")
    return migration


def wait_for_migration(
    course: Any, migration_id: Any, *, poll_seconds: float, timeout_seconds: float
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while True:
        migration = course.get_content_migration(migration_id)
        state = str(getattr(migration, "workflow_state", "") or "")
        if state == "completed":
            return migration
        if state == "failed":
            issues = migration_issue_messages(migration)
            detail = f" Issues: {'; '.join(issues)}" if issues else ""
            raise SystemExit(f"QTI migration {migration_id} failed.{detail}")
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"QTI migration {migration_id} did not finish within "
                f"{timeout_seconds:g}s (state: {state or 'unknown'})."
            )
        time.sleep(poll_seconds)


def migration_issue_messages(migration: Any) -> list[str]:
    try:
        issues = list(migration.get_migration_issues())
    except Exception:  # noqa: BLE001 - issue listing is best-effort diagnostics
        return []
    return [str(getattr(issue, "description", issue)) for issue in issues]


def find_imported_quiz(course: Any, existing_ids: set[Any], match_title: str | None) -> Any:
    quizzes = list(course.get_quizzes())
    new_quizzes = [quiz for quiz in quizzes if quiz.id not in existing_ids]
    if match_title:
        pool = new_quizzes or quizzes
        wanted = normalize_title(match_title)
        matches = [
            quiz for quiz in pool if normalize_title(str(getattr(quiz, "title", ""))) == wanted
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(f"Quiz title is ambiguous: {len(matches)} quizzes match {match_title!r}.")
        raise SystemExit(f"No quiz found with title {match_title!r}.")
    if len(new_quizzes) == 1:
        return new_quizzes[0]
    if not new_quizzes:
        raise SystemExit(
            "Migration completed but no new quiz was found. Pass --match-title to select one."
        )
    raise SystemExit(
        f"Migration created {len(new_quizzes)} quizzes. Pass --match-title to select one."
    )


def verification_report(course: Any, quiz_id: Any, requested: dict[str, Any]) -> dict[str, Any]:
    quiz = course.get_quiz(quiz_id)
    checks = []
    unverified = []
    for field, expected in requested.items():
        actual = getattr(quiz, field, MISSING)
        if actual is MISSING:
            unverified.append(field)
            continue
        checks.append(
            {
                "field": field,
                "expected": expected,
                "actual": actual,
                "ok": values_equal(field, expected, actual),
            }
        )
    mismatches = [check for check in checks if not check["ok"]]
    return {
        "quiz": {
            "id": getattr(quiz, "id", None),
            "assignment_id": getattr(quiz, "assignment_id", None),
            "title": getattr(quiz, "title", "") or "",
            "html_url": getattr(quiz, "html_url", "") or "",
            "quiz_type": getattr(quiz, "quiz_type", "") or "",
            "published": getattr(quiz, "published", None),
            "points_possible": getattr(quiz, "points_possible", None),
            "question_count": getattr(quiz, "question_count", None),
            "due_at": getattr(quiz, "due_at", "") or "",
            "unlock_at": getattr(quiz, "unlock_at", "") or "",
            "lock_at": getattr(quiz, "lock_at", "") or "",
            "time_limit": getattr(quiz, "time_limit", None),
            "allowed_attempts": getattr(quiz, "allowed_attempts", None),
        },
        "requested_settings": requested,
        "checks": checks,
        "unverified": unverified,
        "status": "verified" if not mismatches else "settings mismatch",
    }


def render_verification_lines(report: dict[str, Any]) -> list[str]:
    quiz = report["quiz"]
    lines = [
        f"Imported quiz: {quiz['title']} (quiz ID {quiz['id']}, "
        f"assignment ID {quiz['assignment_id']})",
        f"URL: {quiz['html_url']}",
        f"Published: {quiz['published']}",
        f"Points: {quiz['points_possible']}, questions: {quiz['question_count']}",
        f"Due: {quiz['due_at'] or '-'} (unlock {quiz['unlock_at'] or '-'}, "
        f"lock {quiz['lock_at'] or '-'})",
    ]
    for check in report["checks"]:
        outcome = "OK" if check["ok"] else "MISMATCH"
        lines.append(
            f"  {check['field']}: {outcome} "
            f"(expected {check['expected']!r}, actual {check['actual']!r})"
        )
    for field in report["unverified"]:
        lines.append(f"  {field}: could not verify (not exposed on the quiz object)")
    lines.append(f"Verification: {report['status']}")
    return lines
