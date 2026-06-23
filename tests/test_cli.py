import json
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
import typer
from typer.testing import CliRunner

from danvas.cli import app, run_command
from tests.fixtures import write_assignment_fixture, write_gradebook_fixture, write_quiz_fixture

runner = CliRunner()


def command(*path: str) -> click.Command:
    """Resolve a (sub)command from the Typer app's Click tree."""
    cmd: click.Command = typer.main.get_command(app)
    for name in path:
        assert isinstance(cmd, click.Group)
        cmd = cmd.commands[name]
    return cmd


def option_names(*path: str) -> set[str]:
    cmd = command(*path)
    names: set[str] = set()
    for param in cmd.params:
        names.update(param.opts)
        names.update(param.secondary_opts)
    return names


def test_gradebook_check_cli(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    policy = tmp_path / "course.yaml"
    policy.write_text('exclude_students:\n  - "^Student, Test$"\n', encoding="utf-8")

    result = runner.invoke(
        app, ["gradebook", "check", str(gradebook), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Included rows: 2" in result.output
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_gradebook_audit_cli(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    policy = tmp_path / "course.yaml"
    policy.write_text(
        'exclude_students:\n  - "^Student, Test$"\nweights:\n  Homework: 50\n  Tests: 50\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["gradebook", "audit", str(gradebook), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Status: matches" in result.output
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_gradebook_check_cli_writes_report_run_in_project(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["gradebook", "check", str(gradebook), "--project-root", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    report_dir = report_dirs[0]
    assert report_dir.name.endswith("-gradebook-check")
    assert (report_dir / "gradebook-check.json").is_file()
    assert (report_dir / "gradebook-check.md").is_file()
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "gradebook check"
    assert manifest["may_contain_private_student_data"] is True


def test_gradebook_audit_cli_writes_legacy_and_report_outputs(tmp_path: Path) -> None:
    gradebook = tmp_path / "gradebook.csv"
    write_gradebook_fixture(gradebook)
    output = tmp_path / "audit.json"

    result = runner.invoke(
        app,
        [
            "gradebook",
            "audit",
            str(gradebook),
            "--output",
            str(output),
            "--report-dir",
            str(tmp_path / "audit-report"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert (tmp_path / "audit-report" / "gradebook-audit.json").is_file()
    assert (tmp_path / "audit-report" / "gradebook-audit.md").is_file()


def test_assignments_audit_cli(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    policy = tmp_path / "course.yaml"
    policy.write_text("weights:\n  Homework: 40\n  Tests: 60\n", encoding="utf-8")

    result = runner.invoke(
        app, ["assignments", "audit", str(assignments), "--course-yaml", str(policy), "--no-report"]
    )

    assert result.exit_code == 0
    assert "Assignments: 2" in result.output


def test_assignments_audit_cli_writes_default_report_run(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    config_dir = tmp_path / ".danvas"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["assignments", "audit", str(assignments), "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    assert report_dirs[0].name.endswith("-assignment-audit")
    assert (report_dirs[0] / "assignment-audit.json").is_file()
    assert (report_dirs[0] / "assignment-audit.md").is_file()
    manifest = json.loads((report_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["command"] == "assignments audit"


def test_quiz_analysis_cli(tmp_path: Path) -> None:
    quiz = tmp_path / "student-analysis.csv"
    write_quiz_fixture(quiz)

    result = runner.invoke(
        app,
        ["quiz", "analysis", str(quiz), "--answer-term", "which version", "--answer-term", "comp"],
    )

    assert result.exit_code == 0
    assert "Students: 2" in result.output
    assert not (tmp_path / ".danvas" / "reports").exists()


def test_quiz_analysis_cli_writes_report_run_in_project(tmp_path: Path) -> None:
    quiz = tmp_path / "student-analysis.csv"
    write_quiz_fixture(quiz)
    (tmp_path / ".danvas").mkdir()
    (tmp_path / ".danvas" / "config.toml").write_text(
        '[canvas]\ncourse_id = 101\ntimezone = "America/Chicago"\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "quiz",
            "analysis",
            str(quiz),
            "--answer-term",
            "which version",
            "--project-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    report_dirs = list((tmp_path / ".danvas" / "reports").iterdir())
    assert len(report_dirs) == 1
    report_dir = report_dirs[0]
    assert report_dir.name.endswith("-quiz-analysis")
    assert (report_dir / "quiz-analysis.json").is_file()
    assert (report_dir / "quiz-analysis.md").is_file()
    manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "quiz analysis"
    assert manifest["may_contain_private_student_data"] is True


def test_run_command_echoes_string_exits_only(capsys: pytest.CaptureFixture[str]) -> None:
    def fail_with_message(args: SimpleNamespace) -> None:
        raise SystemExit("something went wrong")

    def fail_with_code(args: SimpleNamespace) -> None:
        raise SystemExit(1)

    with pytest.raises(typer.Exit):
        run_command(fail_with_message, SimpleNamespace())
    assert "something went wrong" in capsys.readouterr().err

    with pytest.raises(typer.Exit):
        run_command(fail_with_code, SimpleNamespace())
    assert capsys.readouterr().err == ""


def test_version_flag() -> None:
    from danvas import __version__

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"danvas {__version__}"


def test_help_renders_without_error() -> None:
    for argv in (
        ["--help"],
        ["quiz", "import-qti", "--help"],
        ["status", "--help"],
        ["recordings", "panopto-captions", "--help"],
    ):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, argv


def test_quiz_import_qti_defines_expected_options() -> None:
    options = option_names("quiz", "import-qti")
    report_options = {"--project-root", "--no-report", "--report-root", "--report-dir", "--report-slug"}

    assert {"--match-title", "--dry-run", "--no-publish", "--course-id"} <= options
    assert report_options <= options


def test_local_report_commands_define_report_options() -> None:
    expected = {"--project-root", "--no-report", "--report-root", "--report-dir", "--report-slug"}

    assert expected <= option_names("gradebook", "check")
    assert expected <= option_names("gradebook", "audit")
    assert expected <= option_names("quiz", "analysis")
    assert expected <= option_names("files", "upload")
    assert expected.isdisjoint(option_names("discussions", "score"))


def test_status_is_read_only() -> None:
    assert "Read-only" in (command("status").help or "")
    assert {"--report-md", "--report-root", "--report-dir", "--report-slug"} <= option_names(
        "status"
    )


def test_recordings_panopto_captions_options() -> None:
    assert "Panopto" in (command("recordings", "panopto-captions").help or "")
    assert {"--folder-id", "--session-id"} <= option_names("recordings", "panopto-captions")


def test_files_upload_cli_options_and_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slides.pptx"
    source.write_text("slides", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_upload(args: SimpleNamespace) -> None:
        captured.update(vars(args))

    monkeypatch.setattr("danvas.cli.command_files_upload", fake_upload)

    result = runner.invoke(
        app,
        [
            "files",
            "upload",
            "--course-id",
            "101",
            "--folder",
            "course files/slides",
            "--on-duplicate",
            "rename",
            "--dry-run",
            "--output",
            "upload.json",
            str(source),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["course_id"] == 101
    assert captured["files"] == [str(source)]
    assert captured["folder"] == "course files/slides"
    assert captured["folder_id"] is None
    assert captured["on_duplicate"] == "rename"
    assert captured["dry_run"] is True
    assert captured["output"] == "upload.json"
    assert captured["project_root"] == "."
    assert captured["no_report"] is False
    assert captured["report_root"] is None
    assert captured["report_dir"] is None
    assert captured["report_slug"] is None
    assert {
        "--folder",
        "--folder-id",
        "--on-duplicate",
        "--dry-run",
        "--course-id",
        "--report-root",
        "--report-dir",
        "--report-slug",
        "--no-report",
    } <= option_names("files", "upload")
