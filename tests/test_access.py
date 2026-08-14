from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import click
import pytest
import typer

from danvas.access import ACCESS_POLICIES, CommandAccessPolicy, DryRunKind, access_policy
from danvas.artifacts import ARTIFACT_POLICIES
from danvas.cli import app

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "danvas"
OUTPUT_OPTIONS = {
    "--output",
    "--output-dir",
    "--report-md",
    "--report-root",
    "--report-dir",
    "--rollback-dir",
    "--save-raw",
}
POSITIONAL_OUTPUT_NAMES = {"output", "output_dir", "destination"}
IMPLICIT_RETAINED_OUTPUT_COMMANDS = {"init", "skill install"}
NONRETAINED_INTERFACE_ARTIFACT_COMMANDS = {
    "guide",
    "describe",
    "skill show",
    "skill doctor",
}

CURRENT_DRY_RUN_DEFAULTS = {
    "assignments overrides-sync": False,
    "assignments create": False,
    "assignments update": False,
    "assignments upsert": False,
    "quiz import-qti": False,
    "submissions feedback": False,
    "grades post": False,
    "grades clear": False,
    "discussions create": False,
    "discussions update": False,
    "discussions sync-prompts": False,
    "pages sync": False,
    "pages create": False,
    "pages update": False,
    "announcements create": False,
    "announcements sync": False,
    "announcements update": False,
    "files upload": False,
    "recordings panopto-captions": False,
    "discussions score": False,
    "skill install": False,
}
PLAN_ONLY_DRY_RUN_COMMANDS = {"discussions score"}

CURRENT_MUTATION_CALLS = Counter(
    {
        ("announcements.py", "command_announcements_create", "create_discussion_topic"): 1,
        ("announcements.py", "command_announcements_update", "topic.update"): 1,
        ("assignments.py", "create_assignment_from_loaded_source", "create_assignment"): 1,
        ("assignments.py", "update_assignment_from_loaded_source", "edit"): 1,
        ("authored_assets.py", "upload_one_asset", "upload"): 1,
        ("discussion_sources.py", "command_discussions_create", "create_discussion_topic"): 1,
        ("discussion_sources.py", "command_discussions_update", "topic.update"): 1,
        ("discussion_sources.py", "post_seed_replies", "post_entry"): 1,
        ("files.py", "execute_file_upload", "upload"): 1,
        ("grades.py", "apply_grade_action", "edit"): 2,
        ("grades.py", "edit_submission_comment", "edit_comment"): 1,
        ("grades.py", "edit_submission_comment", "_requester.request"): 1,
        ("grades.py", "delete_submission_comment", "delete_comment"): 1,
        ("grades.py", "delete_submission_comment", "_requester.request"): 1,
        ("override_sync.py", "apply_override_sync", "edit"): 1,
        ("override_sync.py", "apply_override_sync", "create_override"): 1,
        ("pages.py", "command_pages_create", "create_page"): 1,
        ("pages.py", "command_pages_update", "edit"): 1,
        ("panopto.py", "establish_lti_session", "web.post"): 1,
        ("panopto.py", "lti_get_sessions", "web.post"): 1,
        ("quiz_import.py", "command_quiz_import_qti", "edit"): 1,
        ("quiz_import.py", "start_qti_migration", "create_content_migration"): 1,
        ("quiz_import.py", "start_qti_migration", "requests.post"): 1,
        ("quiz_reports.py", "request_student_analysis_report", "_requester.request"): 1,
        ("submissions.py", "upload_feedback_comment", "attachment_uploader.start"): 1,
        ("submissions.py", "upload_feedback_comment", "edit"): 1,
    }
)

CURRENT_APPLY_COMMANDS = {
    "assignments overrides-sync",
    "assignments create",
    "assignments update",
    "assignments upsert",
    "discussions create",
    "discussions update",
    "pages create",
    "pages update",
    "announcements create",
    "announcements update",
    "quiz import-qti",
    "grades post",
    "grades clear",
    "submissions feedback",
    "files upload",
}

CURRENT_MUTATION_ASSERTIONS = Counter(
    {
        ("announcements.py", "command_announcements_create"): 1,
        ("announcements.py", "command_announcements_update"): 1,
        ("assignments.py", "create_assignment_from_loaded_source"): 1,
        ("assignments.py", "command_assignments_create"): 1,
        ("assignments.py", "command_assignments_update"): 1,
        ("assignments.py", "command_assignments_upsert"): 1,
        ("assignments.py", "execute_assignment_asset_plan"): 1,
        ("assignments.py", "update_assignment_from_loaded_source"): 1,
        ("authored_assets.py", "execute_asset_plan"): 1,
        ("discussion_sources.py", "command_discussions_create"): 1,
        ("discussion_sources.py", "command_discussions_update"): 1,
        ("discussion_sources.py", "post_seed_replies"): 1,
        ("override_sync.py", "apply_override_sync"): 1,
        ("override_sync.py", "command_assignments_overrides_sync"): 1,
        ("pages.py", "command_pages_create"): 1,
        ("pages.py", "command_pages_update"): 1,
        ("grades.py", "command_grades_post"): 1,
        ("grades.py", "command_grades_clear"): 1,
        ("grades.py", "apply_grade_plan"): 1,
        ("grades.py", "apply_grade_action"): 1,
        ("grades.py", "edit_submission_comment"): 1,
        ("grades.py", "delete_submission_comment"): 1,
        ("quiz_import.py", "command_quiz_import_qti"): 2,
        ("quiz_import.py", "start_qti_migration"): 2,
        ("quiz_reports.py", "request_student_analysis_report"): 1,
        ("submissions.py", "command_submissions_feedback"): 1,
        ("submissions.py", "upload_feedback_comment"): 2,
        ("files.py", "command_files_upload"): 1,
        ("files.py", "execute_file_upload"): 1,
    }
)


def root_command() -> click.Command:
    return typer.main.get_command(app)


def leaf_commands() -> dict[str, click.Command]:
    found: dict[str, click.Command] = {}

    def visit(command: click.Command, prefix: tuple[str, ...] = ()) -> None:
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                visit(child, (*prefix, name))
            return
        found[" ".join(prefix)] = command

    visit(root_command())
    return found


def option(command: click.Command, name: str) -> click.Option:
    for param in command.params:
        if isinstance(param, click.Option) and name in (*param.opts, *param.secondary_opts):
            return param
    raise AssertionError(f"Missing {name} on {command.name}")


def retained_output_commands() -> set[str]:
    found = set(IMPLICIT_RETAINED_OUTPUT_COMMANDS)
    for name, command in leaf_commands().items():
        for param in command.params:
            if isinstance(param, click.Option) and OUTPUT_OPTIONS.intersection(
                (*param.opts, *param.secondary_opts)
            ):
                found.add(name)
            if isinstance(param, click.Argument) and param.name in POSITIONAL_OUTPUT_NAMES:
                found.add(name)
    return found


def mutation_call_name(node: ast.Call) -> str | None:
    function = node.func
    if not isinstance(function, ast.Attribute):
        return None
    if function.attr in {
        "create_assignment",
        "create_content_migration",
        "create_discussion_topic",
        "create_override",
        "create_page",
        "delete_comment",
        "edit",
        "edit_comment",
        "post_entry",
        "upload",
        "upload_comment",
    }:
        return function.attr
    if (
        function.attr == "start"
        and isinstance(function.value, ast.Name)
        and function.value.id == "attachment_uploader"
    ):
        return "attachment_uploader.start"
    if function.attr == "update" and isinstance(function.value, ast.Name):
        return "topic.update" if function.value.id == "topic" else None
    if function.attr == "request" and isinstance(function.value, ast.Attribute):
        if function.value.attr != "_requester" or not node.args:
            return None
        method = node.args[0]
        if not isinstance(method, ast.Constant) or not isinstance(method.value, str):
            return "_requester.request"
        return (
            "_requester.request"
            if method.value.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            else None
        )
    if function.attr in {"post", "put"}:
        return f"{ast.unparse(function.value)}.{function.attr}"
    if function.attr in {"delete", "publish", "submit"}:
        return function.attr
    return None


def canvas_mutation_calls() -> Counter[tuple[str, str, str]]:
    found: Counter[tuple[str, str, str]] = Counter()
    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                call_name = mutation_call_name(node)
                if call_name:
                    found[(path.name, function.name, call_name)] += 1
    return found


def canvas_mutation_assertions() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "assert_canvas_mutation_allowed"
                ):
                    found[(path.name, function.name)] += 1
    return found


def test_access_policy_registry_matches_click_tree_exactly() -> None:
    commands = set(leaf_commands())

    assert len(commands) == 60
    assert len(ACCESS_POLICIES) == 60
    assert set(ACCESS_POLICIES) == commands


def test_access_policy_category_counts_match_reviewed_inventory() -> None:
    policies = tuple(ACCESS_POLICIES.values())

    assert sum(not policy.canvas_read for policy in policies) == 15
    assert (
        sum(
            policy.canvas_read
            and not policy.canvas_mutation
            and policy.dry_run_kind is DryRunKind.NONE
            for policy in policies
        )
        == 26
    )
    assert sum(policy.dry_run_kind is DryRunKind.LOCAL_WRITE for policy in policies) == 5
    assert sum(policy.canvas_mutation for policy in policies) == 15
    assert sum(policy.bare_canvas_mutation for policy in policies) == 0


def test_current_dry_run_surface_and_defaults_are_characterized() -> None:
    commands = leaf_commands()
    actual = {
        name: option(command, "--dry-run").default
        for name, command in commands.items()
        if any(
            "--dry-run" in (*param.opts, *param.secondary_opts)
            for param in command.params
            if isinstance(param, click.Option)
        )
    }

    assert actual == CURRENT_DRY_RUN_DEFAULTS
    assert {
        name
        for name, policy in ACCESS_POLICIES.items()
        if policy.dry_run_kind is not DryRunKind.NONE
    } | PLAN_ONLY_DRY_RUN_COMMANDS == set(actual)


def test_current_special_mutation_guards_are_characterized() -> None:
    commands = leaf_commands()

    overrides = commands["assignments overrides-sync"]
    assert option(overrides, "--dry-run").default is False
    assert option(overrides, "--apply").default is False
    assert option(overrides, "--confirm").default == ""
    assert option(commands["assignments upsert"], "--confirm").default == ""
    assert all(
        "--upload" not in (*param.opts, *param.secondary_opts)
        for param in commands["discussions score"].params
        if isinstance(param, click.Option)
    )
    assert all(
        "--sleep-seconds" not in (*param.opts, *param.secondary_opts)
        for param in commands["discussions score"].params
        if isinstance(param, click.Option)
    )
    assert option(commands["files upload"], "--on-duplicate").default == "error"


def test_retained_output_registry_has_no_missing_or_stale_commands() -> None:
    assert set(ARTIFACT_POLICIES) == (
        retained_output_commands() | NONRETAINED_INTERFACE_ARTIFACT_COMMANDS
    )


def test_canvas_mutation_call_sites_match_reviewed_baseline() -> None:
    assert canvas_mutation_calls() == CURRENT_MUTATION_CALLS


def test_current_apply_surface_is_exact() -> None:
    actual = {
        name
        for name, command in leaf_commands().items()
        if any(
            "--apply" in (*param.opts, *param.secondary_opts)
            for param in command.params
            if isinstance(param, click.Option)
        )
    }

    assert actual == CURRENT_APPLY_COMMANDS


def test_common_pre_write_assertion_sites_match_reviewed_baseline() -> None:
    assert canvas_mutation_assertions() == CURRENT_MUTATION_ASSERTIONS


def test_access_policy_rejects_incoherent_declarations() -> None:
    with pytest.raises(ValueError, match="must also declare Canvas read"):
        CommandAccessPolicy(command="bad", canvas_mutation=True)
    with pytest.raises(ValueError, match="Bare mutation requires"):
        CommandAccessPolicy(command="bad", bare_canvas_mutation=True)
    with pytest.raises(ValueError, match="Mutation dry-run requires"):
        CommandAccessPolicy(command="bad", dry_run_kind=DryRunKind.CANVAS_MUTATION)
    with pytest.raises(ValueError, match="Local dry-run requires"):
        CommandAccessPolicy(command="bad", dry_run_kind=DryRunKind.LOCAL_WRITE)


def test_access_policy_lookup_rejects_unknown_command() -> None:
    assert access_policy("grades post").grade_affecting is True
    assert access_policy("submissions feedback").authoritative_verification is True
    with pytest.raises(ValueError, match="No access policy"):
        access_policy("unknown command")
