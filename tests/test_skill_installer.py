from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import click
import pytest
from typer.testing import CliRunner

import danvas.cli as cli_module
from danvas import __version__
from danvas.cli import app
from danvas.skill_installer import (
    PROVENANCE_NAME,
    SKILL_FILE_LIMIT,
    AgentTarget,
    InstallState,
    SkillInstallRefused,
    SkillScope,
    inspect_skill_target,
    install_action,
    install_skill,
    render_doctor,
    resolve_skill_target,
    skill_doctor,
)
from danvas.skill_resources import SkillResourceFile, canonical_skill_files

runner = CliRunner()


USER_ROOTS = {
    AgentTarget.SHARED: ".agents/skills/danvas",
    AgentTarget.CODEX: ".agents/skills/danvas",
    AgentTarget.CLAUDE_CODE: ".claude/skills/danvas",
    AgentTarget.GEMINI: ".gemini/skills/danvas",
    AgentTarget.COPILOT: ".copilot/skills/danvas",
}
PROJECT_ROOTS = {
    AgentTarget.SHARED: ".agents/skills/danvas",
    AgentTarget.CODEX: ".agents/skills/danvas",
    AgentTarget.CLAUDE_CODE: ".claude/skills/danvas",
    AgentTarget.GEMINI: ".gemini/skills/danvas",
    AgentTarget.COPILOT: ".github/skills/danvas",
}


def target(tmp_path: Path, agent: AgentTarget = AgentTarget.SHARED):
    return resolve_skill_target(agent=agent, scope=SkillScope.USER, home=tmp_path)


def old_resources() -> tuple[SkillResourceFile, ...]:
    resources = list(canonical_skill_files())
    resources[0] = SkillResourceFile(
        PurePosixPath(resources[0].relative_path),
        resources[0].content + b"\n<!-- older bundled copy -->\n",
    )
    return tuple(resources)


@pytest.mark.parametrize("agent", tuple(AgentTarget))
def test_allowlisted_user_and_project_targets_are_exact(tmp_path: Path, agent: AgentTarget) -> None:
    user = resolve_skill_target(agent=agent, scope=SkillScope.USER, home=tmp_path)
    project = resolve_skill_target(
        agent=agent,
        scope=SkillScope.PROJECT,
        project_root=tmp_path,
    )

    assert user.path == tmp_path / USER_ROOTS[agent]
    assert project.path == tmp_path / PROJECT_ROOTS[agent]
    assert user.path.is_relative_to(tmp_path)
    assert project.path.is_relative_to(tmp_path)


def test_project_scope_requires_explicit_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires --project-root"):
        resolve_skill_target(agent=AgentTarget.SHARED, scope=SkillScope.PROJECT)


def test_dry_run_reports_absent_target_without_writing(tmp_path: Path) -> None:
    selected = target(tmp_path)
    before = set(tmp_path.rglob("*"))

    result = install_skill(selected, dry_run=True)

    assert result.inspection.state is InstallState.ABSENT
    assert result.action == "would create"
    assert not result.changed
    assert set(tmp_path.rglob("*")) == before


def test_absent_install_is_atomic_exact_and_idempotent(tmp_path: Path) -> None:
    selected = target(tmp_path)

    created = install_skill(selected)
    first_inventory = {
        path.relative_to(selected.path): path.read_bytes()
        for path in selected.path.rglob("*")
        if path.is_file()
    }
    repeated = install_skill(selected)
    second_inventory = {
        path.relative_to(selected.path): path.read_bytes()
        for path in selected.path.rglob("*")
        if path.is_file()
    }

    assert created.action == "created"
    assert created.changed
    assert created.inspection.state is InstallState.EXACT
    assert repeated.action == "already installed"
    assert not repeated.changed
    assert first_inventory == second_inventory
    assert not list(selected.skills_root.glob(".danvas-skill-staging-*"))


def test_owned_stale_unmodified_target_updates_atomically(tmp_path: Path) -> None:
    selected = target(tmp_path)
    old = old_resources()
    install_skill(selected, resources=old)

    stale = inspect_skill_target(selected)
    result = install_skill(selected)

    assert stale.state is InstallState.OWNED_STALE
    assert stale.differences
    assert result.action == "updated"
    assert result.changed
    assert inspect_skill_target(selected).state is InstallState.EXACT


def test_owned_modified_target_is_refused_without_change(tmp_path: Path) -> None:
    selected = target(tmp_path)
    install_skill(selected)
    changed = selected.path / "SKILL.md"
    changed.write_text("locally modified\n", encoding="utf-8")
    before = changed.read_bytes()

    inspection = inspect_skill_target(selected)
    with pytest.raises(SkillInstallRefused) as caught:
        install_skill(selected)

    assert inspection.state is InstallState.OWNED_MODIFIED
    assert caught.value.inspection.state is InstallState.OWNED_MODIFIED
    assert changed.read_bytes() == before


@pytest.mark.parametrize("kind", ("directory", "file"))
def test_unowned_target_is_refused_without_change(tmp_path: Path, kind: str) -> None:
    selected = target(tmp_path)
    selected.path.parent.mkdir(parents=True)
    if kind == "directory":
        selected.path.mkdir()
        marker = selected.path / "keep.txt"
        marker.write_text("user owned\n", encoding="utf-8")
    else:
        selected.path.write_text("user owned\n", encoding="utf-8")
        marker = selected.path
    before = marker.read_bytes()

    with pytest.raises(SkillInstallRefused) as caught:
        install_skill(selected)

    expected = InstallState.UNOWNED if kind == "directory" else InstallState.UNSAFE
    assert caught.value.inspection.state is expected
    assert marker.read_bytes() == before


def test_unsafe_symlink_parent_and_target_are_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    parent_target = target(tmp_path / "parent-case")
    parent_target.base.mkdir()
    (parent_target.base / ".agents").symlink_to(outside, target_is_directory=True)
    direct_target = target(tmp_path / "target-case")
    direct_target.skills_root.mkdir(parents=True)
    direct_target.path.symlink_to(outside, target_is_directory=True)

    assert inspect_skill_target(parent_target).state is InstallState.UNSAFE
    assert inspect_skill_target(direct_target).state is InstallState.UNSAFE
    with pytest.raises(SkillInstallRefused):
        install_skill(parent_target)
    with pytest.raises(SkillInstallRefused):
        install_skill(direct_target)


def test_symlinked_provenance_and_oversize_content_are_unsafe(tmp_path: Path) -> None:
    provenance_target = target(tmp_path / "provenance-case")
    provenance_target.base.mkdir()
    install_skill(provenance_target)
    provenance = provenance_target.path / PROVENANCE_NAME
    saved = provenance_target.base / "saved-provenance.json"
    provenance.rename(saved)
    provenance.symlink_to(saved)

    large_target = target(tmp_path / "large-case")
    large_target.base.mkdir()
    install_skill(large_target)
    (large_target.path / "unexpected.bin").write_bytes(b"x" * (SKILL_FILE_LIMIT + 1))

    assert inspect_skill_target(provenance_target).state is InstallState.UNSAFE
    assert inspect_skill_target(large_target).state is InstallState.UNSAFE


@pytest.mark.parametrize(
    "stage",
    (
        "after_staging_created",
        *(f"after_file:{resource.relative_path}" for resource in canonical_skill_files()),
        f"after_file:{PROVENANCE_NAME}",
        "before_commit",
    ),
)
def test_failure_before_absent_commit_leaves_no_partial_target(tmp_path: Path, stage: str) -> None:
    selected = target(tmp_path)

    def fail(name: str) -> None:
        if name == stage:
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        install_skill(selected, fault_hook=fail)

    assert inspect_skill_target(selected).state is InstallState.ABSENT
    assert not list(selected.skills_root.glob(".danvas-skill-staging-*"))


def test_failure_after_absent_commit_leaves_complete_new_target(tmp_path: Path) -> None:
    selected = target(tmp_path)

    def fail(name: str) -> None:
        if name == "after_commit":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        install_skill(selected, fault_hook=fail)

    assert inspect_skill_target(selected).state is InstallState.EXACT
    assert not list(selected.skills_root.glob(".danvas-skill-staging-*"))


@pytest.mark.parametrize("stage", ("before_commit", "after_commit"))
def test_interrupted_stale_update_preserves_one_complete_version(
    tmp_path: Path, stage: str
) -> None:
    selected = target(tmp_path)
    install_skill(selected, resources=old_resources())

    def fail(name: str) -> None:
        if name == stage:
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        install_skill(selected, fault_hook=fail)

    state = inspect_skill_target(selected).state
    expected = InstallState.OWNED_STALE if stage == "before_commit" else InstallState.EXACT
    assert state is expected
    assert not list(selected.skills_root.glob(".danvas-skill-staging-*"))


def test_race_created_target_is_never_replaced(tmp_path: Path) -> None:
    selected = target(tmp_path)
    marker = selected.path / "keep.txt"

    def race(name: str) -> None:
        if name == "before_commit":
            selected.path.mkdir()
            marker.write_text("race winner\n", encoding="utf-8")

    with pytest.raises(SkillInstallRefused, match="appeared during installation"):
        install_skill(selected, fault_hook=race)

    assert marker.read_text(encoding="utf-8") == "race winner\n"
    assert inspect_skill_target(selected).state is InstallState.UNOWNED


def test_update_race_restores_unowned_target_instead_of_deleting_it(tmp_path: Path) -> None:
    selected = target(tmp_path)
    install_skill(selected, resources=old_resources())
    moved_old = selected.skills_root / "old-owned"
    marker = selected.path / "keep.txt"

    def race(name: str) -> None:
        if name == "before_update_exchange":
            selected.path.rename(moved_old)
            selected.path.mkdir()
            marker.write_text("race winner\n", encoding="utf-8")

    with pytest.raises(SkillInstallRefused, match="conflicting target was restored"):
        install_skill(selected, fault_hook=race)

    assert marker.read_text(encoding="utf-8") == "race winner\n"
    assert inspect_skill_target(selected).state is InstallState.UNOWNED
    assert moved_old.is_dir()


def test_provenance_is_bounded_and_contains_no_local_identity(tmp_path: Path) -> None:
    selected = target(tmp_path)
    install_skill(selected)
    raw = (selected.path / PROVENANCE_NAME).read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["schema"] == "danvas-skill-install-v1"
    assert payload["distribution"] == "danvas-cli"
    assert payload["danvas_version"] == __version__
    assert payload["files"]
    assert str(tmp_path) not in raw
    assert tmp_path.name not in raw
    assert "token" not in raw.lower()
    assert "secret" not in raw.lower()


def test_doctor_scans_every_location_by_default_and_agent_narrows(tmp_path: Path) -> None:
    all_report = skill_doctor(
        home=tmp_path,
        project_root=tmp_path,
        which=lambda _name: "/tools/danvas",
        version_reader=lambda _path: __version__,
    )
    one_report = skill_doctor(
        agent=AgentTarget.COPILOT,
        home=tmp_path,
        project_root=tmp_path,
        which=lambda _name: None,
    )

    assert len(all_report.inspections) == 10
    assert all_report.executable_matches
    assert len(one_report.inspections) == 2
    assert not one_report.executable_matches
    rendered = render_doctor(one_report)
    assert "Executable: missing" in rendered
    assert "danvas skill install --agent copilot --scope user" in rendered
    assert "danvas skill install --agent copilot --scope project" in rendered


def test_doctor_repair_refuses_modified_and_unowned_targets(tmp_path: Path) -> None:
    selected = target(tmp_path)
    install_skill(selected)
    (selected.path / "SKILL.md").write_text("modified\n", encoding="utf-8")
    modified = inspect_skill_target(selected)

    assert modified.state is InstallState.OWNED_MODIFIED
    assert install_action(modified).startswith("inspect or move")


def test_cli_install_is_confined_and_doctor_is_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("skill commands crossed the Canvas boundary")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli_module, "resolve_canvas_context", forbidden)
    dry = runner.invoke(app, ["skill", "install", "--agent", "shared", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "State: absent" in dry.output
    assert not (home / ".agents").exists()

    install = runner.invoke(app, ["skill", "install", "--agent", "shared"])
    doctor = runner.invoke(
        app,
        ["skill", "doctor", "--agent", "shared", "--project-root", str(tmp_path)],
    )

    assert install.exit_code == 0, install.output
    assert "Action: created" in install.output
    assert (home / ".agents/skills/danvas/SKILL.md").is_file()
    assert doctor.exit_code == 0, doctor.output
    assert "shared user" in doctor.output
    assert "shared project" in doctor.output


def test_cli_requires_agent_and_explicit_project_root() -> None:
    missing_agent = runner.invoke(app, ["skill", "install"])
    missing_root = runner.invoke(
        app,
        ["skill", "install", "--agent", "gemini", "--scope", "project"],
    )
    irrelevant_root = runner.invoke(
        app,
        ["skill", "install", "--agent", "gemini", "--project-root", "."],
    )

    assert missing_agent.exit_code == 2
    assert "Missing option '--agent'" in click.unstyle(missing_agent.output)
    assert missing_root.exit_code == 2
    assert "requires --project-root" in click.unstyle(missing_root.output)
    assert irrelevant_root.exit_code == 2
    assert "only with --scope project" in click.unstyle(irrelevant_root.output)


def test_installer_surface_has_no_force_update_or_apply_escape_hatch() -> None:
    result = runner.invoke(app, ["skill", "install", "--help"])
    output = click.unstyle(result.output)

    assert result.exit_code == 0
    assert "--agent" in output
    assert "--scope" in output
    assert "--project-root" in output
    assert "--dry-run" in output
    assert "Runs locally" in output
    assert "never accesses or mutates Canvas" in output
    assert "Reads Canvas" not in output
    assert "--force" not in output
    assert "--update" not in output
    assert "--apply" not in output
