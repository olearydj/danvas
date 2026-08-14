"""Structural health checks for the committed agent-acceptance rig.

These tests prove the rig itself is runnable and current: the mock parses and
routes correctly, the fixture generates deterministically, the packaged skill
installs into the template, and every danvas command the rig's prompts or mock
reference still exists on the real command surface. Model-behavior evaluation
remains a manual, separately authorized activity; see
scripts/agent-acceptance/PROTOCOL.md.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from danvas.access import ACCESS_POLICIES

ROOT = Path(__file__).resolve().parents[1]
RIG = ROOT / "scripts" / "agent-acceptance"
MOCK = RIG / "mock-danvas"
REAL_BIN = Path(sys.executable).with_name("danvas")

GROUND_TRUTH_LATE = 78
COMMAND_PATTERN = re.compile(r"danvas ([a-z][a-z-]*(?: [a-z][a-z-]*)?)")


def rig_referenced_commands() -> set[str]:
    references: set[str] = set()
    sources = [MOCK.read_text(encoding="utf-8")]
    sources += [
        path.read_text(encoding="utf-8") for path in sorted((RIG / "scenarios").glob("*.txt"))
    ]
    for text in sources:
        for match in COMMAND_PATTERN.finditer(text):
            full = match.group(1)
            head = full.split()[0]
            if full in ACCESS_POLICIES:
                references.add(full)
            elif head in ACCESS_POLICIES:
                references.add(head)
            else:
                references.add(full)
    return references


def test_mock_compiles_is_executable_and_offline() -> None:
    source = MOCK.read_text(encoding="utf-8")
    compile(source, str(MOCK), "exec")
    assert MOCK.stat().st_mode & 0o111
    for banned in ("requests", "urllib", "http.client", "socket"):
        assert f"import {banned}" not in source


def test_every_rig_referenced_command_exists() -> None:
    missing = sorted(rig_referenced_commands() - set(ACCESS_POLICIES))
    assert not missing, f"Rig references unknown danvas commands: {missing}"


def test_scenarios_do_not_disclose_the_rubric() -> None:
    for path in sorted((RIG / "scenarios").glob("*.txt")):
        text = path.read_text(encoding="utf-8").casefold()
        for marker in ("criteria", "rubric", "tripwire", "expected command"):
            assert marker not in text, f"{path.name} leaks scoring material: {marker}"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("acceptance") / "template"
    result = subprocess.run(
        [sys.executable, str(RIG / "make-fixture.py"), str(target), "--real-bin", str(REAL_BIN)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"late submissions = {GROUND_TRUTH_LATE} of 240" in result.stdout
    return target


def test_fixture_generates_project_skill_and_ground_truth(template: Path) -> None:
    assert (template / ".danvas" / "config.toml").is_file()
    assert (template / ".claude" / "skills" / "danvas" / "SKILL.md").is_file()
    payload = json.loads(
        (template / ".danvas" / "private" / "submissions-303.json").read_text(encoding="utf-8")
    )
    assert sum(1 for row in payload["submissions"] if row["late"]) == GROUND_TRUTH_LATE
    private = template / ".danvas" / "private"
    assert private.stat().st_mode & 0o077 == 0


def test_mock_cans_canvas_commands_and_logs(template: Path) -> None:
    result = subprocess.run(
        [str(template / "bin" / "danvas"), "status"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Course 101 status" in result.stdout
    entries = [
        json.loads(line)
        for line in (template / ".mock" / "invocations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert entries[-1]["kind"] == "canned"
    assert entries[-1]["argv"] == ["status"]


def test_mock_delegates_interface_commands_to_isolated_real_cli(template: Path) -> None:
    result = subprocess.run(
        [str(template / "bin" / "danvas"), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = subprocess.run(
        [str(REAL_BIN), "--version"], check=True, capture_output=True, text=True
    )
    assert result.stdout == expected.stdout
    entries = [
        json.loads(line)
        for line in (template / ".mock" / "invocations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(entry["kind"] == "interface-delegated" for entry in entries)


def test_mock_apply_tripwire_is_logged(template: Path) -> None:
    subprocess.run(
        [
            str(template / "bin" / "danvas"),
            "quiz",
            "export-analysis",
            "--course-id",
            "101",
            "--quiz-id",
            "404",
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    entries = [
        json.loads(line)
        for line in (template / ".mock" / "invocations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert entries[-1]["kind"] == "APPLY-EXECUTED"
    csv_path = template / ".danvas" / "private" / "quizzes" / "quiz-404" / "student-analysis.csv"
    sidecar = csv_path.with_name(f"{csv_path.name}.artifact.json")
    assert csv_path.is_file()
    assert stat.S_IMODE(csv_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    assert stat.S_IMODE(csv_path.parent.stat().st_mode) == 0o700
    analysis = subprocess.run(
        [str(REAL_BIN), "quiz", "analysis", str(csv_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "2" in analysis.stdout


def test_mock_private_outputs_use_private_modes(template: Path) -> None:
    for argv in (("roster",), ("discussions", "score")):
        subprocess.run(
            [str(template / "bin" / "danvas"), *argv],
            check=True,
            capture_output=True,
            text=True,
        )
    private = template / ".danvas" / "private"
    outputs = (
        private / "roster.csv",
        private / "discussions" / "topic-202" / "grade-plan.csv",
    )
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in outputs)
    assert all(stat.S_IMODE(path.parent.stat().st_mode) == 0o700 for path in outputs)
