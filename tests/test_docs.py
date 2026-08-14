from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-docs.py"
CURRENT_AUTHORITY_DOCS = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/authentication.md",
    "docs/authored-sources.md",
    "docs/quizzes.md",
    "docs/compatibility.md",
    "docs/configuration.md",
    "docs/course-yaml.md",
    "docs/mutation-safety.md",
    "docs/privacy.md",
)


def run_checker(root: Path, *files: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--files", *files],
        check=False,
        capture_output=True,
        text=True,
    )


def test_public_documentation_suite_passes_offline_link_check() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "16 Markdown files" in result.stdout


def test_documentation_checker_accepts_local_links_anchors_and_external_urls(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "README.md").write_text(
        "# Start Here\n\n[Guide](docs/guide.md#safe-retry)\n"
        "[External](https://example.edu/docs)\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        "# Guide\n\n## Safe Retry\n\n[Home](../README.md#start-here)\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path, "README.md", "docs/guide.md")

    assert result.returncode == 0, result.stderr
    assert "2 Markdown files" in result.stdout


def test_documentation_checker_rejects_missing_target_and_anchor(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Home\n\n[Missing](docs/missing.md)\n[Anchor](README.md#absent)\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path, "README.md")

    assert result.returncode == 1
    assert "missing local link target" in result.stderr
    assert "missing Markdown anchor" in result.stderr


def test_documentation_checker_ignores_links_inside_fenced_examples(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Home\n\n```markdown\n[Illustration](not-a-real-file.md)\n```\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path, "README.md")

    assert result.returncode == 0, result.stderr


def test_current_guides_use_only_provider_neutral_credential_surface() -> None:
    retired_spellings = (
        "secret_provider",
        "op_reference",
        "--secret-name",
        "--secret-provider",
        "--op-reference",
        "CANVAS_SECRET_PROVIDER",
        "CANVAS_API_KEY_OP_REFERENCE",
    )

    for relative_path in CURRENT_AUTHORITY_DOCS:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for spelling in retired_spellings:
            assert spelling not in text, f"{relative_path} retains {spelling}"


def test_current_guides_expose_only_login_id_roster_schema() -> None:
    for relative_path in CURRENT_AUTHORITY_DOCS:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "roster --schema" not in text, (
            f"{relative_path} retains the removed roster schema selector"
        )

    migration = (ROOT / "docs/migrations/0.19.0.md").read_text(encoding="utf-8")
    assert "CanvasID,Name,LoginID,SIS_ID" in migration
    assert "roster --schema legacy-v1" in migration


def test_classic_quiz_docs_teach_plan_apply_private_analysis_boundary() -> None:
    workflow = (ROOT / "docs/quizzes.md").read_text(encoding="utf-8")
    migration = (ROOT / "docs/migrations/0.21.0.md").read_text(encoding="utf-8")
    combined = f"{workflow}\n{migration}"

    for command in (
        "danvas quiz export-analysis --course-id 101 --quiz-id 202",
        "danvas quiz export-analysis --course-id 101 --quiz-id 202 --apply",
        "danvas quiz analysis",
    ):
        assert command in combined
    assert "Canvas mutation" in combined
    assert ".danvas/private/quizzes/quiz-202/student-analysis.csv" in combined
    assert "Anonymous Surveys" in combined
    assert "New Quizzes" in combined
    assert "blindly" in combined
    assert "does not authorize a direct Canvas API" in combined


def test_security_policy_tracks_latest_signed_release_not_candidate() -> None:
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "latest signed `0.20.x`" in policy
    assert "`0.19.x` and earlier" in policy
    assert "latest signed `0.21.x`" not in policy


def test_sprint22_baseline_is_provider_neutral_020_surface() -> None:
    design = (ROOT / "docs/sprints/22-agent-interface.md").read_text(
        encoding="utf-8"
    )

    assert "The target release is 0.20.0" in design
    assert "released 0.19.0 command surface" in design
    assert "`--api-key-env`" in design
    assert "`--api-key-file`" in design
    assert "legacy-v1" not in design
