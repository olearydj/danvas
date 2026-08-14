from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-docs.py"


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
    assert "12 Markdown files" in result.stdout


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
