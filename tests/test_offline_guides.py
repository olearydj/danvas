from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import danvas.cli as cli_module
from danvas.access import ACCESS_POLICIES
from danvas.artifacts import ARTIFACT_POLICIES, ArtifactClass
from danvas.cli import app
from danvas.command_guides import COMMAND_GUIDES
from danvas.offline_guides import GUIDE_TOPICS, guide_list_text, render_guide

runner = CliRunner()
EXPECTED_TOPICS = (
    "setup",
    "status",
    "safety",
    "local-sync",
    "privacy",
    "assignments",
    "grades",
    "files",
    "content",
    "integrations",
    "agents",
)


def test_guide_topic_inventory_and_list_are_deterministic() -> None:
    assert tuple(topic.name for topic in GUIDE_TOPICS) == EXPECTED_TOPICS
    assert guide_list_text() == render_guide("list")
    assert guide_list_text() == render_guide("list")
    assert all(topic.resource.endswith(".txt") for topic in GUIDE_TOPICS)
    assert all(path in COMMAND_GUIDES for topic in GUIDE_TOPICS for path in topic.command_paths)


@pytest.mark.parametrize("topic", EXPECTED_TOPICS)
def test_every_guide_renders_offline_with_bounded_content(
    topic: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("offline guide crossed a project, credential, dispatch, or network boundary")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli_module, "run_command", forbidden)
    monkeypatch.setattr(cli_module, "resolve_canvas_context", forbidden)
    monkeypatch.setattr("danvas.auth.resolve_canvas_credential", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)

    result = runner.invoke(app, ["guide", topic])

    assert result.exit_code == 0, result.output
    assert result.output == render_guide(topic)
    assert 25 <= len(result.output.split()) <= 900
    lowered = result.output.lower()
    for forbidden_text in (
        "--live",
        "--upload",
        "--secret-name",
        "--secret-provider",
        "--op-reference",
        "auburn." + "instructure.com",
        "/casa/",
        "/volumes/casa/",
    ):
        assert forbidden_text not in lowered


def test_unknown_guide_topic_has_suggestion_and_list_command() -> None:
    result = runner.invoke(app, ["guide", "assigments"])

    assert result.exit_code == 2
    assert "assignments" in result.output
    assert "danvas guide list" in result.output


def test_discovery_commands_are_shareable_and_local_only() -> None:
    for command in ("guide", "describe", "skill show"):
        assert ACCESS_POLICIES[command].canvas_read is False
        assert ACCESS_POLICIES[command].local_write is False
        assert ARTIFACT_POLICIES[command].artifact_class is ArtifactClass.SHAREABLE
        assert ARTIFACT_POLICIES[command].retained is False
