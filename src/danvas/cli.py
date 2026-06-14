"""Typer command surface for danvas."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import typer
from canvasapi.exceptions import ResourceDoesNotExist
from dotenv import load_dotenv

from danvas import __version__, assignment_audit, gradebook, quiz
from danvas.announcements import command_announcements_create, command_announcements_export
from danvas.assignments import command_assignments_create, command_assignments_export
from danvas.auth import DEFAULT_API_URL
from danvas.config import command_init, command_refresh, resolve_api_url, resolve_course_id
from danvas.courses import command_courses, command_roster
from danvas.discussions import command_discussions_export, command_discussions_score
from danvas.files import command_files_download, command_files_inventory, command_files_upload
from danvas.grades import command_grades_post, command_grades_verify
from danvas.panopto import command_panopto_captions
from danvas.quiz_import import command_quiz_import_qti
from danvas.status import command_status
from danvas.submissions import command_submissions_feedback, command_submissions_media
from danvas.utils import write_json

SecretProvider = Literal["auto", "1password", "env"]
AssignmentExportFormat = Literal["auto", "json", "csv", "markdown"]
DiscussionExportFormat = Literal["json", "csv"]
AnnouncementExportFormat = Literal["auto", "json", "csv", "markdown"]
FileDuplicatePolicy = Literal["overwrite", "rename"]


app = typer.Typer(
    name="danvas",
    help=(
        "Unified Canvas operations CLI.\n\n"
        "Use this for day-to-day course work: discover courses, export rosters, "
        "create or audit assignments, move submission files, post grades, and score discussions. "
        "It intentionally does not manage archival ledger/history data."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
)
assignments_app = typer.Typer(
    help="Create assignments from Markdown sources or export assignment metadata for review.",
    no_args_is_help=True,
)
gradebook_app = typer.Typer(
    help="Check Canvas gradebook exports and audit final-score setup.",
    no_args_is_help=True,
)
quiz_app = typer.Typer(
    help="Analyze Canvas Classic Quiz/Survey student-analysis CSV exports.",
    no_args_is_help=True,
)
submissions_app = typer.Typer(
    help="Download submitted media/attachments or upload per-student feedback files.",
    no_args_is_help=True,
)
grades_app = typer.Typer(
    help="Post grades from CSV, optionally with comments, then verify Canvas matches the CSV.",
    no_args_is_help=True,
)
discussions_app = typer.Typer(
    help="Export discussion posts or score participation for a graded discussion.",
    no_args_is_help=True,
)
announcements_app = typer.Typer(
    help="Create/export course announcements and filtered instructor replies.",
    no_args_is_help=True,
)
files_app = typer.Typer(
    help="Inventory Canvas course Files and compare them to local course files.",
    no_args_is_help=True,
)
recordings_app = typer.Typer(
    help="Discover and download course recording transcripts/captions.",
    no_args_is_help=True,
)

def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"danvas {__version__}")
        raise typer.Exit()


@app.callback()
def app_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the danvas version and exit.",
        ),
    ] = False,
) -> None:
    pass


app.add_typer(assignments_app, name="assignments")
app.add_typer(gradebook_app, name="gradebook")
app.add_typer(quiz_app, name="quiz")
app.add_typer(submissions_app, name="submissions")
app.add_typer(grades_app, name="grades")
app.add_typer(discussions_app, name="discussions")
app.add_typer(announcements_app, name="announcements")
app.add_typer(files_app, name="files")
app.add_typer(recordings_app, name="recordings")


ApiUrl = Annotated[
    str | None,
    typer.Option(
        "--api-url", help="Canvas base URL. Defaults to CANVAS_API_URL, then Auburn Canvas."
    ),
]
SecretProviderOption = Annotated[
    SecretProvider,
    typer.Option("--secret-provider", help="Secret source for the Canvas API token."),
]
OpReference = Annotated[
    str | None,
    typer.Option(
        "--op-reference", help="1Password item reference, such as op://Dev/Canvas/credential."
    ),
]
ApiKeyEnv = Annotated[
    str | None,
    typer.Option("--api-key-env", help="Environment variable containing the Canvas API token."),
]
CourseId = Annotated[int | None, typer.Option("--course-id", help="Canvas course ID.")]
AssignmentId = Annotated[int, typer.Option("--assignment-id", help="Canvas assignment ID.")]


def args_for(**kwargs: Any) -> SimpleNamespace:
    """Build the namespace expected by operation modules."""
    config_start = config_start_for(kwargs)
    if "course_id" in kwargs:
        kwargs["course_id"] = resolve_course_id(kwargs.get("course_id"), start=config_start)
    kwargs["api_url"] = (
        resolve_api_url(kwargs.get("api_url"), start=config_start)
        or os.environ.get("CANVAS_API_URL")
        or DEFAULT_API_URL
    )
    kwargs["secret_provider"] = kwargs.get("secret_provider") or os.environ.get(
        "CANVAS_SECRET_PROVIDER", "auto"
    )
    kwargs["op_reference"] = kwargs.get("op_reference") or os.environ.get(
        "CANVAS_API_KEY_OP_REFERENCE", ""
    )
    kwargs["api_key_env"] = kwargs.get("api_key_env") or os.environ.get(
        "CANVAS_API_KEY_ENV", "CANVAS_API_KEY"
    )
    return SimpleNamespace(**kwargs)


def config_start_for(kwargs: dict[str, Any]) -> Path | None:
    for key in ("project_root", "source"):
        value = kwargs.get(key)
        if value:
            return Path(value)
    return None


def run_command(func: Any, args: SimpleNamespace) -> None:
    try:
        func(args)
    except ResourceDoesNotExist as exc:
        typer.echo(f"Canvas resource not found: {exc}", err=True)
        raise typer.Exit(1) from exc
    except SystemExit as exc:
        if isinstance(exc.code, str) and exc.code:
            typer.echo(exc.code, err=True)
        raise typer.Exit(code=exc.code if isinstance(exc.code, int) else 1) from exc


@app.command(
    "init",
    help="Create .danvas/config.toml and .danvas/course.json for a Canvas course project.",
)
def init_project(
    course_id: Annotated[int, typer.Argument(help="Canvas course ID to bind to this project.")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root to initialize.")
    ] = Path("."),
    timezone: Annotated[
        str, typer.Option("--timezone", help="Course-local timezone for due-date workflows.")
    ] = "America/Chicago",
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing .danvas/config.toml.")
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_init,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            timezone=timezone,
            force=force,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@app.command(
    "refresh",
    help="Refresh .danvas/course.json from Canvas using --course-id or .danvas/config.toml.",
)
def refresh_project(
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Summarize changes since the previous snapshot."),
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_refresh,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            diff=diff,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@app.command(
    help="Report Canvas-vs-local course state from the snapshot and local sources. Read-only."
)
def status(
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    max_age_hours: Annotated[
        float | None,
        typer.Option(
            "--max-age-hours",
            help="Snapshot age in hours before a stale warning. Defaults to [status] config or 24.",
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON status output path.")
    ] = None,
    report_md: Annotated[
        Path | None, typer.Option("--report-md", help="Optional Markdown report output path.")
    ] = None,
) -> None:
    run_command(
        command_status,
        SimpleNamespace(
            project_root=str(project_root),
            max_age_hours=max_age_hours,
            output=str(output) if output else None,
            report_md=str(report_md) if report_md else None,
        ),
    )


@app.command(help="Export active courses visible to the authenticated Canvas user.")
def courses(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="CSV output path: id, name, course_code, start_at, end_at."
        ),
    ] = Path("courses.csv"),
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_courses,
        args_for(
            output=str(output),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@app.command(
    help="Export active course enrollments to a roster CSV for later grade/feedback matching."
)
def roster(
    course_id: CourseId = None,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="CSV output path: CanvasID, Name, Email, SIS_ID.")
    ] = Path("roster.csv"),
    enrollment_type: Annotated[
        str,
        typer.Option("--enrollment-type", help="Canvas enrollment type to include."),
    ] = "StudentEnrollment",
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_roster,
        args_for(
            course_id=course_id,
            output=str(output),
            enrollment_type=enrollment_type,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "export", help="Export assignment details as JSON, CSV, or a Markdown directory."
)
def assignments_export(
    course_id: CourseId = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output path. Use .json, .csv, or a directory with --format markdown.",
        ),
    ] = Path("assignments.json"),
    output_format: Annotated[
        AssignmentExportFormat,
        typer.Option("--format", help="Output format. 'auto' infers JSON/CSV from extension."),
    ] = "auto",
    full: Annotated[
        bool,
        typer.Option("--full", help="Include raw Canvas assignment/group payloads in JSON output."),
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_export,
        args_for(
            course_id=course_id,
            output=str(output),
            format=output_format,
            full=full,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "create",
    help="Create one Canvas assignment from Markdown. Use --dry-run first to inspect the payload.",
)
def assignments_create(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source beginning with YAML (---) or TOML (+++) assignment metadata."
        ),
    ],
    course_id: CourseId = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the Canvas payload without creating anything.")
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_create,
        args_for(
            course_id=course_id,
            source=str(source),
            dry_run=dry_run,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "audit",
    help="Compare a saved assignments export to course policy weights and basic setup expectations.",
)
def assignments_audit(
    assignments_path: Annotated[
        Path, typer.Argument(help="Assignments JSON file or Markdown export directory.")
    ],
    course_yaml: Annotated[
        Path | None,
        typer.Option("--course-yaml", help="Optional course policy YAML with expected weights."),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON audit output path.")
    ] = None,
) -> None:
    payload = assignment_audit.audit_assignment_file(assignments_path, course_yaml)
    typer.echo(f"Assignment setup audit: {assignments_path}")
    if payload["canvas_weights"]:
        typer.echo(f"  Canvas weight sum: {payload['weight_sum']}")
    if payload["missing_groups"]:
        typer.echo(f"  Missing groups: {', '.join(payload['missing_groups'])}")
    if payload["extra_groups"]:
        typer.echo(f"  Extra groups: {', '.join(payload['extra_groups'])}")
    typer.echo(f"  Assignments: {payload['assignments']['count']}")
    typer.echo(f"  Unpublished: {len(payload['assignments']['unpublished'])}")
    typer.echo(f"  Missing due dates: {len(payload['assignments']['missing_due_dates'])}")
    if output:
        write_json(output, payload)
        typer.echo(f"Wrote {output}")


@gradebook_app.command(
    "check",
    help="Inspect a Canvas gradebook CSV export for structure, score variants, and missing cells.",
)
def gradebook_check(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    course_yaml: Annotated[
        Path | None,
        typer.Option(
            "--course-yaml", help="Optional YAML with exclude_students/final_score_column."
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON check output path.")
    ] = None,
) -> None:
    policy = gradebook.load_policy(course_yaml)
    gb = gradebook.CanvasGradebook.read(gradebook_csv, policy.get("exclude_students") or [])
    payload = gradebook.check_gradebook(gb, final_score_column=policy.get("final_score_column"))
    typer.echo(f"Canvas gradebook check: {gradebook_csv}")
    typer.echo(f"  Included rows: {payload['structure']['included_rows']}")
    typer.echo(f"  Columns: {payload['structure']['columns']}")
    typer.echo(f"  Final score column: {payload['structure']['final_score_column']}")
    typer.echo(f"  Assignment columns: {payload['assignments']['detected_columns']}")
    typer.echo(f"  Assignment groups: {payload['assignments']['detected_groups']}")
    typer.echo(f"  Score variant diff rows: {payload['score_variants']['rows_with_differences']}")
    if payload["missing"]["totals"]:
        typer.echo(f"  Missing/nonnumeric totals: {payload['missing']['totals']}")
    if output:
        write_json(output, payload)
        typer.echo(f"Wrote {output}")


@gradebook_app.command(
    "audit",
    help="Audit final-score setup using a gradebook export and optional course policy/assignment snapshot.",
)
def gradebook_audit(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    course_yaml: Annotated[
        Path | None,
        typer.Option(
            "--course-yaml", help="Course policy YAML with weights and reconstruction rules."
        ),
    ] = None,
    assignments_path: Annotated[
        Path | None,
        typer.Option(
            "--assignments",
            help="Optional assignments JSON/directory export for Canvas group weights.",
        ),
    ] = None,
    tolerance: Annotated[
        float, typer.Option("--tolerance", help="Maximum allowed absolute final-score difference.")
    ] = 0.05,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON audit output path.")
    ] = None,
) -> None:
    policy = gradebook.load_policy(course_yaml)
    assignment_weights = None
    if assignments_path:
        assignment_weights = assignment_audit.assignment_group_weights(
            assignment_audit.load_assignment_snapshot(assignments_path)
        )
    gb = gradebook.CanvasGradebook.read(gradebook_csv, policy.get("exclude_students") or [])
    payload = gradebook.audit_gradebook(
        gb,
        policy=policy,
        assignment_weights=assignment_weights,
        tolerance=tolerance,
    )
    typer.echo(f"Canvas gradebook audit: {gradebook_csv}")
    typer.echo(f"  Final score column: {payload['final_score_column']}")
    typer.echo(f"  Weight sum: {payload['weight_sum']}")
    typer.echo(f"  Matched groups: {len(payload['matched_group_columns'])}")
    if payload["missing_weight_groups"]:
        typer.echo(f"  Missing weighted groups: {', '.join(payload['missing_weight_groups'])}")
    recon = payload["reconstruction"]
    typer.echo(f"  Rows compared: {recon['rows_compared']}")
    typer.echo(f"  Max abs diff: {recon['max_abs_diff']}")
    typer.echo(f"  Rows over tolerance: {recon['rows_over_tolerance']}")
    typer.echo(f"  Status: {recon['status']}")
    if output:
        write_json(output, payload)
        typer.echo(f"Wrote {output}")


@quiz_app.command(
    "analysis", help="Summarize a Canvas Classic Quiz/Survey student-analysis CSV export."
)
def quiz_analysis(
    student_analysis_csv: Annotated[
        Path, typer.Argument(help="Canvas student-analysis CSV export.")
    ],
    answer_term: Annotated[
        list[str] | None,
        typer.Option(
            "--answer-term",
            help="Question text term to count answers for. Repeat for multiple terms.",
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON analysis output path.")
    ] = None,
) -> None:
    payload = quiz.analyze_student_analysis(student_analysis_csv, answer_terms=answer_term)
    typer.echo(f"Canvas quiz analysis: {student_analysis_csv}")
    typer.echo(f"  Students: {payload['rows']['students']}")
    typer.echo(f"  Submitted: {payload['rows']['submitted']}")
    typer.echo(f"  Question pairs: {len(payload['questions'])}")
    typer.echo(f"  Mean earned: {payload['score_summary']['earned']['mean']}")
    if "answer_counts" in payload:
        typer.echo(f"  Answer counts: {payload['answer_counts']}")
    if output:
        write_json(output, payload)
        typer.echo(f"Wrote {output}")


@quiz_app.command(
    "import-qti",
    help=(
        "Import a QTI zip as a Classic Quiz, poll the migration to completion, "
        "apply quiz settings, and verify the result."
    ),
)
def quiz_import_qti(
    package: Annotated[Path, typer.Argument(help="QTI zip produced by text2qti/make-qti.")],
    course_id: CourseId = None,
    title: Annotated[
        str | None, typer.Option("--title", help="Quiz title to set after import.")
    ] = None,
    assignment_group_id: Annotated[
        int | None,
        typer.Option("--assignment-group-id", help="Assignment group for the quiz."),
    ] = None,
    due_at: Annotated[
        str | None, typer.Option("--due-at", help="Due timestamp, ISO 8601 UTC.")
    ] = None,
    unlock_at: Annotated[
        str | None, typer.Option("--unlock-at", help="Unlock timestamp, ISO 8601 UTC.")
    ] = None,
    lock_at: Annotated[
        str | None, typer.Option("--lock-at", help="Lock timestamp, ISO 8601 UTC.")
    ] = None,
    time_limit: Annotated[
        int | None, typer.Option("--time-limit", help="Time limit in minutes.")
    ] = None,
    allowed_attempts: Annotated[
        int | None, typer.Option("--allowed-attempts", help="Allowed attempts.")
    ] = None,
    publish: Annotated[
        bool | None,
        typer.Option("--publish/--no-publish", help="Publish state to set after import."),
    ] = None,
    match_title: Annotated[
        str | None,
        typer.Option(
            "--match-title",
            help="Select the imported quiz by exact title when it cannot be identified "
            "automatically. Refuses ambiguous matches.",
        ),
    ] = None,
    poll_seconds: Annotated[
        float, typer.Option("--poll-seconds", help="Delay between migration status checks.")
    ] = 5.0,
    timeout_seconds: Annotated[
        float, typer.Option("--timeout-seconds", help="Maximum time to wait for the migration.")
    ] = 600.0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show the package and settings without importing."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional JSON verification report path."),
    ] = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_quiz_import_qti,
        args_for(
            course_id=course_id,
            package=str(package),
            title=title,
            assignment_group_id=assignment_group_id,
            due_at=due_at,
            unlock_at=unlock_at,
            lock_at=lock_at,
            time_limit=time_limit,
            allowed_attempts=allowed_attempts,
            publish=publish,
            match_title=match_title,
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
            output=str(output) if output else None,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@submissions_app.command(
    "media", help="Download all submission attachments and media comments for one assignment."
)
def submissions_media(
    assignment_id: AssignmentId,
    course_id: CourseId = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir", help="Base directory for downloaded files and .info.json metadata."
        ),
    ] = Path("canvas_assignment_files"),
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_media,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output_dir=str(output_dir),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@submissions_app.command(
    "feedback",
    help="Upload feedback files as submission comments, matching Canvas IDs embedded in filenames.",
)
def submissions_feedback(
    assignment_id: AssignmentId,
    roster_path: Annotated[
        Path, typer.Option("--roster", "-r", help="Roster CSV with a CanvasID column.")
    ],
    feedback_dir: Annotated[
        Path, typer.Option("--feedback-dir", "-d", help="Directory containing feedback files.")
    ],
    course_id: CourseId = None,
    pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            "-p",
            help="Glob pattern inside --feedback-dir, for example '*-feedback.pdf'.",
        ),
    ] = "*",
    comment: Annotated[
        str, typer.Option("--comment", "-c", help="Submission comment text.")
    ] = "Here is your graded feedback.",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show matched/unmatched files without uploading. Recommended first."
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.5,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_feedback,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            roster=str(roster_path),
            feedback_dir=str(feedback_dir),
            pattern=pattern,
            comment=comment,
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "post",
    help="Post assignment grades from CSV. If Comment is present, add it once as a submission comment.",
)
def grades_post(
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path,
        typer.Option(
            "--grades-csv", "-g", help="CSV with CanvasID, Grade, optional Name, optional Comment."
        ),
    ],
    course_id: CourseId = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print rows without posting. Recommended before live grade writes."
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.25,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_post,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "verify", help="Check Canvas grades/comments against a CSV and exit nonzero on mismatch."
)
def grades_verify(
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path, typer.Option("--grades-csv", "-g", help="CSV with CanvasID, Grade, optional Comment.")
    ],
    course_id: CourseId = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_verify,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "export", help="Export all visible posts from one Canvas discussion topic to JSON or CSV."
)
def discussions_export(
    discussion_url: Annotated[
        str, typer.Argument(help="Canvas discussion URL containing course and topic IDs.")
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output file. Use --format csv for spreadsheet review."
        ),
    ] = Path("discussion.json"),
    output_format: Annotated[
        DiscussionExportFormat, typer.Option("--format", help="Output format.")
    ] = "json",
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_export,
        args_for(
            discussion_url=discussion_url,
            output=str(output),
            format=output_format,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "create",
    help="Create one Canvas announcement from Markdown. Use --dry-run first to inspect the payload.",
)
def announcements_create(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source beginning with YAML (---) or TOML (+++) announcement metadata."
        ),
    ],
    course_id: CourseId = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the Canvas payload without creating anything.")
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_create,
        args_for(
            course_id=course_id,
            source=str(source),
            dry_run=dry_run,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "export",
    help="Export course announcements, including only replies from the authenticated user by default.",
)
def announcements_export(
    course_id: CourseId = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output file. Use .json, .csv, or .md, or specify --format.",
        ),
    ] = Path("announcements.json"),
    output_format: Annotated[
        AnnouncementExportFormat,
        typer.Option("--format", help="Output format. 'auto' infers JSON/CSV/Markdown."),
    ] = "auto",
    reply_user_id: Annotated[
        int | None,
        typer.Option(
            "--reply-user-id",
            help="Canvas user ID whose replies should be included. Defaults to authenticated user.",
        ),
    ] = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_export,
        args_for(
            course_id=course_id,
            output=str(output),
            format=output_format,
            reply_user_id=reply_user_id,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "inventory",
    help="Write a Canvas Files inventory JSON/CSV and local missing-file Markdown report.",
)
def files_inventory(
    course_id: CourseId = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory for files-inventory.json, files-inventory.csv, and files-missing-report.md.",
        ),
    ] = Path("canvas-files-inventory"),
    local_root: Annotated[
        Path | None,
        typer.Option(
            "--local-root",
            help="Local course root for filename/size comparison. Omit to inventory Canvas only.",
        ),
    ] = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_inventory,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir),
            local_root=str(local_root) if local_root else None,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "download",
    help="Download all Canvas course Files into a local folder tree and write a manifest.",
)
def files_download(
    course_id: CourseId = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory where Canvas Files should be downloaded.",
        ),
    ] = Path("canvas-files"),
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace local files that already exist."),
    ] = False,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_download,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir),
            overwrite=overwrite,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "upload",
    help="Upload one or more local files to an existing Canvas Files folder.",
)
def files_upload(
    files: Annotated[
        list[Path],
        typer.Argument(help="One or more local files to upload. Directories are rejected."),
    ],
    course_id: CourseId = None,
    folder: Annotated[
        str | None,
        typer.Option(
            "--folder",
            help="Exact Canvas folder full_name, for example 'course files/slides'.",
        ),
    ] = None,
    folder_id: Annotated[
        int | None,
        typer.Option("--folder-id", help="Canvas folder ID. Mutually exclusive with --folder."),
    ] = None,
    on_duplicate: Annotated[
        FileDuplicatePolicy,
        typer.Option(
            "--on-duplicate",
            help="Canvas duplicate filename behavior.",
        ),
    ] = "overwrite",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Resolve the upload plan without uploading files."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional JSON upload report path."),
    ] = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_upload,
        args_for(
            course_id=course_id,
            files=[str(path) for path in files],
            folder=folder,
            folder_id=folder_id,
            on_duplicate=on_duplicate,
            dry_run=dry_run,
            output=str(output) if output else None,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@recordings_app.command(
    "panopto-captions",
    help=(
        "Use the Canvas Panopto LTI tool to list or download Panopto caption text exports."
    ),
)
def recordings_panopto_captions(
    course_id: CourseId = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory for caption files plus manifest.json and manifest.csv.",
        ),
    ] = Path("panopto-captions"),
    folder_id: Annotated[
        str | None,
        typer.Option(
            "--folder-id",
            help="Optional Panopto folder GUID. Omit to list visible recent sessions.",
        ),
    ] = None,
    session_id: Annotated[
        list[str] | None,
        typer.Option(
            "--session-id",
            help="Optional Panopto session GUID. Repeat to restrict to specific sessions.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum Panopto sessions to inspect."),
    ] = 20,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Write manifests without downloading caption files."),
    ] = False,
    caption_language: Annotated[
        str,
        typer.Option(
            "--caption-language",
            help="Panopto caption language value used by the transcript export endpoint.",
        ),
    ] = "English_USA",
    panopto_base_url: Annotated[
        str | None,
        typer.Option(
            "--panopto-base-url",
            help="Override Panopto base URL. Defaults to the Canvas Panopto tool domain.",
        ),
    ] = None,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_panopto_captions,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir),
            folder_id=folder_id,
            session_id=session_id or [],
            limit=limit,
            dry_run=dry_run,
            caption_language=caption_language,
            panopto_base_url=panopto_base_url,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "score",
    help="Score student discussion activity from post/reply counts and optionally upload to the graded discussion.",
)
def discussions_score(
    discussion_url: Annotated[
        str, typer.Argument(help="Canvas discussion URL containing course and topic IDs.")
    ],
    points_per_original: Annotated[float, typer.Argument(help="Points awarded per original post.")],
    points_per_response: Annotated[float, typer.Argument(help="Points awarded per response.")],
    max_original_comments: Annotated[int, typer.Argument(help="Maximum original posts counted.")],
    max_responses: Annotated[int, typer.Argument(help="Maximum responses counted.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional CSV output for scored rows.")
    ] = None,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload", help="Post scores and comments to the discussion's Canvas assignment."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show upload actions without writing to Canvas. Implies upload preview.",
        ),
    ] = False,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.3,
    api_url: ApiUrl = None,
    secret_provider: SecretProviderOption = "auto",
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_score,
        args_for(
            discussion_url=discussion_url,
            points_per_original=points_per_original,
            points_per_response=points_per_response,
            max_original_comments=max_original_comments,
            max_responses=max_responses,
            output=str(output) if output else None,
            upload=upload,
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            api_url=api_url,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


def main() -> None:
    load_dotenv()
    app()


if __name__ == "__main__":
    main()
