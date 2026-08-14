from __future__ import annotations

import ast
import json
from pathlib import Path

import click
import typer
from typer.testing import CliRunner

from danvas.access import ACCESS_POLICIES, DryRunKind
from danvas.artifacts import ARTIFACT_POLICIES, ArtifactClass
from danvas.cli import app
from danvas.command_description import describe_payload
from danvas.command_guides import COMMAND_GUIDES, ExampleStage
from danvas.offline_guides import render_guide
from danvas.quiz import StudentAnalysisReport, analyze_student_analysis
from danvas.skill_resources import canonical_skill_files

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sprint23"
runner = CliRunner()


def root_command() -> click.Command:
    return typer.main.get_command(app)


def quiz_commands() -> dict[str, click.Command]:
    root = root_command()
    assert isinstance(root, click.Group)
    quiz = root.commands["quiz"]
    assert isinstance(quiz, click.Group)
    return dict(quiz.commands)


def test_quiz_surface_includes_reviewed_report_acquisition() -> None:
    assert set(quiz_commands()) == {"analysis", "export-analysis", "import-qti"}

    acquisition = ACCESS_POLICIES["quiz export-analysis"]
    assert acquisition.canvas_read is True
    assert acquisition.canvas_mutation is True
    assert acquisition.local_write is True
    assert acquisition.dry_run_kind is DryRunKind.CANVAS_MUTATION
    assert acquisition.bare_canvas_mutation is False
    assert acquisition.authoritative_verification is True
    assert (
        ARTIFACT_POLICIES["quiz export-analysis"].artifact_class
        is ArtifactClass.PRIVATE
    )
    assert COMMAND_GUIDES["quiz export-analysis"].guide_topics == ("content", "safety")

    analysis = ACCESS_POLICIES["quiz analysis"]
    assert analysis.canvas_read is False
    assert analysis.canvas_mutation is False
    assert analysis.local_write is True
    assert analysis.dry_run_kind is DryRunKind.NONE
    assert ARTIFACT_POLICIES["quiz analysis"].artifact_class is ArtifactClass.PRIVATE


def test_quiz_help_and_description_expose_export_then_analyze_workflow() -> None:
    help_result = runner.invoke(app, ["quiz", "--help"], color=False)
    assert help_result.exit_code == 0
    help_text = click.unstyle(help_result.output)
    assert "analysis" in help_text
    assert "import-qti" in help_text
    assert "export-analysis" in help_text
    assert "Export then analyze" in help_text

    payload = describe_payload(root_command(), ("quiz",))
    children = {child["command_path"]: child for child in payload["command"]["children"]}
    assert set(children) == {
        "quiz analysis",
        "quiz export-analysis",
        "quiz import-qti",
    }
    assert children["quiz analysis"]["requirements"] == {
        "canvas": False,
        "network": False,
        "credentials": False,
        "profile_supported": False,
        "project_option": True,
    }
    assert children["quiz analysis"]["artifact"] == {
        "retained": True,
        "artifact_class": "private",
        "default_relative": None,
    }
    exported = children["quiz export-analysis"]
    assert exported["requirements"] == {
        "canvas": True,
        "network": True,
        "credentials": True,
        "profile_supported": True,
        "project_option": True,
    }
    assert exported["access"]["canvas_mutation"] is True
    assert exported["access"]["bare_canvas_mutation"] is False
    assert exported["access"]["authoritative_verification"] is True
    assert exported["artifact"] == {
        "retained": True,
        "artifact_class": "private",
        "default_relative": None,
    }


def test_generated_interfaces_require_plan_and_reject_bypass_examples() -> None:
    guide = COMMAND_GUIDES["quiz export-analysis"]
    assert [example.stage for example in guide.examples[:2]] == [
        ExampleStage.PLAN,
        ExampleStage.APPLY,
    ]
    assert "--apply" not in guide.examples[0].argv
    assert "--apply" in guide.examples[1].argv

    leaf_help = runner.invoke(app, ["quiz", "export-analysis", "--help"], color=False)
    assert leaf_help.exit_code == 0
    public_text = "\n".join(
        [
            click.unstyle(leaf_help.output),
            render_guide("content"),
            render_guide("safety"),
            *(
                resource.content.decode("utf-8")
                for resource in canonical_skill_files()
            ),
        ]
    )
    lowered = public_text.lower()
    assert "missing danvas" in lowered
    assert "direct canvas api" in lowered
    assert "does not authorize" in lowered
    assert "canvas mutation" in lowered
    for raw_interface in ("/api/v1/", "progress_url", '"quiz_report"'):
        assert raw_interface not in public_text


def test_identified_student_analysis_shape_is_characterized() -> None:
    report = StudentAnalysisReport(FIXTURES / "identified-student-analysis.csv")

    assert {"id", "submitted"} <= set(report.headers)
    assert len(report.data_rows) == 2
    assert [pair.question_id for pair in report.question_pairs] == ["123", "124"]
    assert analyze_student_analysis(report.path)["rows"] == {
        "students": 2,
        "submitted": 2,
        "missing_submissions": 0,
    }


def test_parser_accepts_bom_zero_row_zero_question_and_partial_rows(tmp_path: Path) -> None:
    bom = tmp_path / "bom.csv"
    bom.write_bytes((FIXTURES / "identified-student-analysis.csv").read_bytes())
    bom.write_bytes(b"\xef\xbb\xbf" + bom.read_bytes())
    assert StudentAnalysisReport(bom).headers[0] == "name"

    zero_rows = StudentAnalysisReport(FIXTURES / "zero-row-student-analysis.csv")
    assert list(zero_rows.iter_rows()) == []
    assert zero_rows.question_pairs == []

    zero_questions = StudentAnalysisReport(FIXTURES / "zero-question-student-analysis.csv")
    assert len(list(zero_questions.iter_rows())) == 1
    assert zero_questions.question_pairs == []

    partial = tmp_path / "partial.csv"
    partial.write_text("id,submitted,123: Q,1,score\n10,2026-01-01,A\n", encoding="utf-8")
    row = next(iter(StudentAnalysisReport(partial).iter_rows()))
    assert row == ["10", "2026-01-01", "A", "", ""]


def test_local_parser_remains_permissive_for_anonymous_and_malformed_shapes() -> None:
    anonymous = StudentAnalysisReport(FIXTURES / "anonymous-student-analysis.csv")
    malformed = StudentAnalysisReport(FIXTURES / "malformed-student-analysis.csv")

    assert "id" not in anonymous.header_index
    assert anonymous.answer_for(next(iter(anonymous.iter_rows())), ["which version"]) == "Python"
    assert "id" not in malformed.header_index
    assert "submitted" not in malformed.header_index


def test_primary_source_shaped_report_fixture_covers_reviewed_states() -> None:
    payload = json.loads(
        (FIXTURES / "canvas-report-responses.json").read_text(encoding="utf-8")
    )

    assert set(payload) == {
        "identified_quiz",
        "identified_survey",
        "anonymous_survey",
        "completed_report",
        "running_report",
        "queued_progress",
        "running_progress",
        "completed_progress",
        "failed_progress",
        "malformed_report",
    }
    assert payload["completed_report"]["report_type"] == "student_analysis"
    assert payload["completed_report"]["file"]["id"] == 404
    assert payload["running_report"]["progress_url"].endswith("token=PROTECTED")
    assert payload["anonymous_survey"]["anonymous_submissions"] is True
    assert {
        payload[name]["workflow_state"]
        for name in (
            "queued_progress",
            "running_progress",
            "completed_progress",
            "failed_progress",
        )
    } == {"queued", "running", "completed", "failed"}


def test_quiz_export_evidence_schema_v1_is_pinned() -> None:
    contract = json.loads(
        (FIXTURES / "evidence-contract-v1.json").read_text(encoding="utf-8")
    )

    assert contract == {
        "schema_version": "quiz-analysis-export-v1",
        "request_status": [
            "not_attempted",
            "accepted",
            "reused",
            "unknown_after_exception",
            "conflict",
        ],
        "progress_status": [
            "not_checked",
            "queued",
            "running",
            "completed",
            "failed",
            "timed_out",
            "unavailable",
        ],
        "download_status": [
            "not_attempted",
            "downloaded_verified",
            "failed",
            "accepted_unverified",
        ],
        "overall_status": [
            "planned",
            "applied_verified",
            "accepted_unverified",
            "conflict",
            "failed",
        ],
        "required_identity_fields": [
            "course_id",
            "quiz_id",
            "report_type",
            "includes_all_versions",
        ],
    }


def test_group_1_adds_raw_report_boundary_without_canvasapi_convenience_call() -> None:
    package = ROOT / "src" / "danvas"
    source_parts = [path.read_text(encoding="utf-8") for path in sorted(package.glob("*.py"))]
    calls = {
        node.func.attr
        for source in source_parts
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    source = "\n".join(source_parts)

    assert "create_report" not in calls
    assert "quiz-analysis-export-v1" in source
    assert "quiz export-analysis" in source
