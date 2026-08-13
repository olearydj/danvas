"""Typer command surface for danvas."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import typer
from canvasapi.exceptions import ResourceDoesNotExist
from dotenv import load_dotenv

from danvas import __version__, assignment_audit, gradebook, quiz
from danvas.announcements import (
    command_announcements_create,
    command_announcements_export,
    command_announcements_latest,
    command_announcements_sync,
    command_announcements_update,
    command_announcements_verify,
)
from danvas.artifacts import (
    resolve_private_path,
    warn_if_external_private_path,
    write_private_json,
)
from danvas.assignments import (
    command_assignments_create,
    command_assignments_export,
    command_assignments_overrides,
    command_assignments_update,
    command_assignments_upsert,
    command_assignments_verify,
)
from danvas.auth import command_auth_doctor
from danvas.config import command_init, command_refresh, resolve_course_id
from danvas.courses import command_courses, command_roster
from danvas.discussion_sources import (
    command_discussions_create,
    command_discussions_update,
    command_discussions_verify,
)
from danvas.discussions import (
    command_discussions_export,
    command_discussions_score,
    command_discussions_sync_prompts,
)
from danvas.files import (
    command_files_compare,
    command_files_download,
    command_files_download_one,
    command_files_inventory,
    command_files_upload,
)
from danvas.grades import (
    command_grades_clear,
    command_grades_comments,
    command_grades_post,
    command_grades_verify,
)
from danvas.mutation import APPLY_HELP, DRY_RUN_HELP, MutationMode, resolve_mutation_mode
from danvas.override_sync import command_assignments_overrides_sync
from danvas.pages import (
    command_pages_create,
    command_pages_css_check,
    command_pages_export,
    command_pages_list,
    command_pages_render,
    command_pages_sync,
    command_pages_update,
    command_pages_verify,
)
from danvas.panopto import command_panopto_captions
from danvas.profiles import resolve_canvas_context
from danvas.quiz_import import command_quiz_import_qti
from danvas.reports import (
    create_report_run,
    discover_report_runs,
    latest_report_run,
    should_write_report_run,
)
from danvas.source_lint import command_sources_lint
from danvas.status import command_status
from danvas.submissions import (
    command_submissions_export,
    command_submissions_feedback,
    command_submissions_grades,
    command_submissions_media,
)
from danvas.utils import slugify, write_json

SecretProvider = Literal["auto", "1password", "env"]
AssignmentExportFormat = Literal["auto", "json", "csv", "markdown"]
DiscussionExportFormat = Literal["json", "csv"]
AnnouncementExportFormat = Literal["auto", "json", "csv", "markdown"]
AnnouncementLatestFormat = Literal["auto", "json", "markdown"]
FileDuplicatePolicy = Literal["overwrite", "rename"]
AssetDuplicatePolicy = Literal["error", "rename"]
AssignmentUpsertConfirm = Literal["", "create", "update"]
OverrideSyncConfirm = Literal["", "apply"]
SubmissionLayout = Literal["flat", "assignment-subdir"]
SourceKind = Literal["assignment", "announcement", "discussion", "page"]
LintFormat = Literal["text", "json"]
LintFailOn = Literal["error", "warning"]
PageExportFormat = Literal["json", "html", "markdown"]
PageSyncFormat = Literal["html", "markdown"]
RosterSchema = Literal["v2", "legacy-v1"]


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
auth_app = typer.Typer(
    help="Inspect Canvas authentication configuration without printing secrets.",
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
    help="Safely post, clear, and verify CSV grades/comments with private readback evidence.",
    no_args_is_help=True,
)
discussions_app = typer.Typer(
    help="Create, verify, export, update, or score Canvas discussions.",
    no_args_is_help=True,
)
announcements_app = typer.Typer(
    help="Create/export course announcements and filtered instructor replies.",
    no_args_is_help=True,
)
pages_app = typer.Typer(
    help="Render, inspect, sync, create, update, and verify Canvas Pages.",
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
reports_app = typer.Typer(
    help="List and inspect generated .danvas report runs.",
    no_args_is_help=True,
)
sources_app = typer.Typer(
    help="Validate local Canvas-facing authored sources without Canvas access.",
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
app.add_typer(auth_app, name="auth")
app.add_typer(gradebook_app, name="gradebook")
app.add_typer(quiz_app, name="quiz")
app.add_typer(submissions_app, name="submissions")
app.add_typer(grades_app, name="grades")
app.add_typer(discussions_app, name="discussions")
app.add_typer(announcements_app, name="announcements")
app.add_typer(pages_app, name="pages")
app.add_typer(files_app, name="files")
app.add_typer(recordings_app, name="recordings")
app.add_typer(reports_app, name="reports")
app.add_typer(sources_app, name="sources")


ApiUrl = Annotated[
    str | None,
    typer.Option(
        "--api-url",
        help=(
            "Canvas base URL. Overrides project and profile configuration; "
            "CANVAS_API_URL is the final fallback."
        ),
    ),
]
ProfileName = Annotated[
    str | None,
    typer.Option(
        "--profile",
        help="User-level Canvas instance profile from the danvas platform config.",
    ),
]
SecretProviderOption = Annotated[
    SecretProvider | None,
    typer.Option("--secret-provider", help="Secret source for the Canvas API token."),
]
SecretName = Annotated[
    str | None,
    typer.Option("--secret-name", help="secretpath name for the Canvas API token."),
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
CanvasDryRun = Annotated[bool, typer.Option("--dry-run", help=DRY_RUN_HELP)]
CanvasApply = Annotated[bool, typer.Option("--apply", help=APPLY_HELP)]


def mutation_args_from_cli(
    *,
    dry_run: bool,
    apply: bool,
    legacy_live: bool = False,
    confirm: str = "",
    required_confirm: str | set[str] | None = None,
) -> dict[str, Any]:
    """Normalize mutation flags before configuration, authentication, or output."""
    try:
        mode = resolve_mutation_mode(
            dry_run=dry_run,
            apply=apply,
            legacy_live=legacy_live,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    normalized_confirm = confirm.strip()
    if normalized_confirm and mode is MutationMode.PLAN:
        raise typer.BadParameter("--confirm requires --apply.")
    if mode is MutationMode.APPLY and required_confirm is not None:
        allowed = (
            {required_confirm} if isinstance(required_confirm, str) else required_confirm
        )
        if normalized_confirm not in allowed:
            expected = " or ".join(f"--confirm {value}" for value in sorted(allowed))
            raise typer.BadParameter(f"--apply requires {expected}.")
    if legacy_live:
        typer.echo(
            "Warning: --live is deprecated; use --apply instead. "
            "It will be removed in danvas 0.18.0.",
            err=True,
        )
    return {
        "dry_run": mode is MutationMode.PLAN,
        "mutation_mode": mode.value,
    }


def args_for(**kwargs: Any) -> SimpleNamespace:
    """Build the namespace expected by operation modules."""
    canvas_backed = "api_url" in kwargs
    allow_missing_api_url = bool(kwargs.pop("_allow_missing_api_url", False)) or not canvas_backed
    config_start = config_start_for(kwargs)
    if "course_id" in kwargs:
        kwargs["course_id"] = resolve_course_id(kwargs.get("course_id"), start=config_start)
    if not canvas_backed:
        return SimpleNamespace(**kwargs)
    context = resolve_canvas_context(
        explicit_profile=kwargs.get("profile"),
        explicit_api_url=kwargs.get("api_url"),
        explicit_secret_name=kwargs.get("secret_name"),
        explicit_secret_provider=kwargs.get("secret_provider"),
        explicit_op_reference=kwargs.get("op_reference"),
        explicit_api_key_env=kwargs.get("api_key_env"),
        start=config_start,
        allow_missing_api_url=allow_missing_api_url,
    )
    kwargs["profile"] = context.profile
    kwargs["profile_timezone"] = context.profile_timezone
    kwargs["api_url"] = context.api_url
    kwargs["api_url_source"] = context.api_url_source
    kwargs["secret_name"] = context.secret_name
    kwargs["secret_provider"] = context.secret_provider
    kwargs["op_reference"] = context.op_reference
    kwargs["api_key_env"] = context.api_key_env
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


def write_cli_report_run(
    *,
    command: str,
    slug: str,
    project_root: Path,
    report_root: Path | None,
    report_dir: Path | None,
    input_paths: list[Path],
    private_data: bool,
    json_filename: str,
    markdown_filename: str,
    payload: dict[str, Any],
    markdown: str,
) -> None:
    report_run = create_report_run(
        command=command,
        slug=slug,
        project_root=project_root,
        report_root=report_root,
        report_dir=report_dir,
        input_paths=input_paths,
        private_data=private_data,
    )
    try:
        json_path = report_run.write_json(json_filename, payload)
        md_path = report_run.write_text(markdown_filename, markdown)
        manifest_path = report_run.finish()
        typer.echo(f"Wrote {json_path}")
        typer.echo(f"Wrote {md_path}")
        typer.echo(f"Wrote {manifest_path}")
        typer.echo(f"Report directory: {report_run.path}")
    except Exception as exc:
        report_run.finish("failed", error=str(exc))
        raise


def render_gradebook_check_markdown(payload: dict[str, Any]) -> str:
    structure = payload["structure"]
    assignments = payload["assignments"]
    score_variants = payload["score_variants"]
    lines = [
        "# Gradebook Check Report",
        "",
        f"Source: `{payload['source']}`",
        "",
        "## Summary",
        "",
        f"- Included rows: `{structure['included_rows']}`",
        f"- Columns: `{structure['columns']}`",
        f"- Final score column: `{structure['final_score_column']}`",
        f"- Assignment columns: `{assignments['detected_columns']}`",
        f"- Assignment groups: `{assignments['detected_groups']}`",
        f"- Score variant diff rows: `{score_variants['rows_with_differences']}`",
        "",
        "## Missing Or Nonnumeric Values",
        "",
    ]
    totals = payload["missing"]["totals"]
    if totals:
        for label, count in sorted(totals.items()):
            lines.append(f"- {label}: `{count}`")
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def render_gradebook_audit_markdown(payload: dict[str, Any]) -> str:
    recon = payload["reconstruction"]
    lines = [
        "# Gradebook Audit Report",
        "",
        f"Source: `{payload['source']}`",
        "",
        "## Summary",
        "",
        f"- Final score column: `{payload['final_score_column']}`",
        f"- Weight sum: `{payload['weight_sum']}`",
        f"- Matched groups: `{len(payload['matched_group_columns'])}`",
        f"- Rows compared: `{recon['rows_compared']}`",
        f"- Max absolute difference: `{recon['max_abs_diff']}`",
        f"- Rows over tolerance: `{recon['rows_over_tolerance']}`",
        f"- Status: `{recon['status']}`",
        "",
        "## Missing Weighted Groups",
        "",
    ]
    if payload["missing_weight_groups"]:
        lines.extend(f"- {group}" for group in payload["missing_weight_groups"])
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def render_quiz_analysis_markdown(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    earned = payload["score_summary"]["earned"]
    lines = [
        "# Quiz Analysis Report",
        "",
        f"Source: `{payload['source']}`",
        "",
        "## Summary",
        "",
        f"- Students: `{rows['students']}`",
        f"- Submitted: `{rows['submitted']}`",
        f"- Missing submissions: `{rows['missing_submissions']}`",
        f"- Question pairs: `{len(payload['questions'])}`",
        f"- Mean earned: `{earned['mean']}`",
    ]
    if "answer_counts" in payload:
        lines.extend(["", "## Answer Counts", ""])
        for term, counts in payload["answer_counts"].items():
            lines.append(f"### {term}")
            for answer, count in sorted(counts.items()):
                lines.append(f"- {answer}: `{count}`")
    return "\n".join(lines).rstrip() + "\n"


def write_payload_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_explicit_private_json(
    *, command_name: str, output: Path, project_root: Path, payload: dict[str, Any]
) -> None:
    resolved = resolve_private_path(
        explicit=output,
        project_root=project_root,
        default_relative=output.name,
        option_name="--output",
    )
    warn_if_external_private_path(resolved)
    try:
        write_private_json(resolved.path, payload, command=command_name)
    except FileExistsError as exc:
        raise SystemExit(f"Refusing to overwrite existing private output: {resolved.path}") from exc


def echo_report_rows(rows: list[dict[str, Any]], *, root: Path | None = None) -> None:
    if root:
        typer.echo(f"Reports: {root}")
    if not rows:
        typer.echo("No report runs found.")
        return
    for row in rows:
        status = row["status"] or row["manifest_status"]
        command = row["command"] or "(unknown command)"
        slug = row["report_slug"] or "(unknown slug)"
        generated = row["generated_at"] or "(unknown time)"
        scope = row.get("storage_scope") or "reports"
        typer.echo(f"{scope}:{row['name']}  {status}  {slug}  {command}  {generated}")
        if row["manifest_status"] != "valid":
            typer.echo(f"  manifest: {row['manifest_status']}")
            if row.get("error"):
                typer.echo(f"  error: {row['error']}")


def echo_report_detail(row: dict[str, Any]) -> None:
    typer.echo(f"Report: {row['name']}")
    typer.echo(f"  Storage: {row.get('storage_scope') or 'reports'}")
    typer.echo(f"  Path: {row['path']}")
    typer.echo(f"  Command: {row['command']}")
    typer.echo(f"  Slug: {row['report_slug']}")
    typer.echo(f"  Status: {row['status']}")
    typer.echo(f"  Generated: {row['generated_at']}")
    typer.echo(f"  Course ID: {row['course_id']}")
    typer.echo(f"  Private student data: {row['may_contain_private_student_data']}")
    if row.get("error"):
        typer.echo(f"  Error: {row['error']}")
    files = row.get("files") or []
    if files:
        typer.echo("  Files:")
        for file_name in files:
            typer.echo(f"    - {file_name}")
    else:
        typer.echo("  Files: none recorded")


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
        str | None,
        typer.Option(
            "--timezone",
            help=(
                "Course-local IANA timezone. Defaults to Canvas course metadata, "
                "then the selected profile."
            ),
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing .danvas/config.toml.")
    ] = False,
    require_complete: Annotated[
        bool,
        typer.Option(
            "--require-complete",
            help="Exit 3 without writing project state if any snapshot collection is partial.",
        ),
    ] = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
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
            require_complete=require_complete,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@auth_app.command(
    "doctor",
    help="Check secretpath and optional Canvas API authentication without printing secrets.",
)
def auth_doctor(
    check_canvas: Annotated[
        bool,
        typer.Option(
            "--check-canvas", help="Resolve the Canvas token and call Canvas current user."
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_auth_doctor,
        args_for(
            _allow_missing_api_url=True,
            check_canvas=check_canvas,
            json=json_output,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@app.command(
    "refresh",
    help=(
        "Refresh .danvas/course.json from Canvas using --course-id or .danvas/config.toml. "
        "Optional endpoint failures produce an explicit partial snapshot."
    ),
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
    require_complete: Annotated[
        bool,
        typer.Option(
            "--require-complete",
            help="Exit 3 without replacing snapshot state if any collection is partial.",
        ),
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated refresh diff report run."),
    ] = None,
    report_dir: Annotated[
        Path | None,
        typer.Option("--report-dir", help="Exact refresh diff report run directory to create."),
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_refresh,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            diff=diff,
            require_complete=require_complete,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    require_complete: Annotated[
        bool,
        typer.Option(
            "--require-complete",
            help="Write requested evidence, then exit 3 when the source snapshot is partial.",
        ),
    ] = False,
) -> None:
    run_command(
        command_status,
        SimpleNamespace(
            project_root=str(project_root),
            max_age_hours=max_age_hours,
            output=str(output) if output else None,
            report_md=str(report_md) if report_md else None,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            require_complete=require_complete,
        ),
    )


@reports_app.command("list", help="List generated report runs under .danvas/reports.")
def reports_list(
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Reports root to inspect.")
    ] = None,
    slug: Annotated[
        str | None, typer.Option("--slug", help="Only show report runs with this report slug.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON output path.")
    ] = None,
) -> None:
    rows = discover_report_runs(project_root=project_root, report_root=report_root)
    if slug:
        wanted = slugify(slug, "")
        rows = [row for row in rows if row["report_slug"] == wanted]
    if output:
        write_payload_json(output, rows)
        typer.echo(f"Wrote {output}")
    echo_report_rows(rows, root=report_root)


@reports_app.command("latest", help="Show the newest valid report run, optionally by slug.")
def reports_latest(
    slug: Annotated[
        str | None,
        typer.Argument(help="Optional report slug, such as status or files-inventory."),
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Reports root to inspect.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON output path.")
    ] = None,
) -> None:
    row = latest_report_run(slug=slug, project_root=project_root, report_root=report_root)
    if row is None:
        suffix = f" for slug {slug!r}" if slug else ""
        raise typer.BadParameter(f"No valid report run found{suffix}.")
    if output:
        write_payload_json(output, row)
        typer.echo(f"Wrote {output}")
    echo_report_detail(row)


@app.command(
    help=(
        "Export active courses visible to the authenticated Canvas user. The CSV is "
        "course-internal and is not automatically safe to publish."
    )
)
def courses(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="CSV output path: id, name, course_code, start_at, end_at."
        ),
    ] = Path("courses.csv"),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_courses,
        args_for(
            output=str(output),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private CSV output. Defaults to .danvas/private/roster.csv in a project; "
                "required otherwise."
            ),
        ),
    ] = None,
    schema: Annotated[
        RosterSchema,
        typer.Option(
            "--schema",
            help="Roster columns: v2 uses LoginID; legacy-v1 retains the deprecated Email label.",
        ),
    ] = "v2",
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    enrollment_type: Annotated[
        str,
        typer.Option("--enrollment-type", help="Canvas enrollment type to include."),
    ] = "StudentEnrollment",
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_roster,
        args_for(
            course_id=course_id,
            output=str(output) if output else None,
            schema=schema,
            project_root=str(project_root),
            enrollment_type=enrollment_type,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "export", help="Export sanitized assignment evidence as JSON, CSV, or Markdown."
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
        typer.Option("--full", help="Include extended sanitized assignment/group metadata."),
    ] = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
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
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "overrides", help="Export one assignment's override windows and private membership."
)
def assignments_overrides(
    assignment_id: AssignmentId,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private YAML or JSON output. Defaults beneath .danvas/private/overrides in "
                "a project; required otherwise."
            ),
        ),
    ] = None,
    source: Annotated[
        Path | None,
        typer.Option("--source", help="Optional authored assignment source path to record."),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing private output file.")
    ] = False,
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_overrides,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output=str(output) if output else None,
            source=str(source) if source else "",
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "overrides-sync",
    help="Plan override reconciliation; use --apply --confirm apply to write Canvas.",
)
def assignments_overrides_sync(
    source: Annotated[
        Path,
        typer.Argument(help="Assignment Markdown with availability_overrides_ref front matter."),
    ],
    course_id: CourseId = None,
    assignment_id: Annotated[
        int | None,
        typer.Option("--assignment-id", help="Canvas assignment ID, overriding local provenance."),
    ] = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Deprecated alias for --apply; removed in danvas 0.18.0.",
        ),
    ] = False,
    confirm: Annotated[
        OverrideSyncConfirm,
        typer.Option("--confirm", help="Applying requires the exact value 'apply'."),
    ] = "",
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default private report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact private report directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(
        dry_run=dry_run,
        apply=apply,
        legacy_live=live,
        confirm=confirm,
        required_confirm="apply",
    )
    run_command(
        command_assignments_overrides_sync,
        args_for(
            course_id=course_id,
            source=str(source),
            assignment_id=assignment_id,
            **mutation,
            confirm=confirm,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "create",
    help="Plan one assignment from Markdown; use --apply to create it in Canvas.",
)
def assignments_create(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source beginning with YAML (---) or TOML (+++) assignment metadata."
        ),
    ],
    course_id: CourseId = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    asset_folder: Annotated[
        str | None,
        typer.Option("--asset-folder", help="Existing Canvas Files folder for local assets."),
    ] = None,
    asset_folder_id: Annotated[
        int | None,
        typer.Option("--asset-folder-id", help="Existing Canvas Files folder ID for local assets."),
    ] = None,
    asset_on_duplicate: Annotated[
        AssetDuplicatePolicy,
        typer.Option("--asset-on-duplicate", help="Local-asset duplicate behavior."),
    ] = "error",
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_assignments_create,
        args_for(
            course_id=course_id,
            source=str(source),
            **mutation,
            project_root=str(project_root),
            asset_folder=asset_folder,
            asset_folder_id=asset_folder_id,
            asset_on_duplicate=asset_on_duplicate,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "verify",
    help="Verify declared assignment fields and exact current-course Canvas file targets.",
)
def assignments_verify(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source with assignment_id/canvas_id front matter, or pass --assignment-id."
        ),
    ],
    course_id: CourseId = None,
    assignment_id: Annotated[
        int | None,
        typer.Option("--assignment-id", help="Canvas assignment ID to verify against."),
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_assignments_verify,
        args_for(
            course_id=course_id,
            source=str(source),
            assignment_id=assignment_id,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "update",
    help="Plan one assignment update from Markdown; use --apply to write Canvas.",
)
def assignments_update(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source with assignment_id/canvas_id front matter, source-map entry, or --assignment-id."
        ),
    ],
    course_id: CourseId = None,
    assignment_id: Annotated[
        int | None,
        typer.Option("--assignment-id", help="Canvas assignment ID to update."),
    ] = None,
    match_title: Annotated[
        bool,
        typer.Option(
            "--match-title",
            help="Resolve by exact Canvas assignment title only when no ID is available.",
        ),
    ] = False,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    asset_folder: Annotated[
        str | None,
        typer.Option("--asset-folder", help="Existing Canvas Files folder for local assets."),
    ] = None,
    asset_folder_id: Annotated[
        int | None,
        typer.Option("--asset-folder-id", help="Existing Canvas Files folder ID for local assets."),
    ] = None,
    asset_on_duplicate: Annotated[
        AssetDuplicatePolicy,
        typer.Option("--asset-on-duplicate", help="Local-asset duplicate behavior."),
    ] = "error",
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_assignments_update,
        args_for(
            course_id=course_id,
            source=str(source),
            assignment_id=assignment_id,
            match_title=match_title,
            **mutation,
            project_root=str(project_root),
            asset_folder=asset_folder,
            asset_folder_id=asset_folder_id,
            asset_on_duplicate=asset_on_duplicate,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@assignments_app.command(
    "upsert",
    help="Plan whether one assignment source would update an existing assignment or create a new one.",
)
def assignments_upsert(
    source: Annotated[
        Path,
        typer.Argument(help="Markdown source to plan as an assignment create-or-update operation."),
    ],
    course_id: CourseId = None,
    assignment_id: Annotated[
        int | None,
        typer.Option("--assignment-id", help="Canvas assignment ID to update if present."),
    ] = None,
    match_title: Annotated[
        bool,
        typer.Option(
            "--match-title",
            help="Resolve by exact Canvas assignment title only when no ID is available.",
        ),
    ] = False,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    confirm: Annotated[
        AssignmentUpsertConfirm,
        typer.Option(
            "--confirm",
            help="Required with --apply. Must match the planned action: create or update.",
        ),
    ] = "",
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    asset_folder: Annotated[
        str | None,
        typer.Option("--asset-folder", help="Existing Canvas Files folder for local assets."),
    ] = None,
    asset_folder_id: Annotated[
        int | None,
        typer.Option("--asset-folder-id", help="Existing Canvas Files folder ID for local assets."),
    ] = None,
    asset_on_duplicate: Annotated[
        AssetDuplicatePolicy,
        typer.Option("--asset-on-duplicate", help="Local-asset duplicate behavior."),
    ] = "error",
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(
        dry_run=dry_run,
        apply=apply,
        confirm=confirm,
        required_confirm={"create", "update"},
    )
    run_command(
        command_assignments_upsert,
        args_for(
            course_id=course_id,
            source=str(source),
            assignment_id=assignment_id,
            match_title=match_title,
            **mutation,
            confirm=confirm,
            project_root=str(project_root),
            asset_folder=asset_folder,
            asset_folder_id=asset_folder_id,
            asset_on_duplicate=asset_on_duplicate,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    course_yaml: Annotated[
        Path | None,
        typer.Option("--course-yaml", help="Optional course policy YAML with expected weights."),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional JSON audit output path.")
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
) -> None:
    payload = assignment_audit.audit_assignment_file(assignments_path, course_yaml)
    typer.echo(f"Assignment setup audit: {assignments_path}")
    if payload["canvas_weights"]:
        typer.echo(f"  Canvas weight sum: {payload['weight_sum']}")
    if payload.get("expected_weights_note"):
        typer.echo(f"  {payload['expected_weights_note']}")
    if payload["missing_groups"]:
        typer.echo(f"  Missing groups: {', '.join(payload['missing_groups'])}")
    if payload["extra_groups"]:
        typer.echo(f"  Extra groups: {', '.join(payload['extra_groups'])}")
    typer.echo(f"  Assignments: {payload['assignments']['count']}")
    typer.echo(f"  Unpublished: {len(payload['assignments']['unpublished'])}")
    typer.echo(f"  Missing due dates: {len(payload['assignments']['missing_due_dates'])}")
    report_option = bool(report_root or report_dir or report_slug)
    if no_report and report_option:
        raise typer.BadParameter("Use either --no-report or report output options, not both.")
    if output:
        write_json(output, payload)
        typer.echo(f"Wrote {output}")
    report_enabled = not no_report and (not output or report_option)
    if report_enabled:
        report_run = create_report_run(
            command="assignments audit",
            slug=report_slug or "assignment-audit",
            project_root=project_root,
            report_root=report_root,
            report_dir=report_dir,
            input_paths=[assignments_path, *([course_yaml] if course_yaml else [])],
            private_data=False,
        )
        try:
            json_path = report_run.write_json("assignment-audit.json", payload)
            md_path = report_run.write_text(
                "assignment-audit.md",
                assignment_audit.render_assignment_audit_markdown(payload),
            )
            manifest_path = report_run.finish()
            typer.echo(f"Wrote {json_path}")
            typer.echo(f"Wrote {md_path}")
            typer.echo(f"Wrote {manifest_path}")
            typer.echo(f"Report directory: {report_run.path}")
        except Exception as exc:
            report_run.finish("failed", error=str(exc))
            raise


@gradebook_app.command(
    "check",
    help="Inspect a Canvas gradebook CSV export for structure, score variants, and missing cells.",
)
def gradebook_check(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    course_yaml: Annotated[
        Path | None,
        typer.Option(
            "--course-yaml", help="Optional YAML with exclude_students/final_score_column."
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional private JSON check output path."),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
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
        write_explicit_private_json(
            command_name="gradebook check",
            output=output,
            project_root=project_root,
            payload=payload,
        )
        typer.echo(f"Wrote {output}")
    if should_write_report_run(
        no_report=no_report,
        legacy_output=output is not None,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        write_cli_report_run(
            command="gradebook check",
            slug=report_slug or "gradebook-check",
            project_root=project_root,
            report_root=report_root,
            report_dir=report_dir,
            input_paths=[gradebook_csv, *([course_yaml] if course_yaml else [])],
            private_data=True,
            json_filename="gradebook-check.json",
            markdown_filename="gradebook-check.md",
            payload=payload,
            markdown=render_gradebook_check_markdown(payload),
        )


@gradebook_app.command(
    "audit",
    help="Audit final-score setup using a gradebook export and optional course policy/assignment snapshot.",
)
def gradebook_audit(
    gradebook_csv: Annotated[Path, typer.Argument(help="Canvas gradebook CSV export.")],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
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
        Path | None,
        typer.Option("--output", "-o", help="Optional private JSON audit output path."),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
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
        write_explicit_private_json(
            command_name="gradebook audit",
            output=output,
            project_root=project_root,
            payload=payload,
        )
        typer.echo(f"Wrote {output}")
    if should_write_report_run(
        no_report=no_report,
        legacy_output=output is not None,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        write_cli_report_run(
            command="gradebook audit",
            slug=report_slug or "gradebook-audit",
            project_root=project_root,
            report_root=report_root,
            report_dir=report_dir,
            input_paths=[
                gradebook_csv,
                *([course_yaml] if course_yaml else []),
                *([assignments_path] if assignments_path else []),
            ],
            private_data=True,
            json_filename="gradebook-audit.json",
            markdown_filename="gradebook-audit.md",
            payload=payload,
            markdown=render_gradebook_audit_markdown(payload),
        )


@quiz_app.command(
    "analysis", help="Summarize a Canvas Classic Quiz/Survey student-analysis CSV export."
)
def quiz_analysis(
    student_analysis_csv: Annotated[
        Path, typer.Argument(help="Canvas student-analysis CSV export.")
    ],
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    answer_term: Annotated[
        list[str] | None,
        typer.Option(
            "--answer-term",
            help="Question text term to count answers for. Repeat for multiple terms.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional private JSON analysis output path."),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
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
        write_explicit_private_json(
            command_name="quiz analysis",
            output=output,
            project_root=project_root,
            payload=payload,
        )
        typer.echo(f"Wrote {output}")
    if should_write_report_run(
        no_report=no_report,
        legacy_output=output is not None,
        report_root=report_root,
        report_dir=report_dir,
        report_slug=report_slug,
        project_root=project_root,
    ):
        write_cli_report_run(
            command="quiz analysis",
            slug=report_slug or "quiz-analysis",
            project_root=project_root,
            report_root=report_root,
            report_dir=report_dir,
            input_paths=[student_analysis_csv],
            private_data=True,
            json_filename="quiz-analysis.json",
            markdown_filename="quiz-analysis.md",
            payload=payload,
            markdown=render_quiz_analysis_markdown(payload),
        )


@quiz_app.command(
    "import-qti",
    help=(
        "Plan a QTI Classic Quiz import, or apply it with --apply and verify the result."
    ),
)
def quiz_import_qti(
    package: Annotated[Path, typer.Argument(help="QTI zip produced by text2qti/make-qti.")],
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
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
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional JSON verification report path."),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_quiz_import_qti,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
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
            **mutation_args_from_cli(dry_run=dry_run, apply=apply),
            output=str(output) if output else None,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@submissions_app.command(
    "export", help="Export private submission metadata without downloading attachments."
)
def submissions_export(
    assignment_id: AssignmentId,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private JSON or CSV output. Defaults beneath .danvas/private/submissions "
                "in a project; required otherwise."
            ),
        ),
    ] = None,
    include_comments: Annotated[
        bool, typer.Option("--include-comments", help="Include full text submission comments.")
    ] = False,
    include_history: Annotated[
        bool, typer.Option("--include-history", help="Include submission history when available.")
    ] = False,
    save_raw: Annotated[
        Path | None,
        typer.Option("--save-raw", help="Explicit path for private raw Canvas payload JSON."),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing explicit outputs.")
    ] = False,
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_export,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output=str(output) if output else None,
            include_comments=include_comments,
            include_history=include_history,
            save_raw=str(save_raw) if save_raw else None,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@submissions_app.command("grades", help="Export current grades and submission comments for review.")
def submissions_grades(
    assignment_id: AssignmentId,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private JSON or CSV output. Defaults beneath .danvas/private/submissions "
                "in a project; required otherwise."
            ),
        ),
    ] = None,
    only_graded: Annotated[
        bool, typer.Option("--only-graded", help="Exclude submissions without a current grade.")
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing explicit output.")
    ] = False,
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_grades,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output=str(output) if output else None,
            only_graded=only_graded,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
        Path | None,
        typer.Option(
            "--output-dir",
            help=(
                "Private directory for files and .info.json metadata. Defaults beneath "
                ".danvas/private/submissions in a project; required otherwise."
            ),
        ),
    ] = None,
    layout: Annotated[
        SubmissionLayout,
        typer.Option("--layout", help="Use a flat output or an assignment subdirectory."),
    ] = "assignment-subdir",
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing downloaded files.")
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_submissions_media,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            output_dir=str(output_dir) if output_dir else None,
            layout=layout,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private feedback JSON. Defaults to feedback-plan.json for --dry-run and "
                "feedback-results.json for live use beneath .danvas/private/submissions; "
                "required outside a project."
            ),
        ),
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.5,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
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
            output=str(output) if output else None,
            project_root=str(project_root),
            sleep_seconds=sleep_seconds,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "post",
    help="Post CSV grades/comments, classify readback outcomes, and record private evidence.",
)
def grades_post(
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path,
        typer.Option(
            "--grades-csv",
            "-g",
            help=(
                "CSV with CanvasID, Grade, optional Name/Comment, and guarded CommentAction fields."
            ),
        ),
    ],
    course_id: CourseId = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    offline_preview: Annotated[
        bool,
        typer.Option("--offline-preview", help="Print CSV rows without contacting Canvas."),
    ] = False,
    expected_assignment_title: Annotated[
        str | None,
        typer.Option(
            "--expected-assignment-title",
            help="Block if the Canvas assignment title is not this exact value.",
        ),
    ] = None,
    rollback_dir: Annotated[
        Path | None,
        typer.Option(
            "--rollback-dir",
            help=(
                "Private rollback directory. Defaults beneath .danvas/private/grades; "
                "required outside a project for a live run."
            ),
        ),
    ] = None,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.25,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default private report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact private report directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_post,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            **mutation_args_from_cli(dry_run=dry_run, apply=apply),
            offline_preview=offline_preview,
            expected_assignment_title=expected_assignment_title,
            rollback_dir=str(rollback_dir) if rollback_dir else None,
            sleep_seconds=sleep_seconds,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "clear",
    help="Clear targeted grades/comments, classify readback outcomes, and record private evidence.",
)
def grades_clear(
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path,
        typer.Option(
            "--grades-csv",
            "-g",
            help="CSV with CanvasID and optional ExpectedCurrentGrade, ClearGrade, CommentID, Comment.",
        ),
    ],
    course_id: CourseId = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    expected_assignment_title: Annotated[
        str | None,
        typer.Option(
            "--expected-assignment-title",
            help="Block if the Canvas assignment title is not this exact value.",
        ),
    ] = None,
    rollback_dir: Annotated[
        Path | None,
        typer.Option(
            "--rollback-dir",
            help=(
                "Private rollback directory. Defaults beneath .danvas/private/grades; "
                "required outside a project for a live run."
            ),
        ),
    ] = None,
    sleep_seconds: Annotated[
        float, typer.Option("--sleep-seconds", help="Delay between Canvas writes.")
    ] = 0.25,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default private report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact private report directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_clear,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            **mutation_args_from_cli(dry_run=dry_run, apply=apply),
            expected_assignment_title=expected_assignment_title,
            rollback_dir=str(rollback_dir) if rollback_dir else None,
            sleep_seconds=sleep_seconds,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command("comments", help="List one submission's comments and current-user ownership.")
def grades_comments(
    assignment_id: AssignmentId,
    canvas_id: Annotated[int, typer.Option("--canvas-id", help="Canvas user ID.")],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private JSON output. Defaults beneath .danvas/private/grades; "
                "required outside a project."
            ),
        ),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output file.")
    ] = False,
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_comments,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            canvas_id=canvas_id,
            output=str(output) if output else None,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@grades_app.command(
    "verify",
    help="Verify CSV grades/comments and record targeted student release-state evidence.",
)
def grades_verify(
    assignment_id: AssignmentId,
    grades_csv: Annotated[
        Path, typer.Option("--grades-csv", "-g", help="CSV with CanvasID, Grade, optional Comment.")
    ],
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default private report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact private report directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_grades_verify,
        args_for(
            course_id=course_id,
            assignment_id=assignment_id,
            grades_csv=str(grades_csv),
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private output file. Defaults beneath .danvas/private/discussions; "
                "required outside a project."
            ),
        ),
    ] = None,
    output_format: Annotated[
        DiscussionExportFormat, typer.Option("--format", help="Output format.")
    ] = "json",
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing private output pair.")
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_export,
        args_for(
            discussion_url=discussion_url,
            output=str(output) if output else None,
            format=output_format,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "create",
    help="Plan a discussion from Markdown; use --apply to create it in Canvas.",
)
def discussions_create(
    source: Annotated[Path, typer.Argument(help="Authored discussion Markdown source.")],
    course_id: CourseId = None,
    seed_replies: Annotated[
        bool,
        typer.Option(
            "--seed-replies",
            help="Confirm posting all --- reply --- sections as instructor entries.",
        ),
    ] = False,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_discussions_create,
        args_for(
            source=str(source),
            course_id=course_id,
            seed_replies=seed_replies,
            **mutation,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "verify",
    help="Compare authored discussion metadata, body, and known seed entries with Canvas.",
)
def discussions_verify(
    source: Annotated[Path, typer.Argument(help="Authored discussion Markdown source.")],
    course_id: CourseId = None,
    discussion_id: Annotated[
        int | None,
        typer.Option("--discussion-id", min=1, help="Explicit Canvas discussion topic ID."),
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_verify,
        args_for(
            source=str(source),
            course_id=course_id,
            discussion_id=discussion_id,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "update",
    help="Plan a scoped discussion update; use --apply to write the root topic.",
)
def discussions_update(
    source: Annotated[Path, typer.Argument(help="Authored discussion Markdown source.")],
    course_id: CourseId = None,
    discussion_id: Annotated[
        int | None,
        typer.Option("--discussion-id", min=1, help="Explicit Canvas discussion topic ID."),
    ] = None,
    body_only: Annotated[
        bool,
        typer.Option(
            "--body-only",
            help="Update only the root topic body; never alter seed replies or responses.",
        ),
    ] = False,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_discussions_update,
        args_for(
            source=str(source),
            course_id=course_id,
            discussion_id=discussion_id,
            body_only=body_only,
            **mutation,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "sync-prompts",
    help="Create missing local Markdown prompt sources from Canvas discussions.",
)
def discussions_sync_prompts(
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Directory for created discussion prompt Markdown sources.",
        ),
    ] = Path("content/discussions"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan source creation without writing content files."),
    ] = False,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_discussions_sync_prompts,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            output_dir=str(output_dir),
            dry_run=dry_run,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@sources_app.command("lint", help="Lint Canvas-facing local sources without making Canvas calls.")
def sources_lint(
    paths: Annotated[
        list[Path] | None, typer.Argument(help="Source paths, directories, or glob patterns.")
    ] = None,
    kind: Annotated[
        SourceKind | None,
        typer.Option("--kind", help="Force one source kind; otherwise infer per file."),
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course root used for discovery and provenance.")
    ] = Path("."),
    output_format: Annotated[
        LintFormat, typer.Option("--format", help="Human-readable text or JSON.")
    ] = "text",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Explicit JSON output path.")
    ] = None,
    fail_on: Annotated[
        LintFailOn, typer.Option("--fail-on", help="Lowest severity that produces exit 1.")
    ] = "error",
) -> None:
    if output and output_format != "json":
        raise typer.BadParameter("--output requires --format json")
    run_command(
        command_sources_lint,
        args_for(
            paths=[str(path) for path in paths or []],
            kind=kind,
            project_root=str(project_root),
            format=output_format,
            output=str(output) if output else None,
            fail_on=fail_on,
        ),
    )


@pages_app.command("list", help="List Canvas Pages without writing local files.")
def pages_list(
    course_id: CourseId = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_pages_list,
        args_for(
            course_id=course_id,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@pages_app.command("export", help="Export all Pages as JSON or one Page as HTML/Markdown source.")
def pages_export(
    output: Annotated[Path, typer.Option("--output", "-o", help="Explicit output path.")],
    course_id: CourseId = None,
    output_format: Annotated[
        PageExportFormat, typer.Option("--format", help="JSON, native HTML, or Markdown source.")
    ] = "json",
    page_id: Annotated[
        str | None, typer.Option("--page-id", help="Select one Canvas Page by numeric ID.")
    ] = None,
    url: Annotated[
        str | None, typer.Option("--url", help="Select one Canvas Page by exact URL slug.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output file.")
    ] = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_pages_export,
        args_for(
            course_id=course_id,
            output=str(output),
            format=output_format,
            page_id=page_id,
            url=url,
            overwrite=overwrite,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@pages_app.command(
    "sync", help="Create missing local Page sources without overwriting authored files."
)
def pages_sync(
    output_dir: Annotated[
        Path, typer.Option("--output-dir", help="Directory for new Page sources.")
    ],
    course_id: CourseId = None,
    output_format: Annotated[
        PageSyncFormat,
        typer.Option("--format", help="Local Markdown or native HTML source format."),
    ] = "markdown",
    page_id: Annotated[
        str | None, typer.Option("--page-id", help="Limit actions to one numeric Page ID.")
    ] = None,
    url: Annotated[
        str | None, typer.Option("--url", help="Limit actions to one exact Page URL slug.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Plan local source creation without writing files.")
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_pages_sync,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir),
            format=output_format,
            page_id=page_id,
            url=url,
            dry_run=dry_run,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@pages_app.command(
    "render", help="Render a local Page source to a Canvas-compatible HTML fragment."
)
def pages_render(
    source: Annotated[Path, typer.Argument(help="Markdown or HTML Page source with front matter.")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output path, or - for stdout.")
    ] = "-",
) -> None:
    run_command(command_pages_render, args_for(source=str(source), output=output))


@pages_app.command(
    "css-check", help="Validate restricted Canvas CSS and optionally show its inline plan."
)
def pages_css_check(
    css: Annotated[Path, typer.Argument(help="Restricted .canvas.css sidecar.")],
    source: Annotated[
        Path | None,
        typer.Option("--source", help="Optional Page source used to test selector matches."),
    ] = None,
) -> None:
    run_command(
        command_pages_css_check, args_for(css=str(css), source=str(source) if source else None)
    )


@pages_app.command(
    "create", help="Plan one Page; use --apply to create it and verify Canvas readback."
)
def pages_create(
    source: Annotated[Path, typer.Argument(help="Markdown or HTML Page source with front matter.")],
    course_id: CourseId = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_pages_create,
        args_for(
            course_id=course_id,
            source=str(source),
            **mutation,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@pages_app.command(
    "update",
    help="Plan Page body/publication changes; use --apply to write Canvas.",
)
def pages_update(
    source: Annotated[Path, typer.Argument(help="Page source resolvable by ID or source map.")],
    course_id: CourseId = None,
    page_id: Annotated[
        str | None, typer.Option("--page-id", help="Canvas Page numeric ID or URL slug.")
    ] = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_pages_update,
        args_for(
            course_id=course_id,
            source=str(source),
            page_id=page_id,
            **mutation,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@pages_app.command(
    "verify", help="Verify a rendered Page source and publication state against Canvas."
)
def pages_verify(
    source: Annotated[Path, typer.Argument(help="Page source resolvable by ID or source map.")],
    course_id: CourseId = None,
    page_id: Annotated[
        str | None, typer.Option("--page-id", help="Canvas Page numeric ID or URL slug.")
    ] = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_pages_verify,
        args_for(
            course_id=course_id,
            source=str(source),
            page_id=page_id,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "create",
    help="Plan one announcement from Markdown; use --apply to create it in Canvas.",
)
def announcements_create(
    source: Annotated[
        Path,
        typer.Argument(
            help="Markdown source beginning with YAML (---) or TOML (+++) announcement metadata."
        ),
    ],
    course_id: CourseId = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_announcements_create,
        args_for(
            course_id=course_id,
            source=str(source),
            **mutation,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private output file. Defaults beneath .danvas/private/announcements; "
                "required outside a project."
            ),
        ),
    ] = None,
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
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing private output pair.")
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_export,
        args_for(
            course_id=course_id,
            output=str(output) if output else None,
            format=output_format,
            reply_user_id=reply_user_id,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "latest",
    help="Export the latest Canvas announcement as Markdown or JSON.",
)
def announcements_latest(
    course_id: CourseId = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional output file. Omit to print to stdout.",
        ),
    ] = None,
    output_format: Annotated[
        AnnouncementLatestFormat,
        typer.Option(
            "--format", help="Output format. 'auto' uses Markdown unless output is .json."
        ),
    ] = "auto",
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_latest,
        args_for(
            course_id=course_id,
            output=str(output) if output else None,
            format=output_format,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "sync",
    help="Create missing local Markdown sources from Canvas announcements without overwriting.",
)
def announcements_sync(
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Directory for created announcement Markdown sources.",
        ),
    ] = Path("content/announcements"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan source creation without writing content files."),
    ] = False,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_sync,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            output_dir=str(output_dir),
            dry_run=dry_run,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "update",
    help="Plan one announcement update from Markdown; use --apply to write Canvas.",
)
def announcements_update(
    source: Annotated[
        Path,
        typer.Argument(
            help="Local announcement Markdown source with canvas_id, source-map entry, or --announcement-id."
        ),
    ],
    course_id: CourseId = None,
    announcement_id: Annotated[
        int | None,
        typer.Option(
            "--announcement-id",
            help="Canvas announcement/discussion topic ID. Overrides source canvas_id.",
        ),
    ] = None,
    dry_run: CanvasDryRun = False,
    apply: CanvasApply = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None, typer.Option("--report-root", help="Root for a dated report run directory.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    mutation = mutation_args_from_cli(dry_run=dry_run, apply=apply)
    run_command(
        command_announcements_update,
        args_for(
            course_id=course_id,
            source=str(source),
            announcement_id=announcement_id,
            **mutation,
            project_root=str(project_root),
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@announcements_app.command(
    "verify",
    help="Verify one local announcement Markdown source against Canvas by ID.",
)
def announcements_verify(
    source: Annotated[
        Path,
        typer.Argument(help="Local announcement Markdown source with canvas_id front matter."),
    ],
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    announcement_id: Annotated[
        int | None,
        typer.Option(
            "--announcement-id",
            help="Canvas announcement/discussion topic ID. Overrides source canvas_id.",
        ),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_announcements_verify,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            source=str(source),
            announcement_id=announcement_id,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help=(
                "Legacy output directory for files-inventory.json, files-inventory.csv, "
                "and files-missing-report.md. Omit to write a report run."
            ),
        ),
    ] = None,
    local_root: Annotated[
        Path | None,
        typer.Option(
            "--local-root",
            help="Local course root for filename/size comparison. Omit to inventory Canvas only.",
        ),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_inventory,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            output_dir=str(output_dir) if output_dir else None,
            local_root=str(local_root) if local_root else None,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_download,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir),
            overwrite=overwrite,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "download-one",
    help="Download exactly one Canvas course file to an explicit output path.",
)
def files_download_one(
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file for the downloaded Canvas file."),
    ] = None,
    file_id: Annotated[
        int | None,
        typer.Option("--file-id", help="Canvas file ID. Mutually exclusive with --canvas-path."),
    ] = None,
    canvas_path: Annotated[
        str | None,
        typer.Option(
            "--canvas-path",
            help=("Exact Canvas Files path, for example 'course files/slides/example.pptx'."),
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace the output file if it already exists."),
    ] = False,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_download_one,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            output=str(output) if output else None,
            file_id=file_id,
            canvas_path=canvas_path,
            overwrite=overwrite,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "compare",
    help="Compare Canvas file metadata with one local file and write a report run.",
)
def files_compare(
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    local: Annotated[
        Path | None,
        typer.Option("--local", help="Local file to compare against Canvas metadata."),
    ] = None,
    file_id: Annotated[
        int | None,
        typer.Option("--file-id", help="Canvas file ID. Mutually exclusive with --canvas-path."),
    ] = None,
    canvas_path: Annotated[
        str | None,
        typer.Option(
            "--canvas-path",
            help=("Exact Canvas Files path, for example 'course files/slides/example.pptx'."),
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional JSON comparison report path."),
    ] = None,
    downloaded_canvas: Annotated[
        Path | None,
        typer.Option(
            "--downloaded-canvas",
            help="Previously downloaded Canvas file to hash against --local.",
        ),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_compare,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            local=str(local) if local else None,
            file_id=file_id,
            canvas_path=canvas_path,
            output=str(output) if output else None,
            downloaded_canvas=str(downloaded_canvas) if downloaded_canvas else None,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@files_app.command(
    "upload",
    help="Plan or upload files with duplicate-action and stable-link evidence.",
)
def files_upload(
    files: Annotated[
        list[Path],
        typer.Argument(help="One or more local files to upload. Directories are rejected."),
    ],
    course_id: CourseId = None,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
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
        typer.Option(
            "--dry-run",
            help="Inspect the destination and classify create/overwrite/rename without uploading.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional JSON upload report path."),
    ] = None,
    no_report: Annotated[
        bool, typer.Option("--no-report", help="Suppress the default report run.")
    ] = False,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Root for a dated report run directory."),
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option("--report-dir", help="Exact report run directory to create.")
    ] = None,
    report_slug: Annotated[
        str | None, typer.Option("--report-slug", help="Override the report run slug.")
    ] = None,
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_files_upload,
        args_for(
            course_id=course_id,
            project_root=str(project_root),
            files=[str(path) for path in files],
            folder=folder,
            folder_id=folder_id,
            on_duplicate=on_duplicate,
            dry_run=dry_run,
            output=str(output) if output else None,
            no_report=no_report,
            report_root=str(report_root) if report_root else None,
            report_dir=str(report_dir) if report_dir else None,
            report_slug=report_slug,
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@recordings_app.command(
    "panopto-captions",
    help=("Use the Canvas Panopto LTI tool to list or download Panopto caption text exports."),
)
def recordings_panopto_captions(
    course_id: CourseId = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help=(
                "Private caption bundle. Defaults beneath .danvas/private/recordings; "
                "required outside a project."
            ),
        ),
    ] = None,
    folder_id: Annotated[
        str | None,
        typer.Option(
            "--folder-id",
            help="Optional Panopto folder GUID. Omit to list visible recent sessions.",
        ),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing private bundle manifests.")
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
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
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
    op_reference: OpReference = None,
    api_key_env: ApiKeyEnv = None,
) -> None:
    run_command(
        command_panopto_captions,
        args_for(
            course_id=course_id,
            output_dir=str(output_dir) if output_dir else None,
            folder_id=folder_id,
            session_id=session_id or [],
            limit=limit,
            dry_run=dry_run,
            caption_language=caption_language,
            panopto_base_url=panopto_base_url,
            overwrite=overwrite,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
            secret_provider=secret_provider,
            op_reference=op_reference,
            api_key_env=api_key_env,
        ),
    )


@discussions_app.command(
    "score",
    help=(
        "Score discussion activity and write a private grade plan for the grades post transaction."
    ),
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
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Private CSV grade plan. Defaults beneath .danvas/private/discussions; "
                "required outside a project."
            ),
        ),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing private grade plan pair.")
    ] = False,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload",
            help=(
                "Deprecated migration spelling: write the plan, print the grades post replacement, "
                "and exit nonzero. Never uploads."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Explicit spelling for the default plan-only behavior.",
        ),
    ] = False,
    project_root: Annotated[
        Path, typer.Option("--project-root", help="Course project root containing .danvas.")
    ] = Path("."),
    profile: ProfileName = None,
    api_url: ApiUrl = None,
    secret_name: SecretName = None,
    secret_provider: SecretProviderOption = None,
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
            overwrite=overwrite,
            upload=upload,
            dry_run=dry_run,
            project_root=str(project_root),
            profile=profile,
            api_url=api_url,
            secret_name=secret_name,
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
