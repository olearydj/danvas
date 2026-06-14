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


def test_assignments_audit_cli(tmp_path: Path) -> None:
    assignments = tmp_path / "assignments.json"
    write_assignment_fixture(assignments)
    policy = tmp_path / "course.yaml"
    policy.write_text("weights:\n  Homework: 40\n  Tests: 60\n", encoding="utf-8")

    result = runner.invoke(
        app, ["assignments", "audit", str(assignments), "--course-yaml", str(policy)]
    )

    assert result.exit_code == 0
    assert "Assignments: 2" in result.output


def test_quiz_analysis_cli(tmp_path: Path) -> None:
    quiz = tmp_path / "student-analysis.csv"
    write_quiz_fixture(quiz)

    result = runner.invoke(
        app,
        ["quiz", "analysis", str(quiz), "--answer-term", "which version", "--answer-term", "comp"],
    )

    assert result.exit_code == 0
    assert "Students: 2" in result.output


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

    assert {"--match-title", "--dry-run", "--no-publish", "--course-id"} <= options


def test_status_is_read_only() -> None:
    assert "Read-only" in (command("status").help or "")
    assert "--report-md" in option_names("status")


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
    assert {"--folder", "--folder-id", "--on-duplicate", "--dry-run", "--course-id"} <= (
        option_names("files", "upload")
    )
