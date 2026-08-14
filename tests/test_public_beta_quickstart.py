from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-public-beta-quickstart.py"


def test_public_beta_quickstart_renders_standard_and_preserves_legacy(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace", str(workspace)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "public beta quickstart fixtures passed\n"

    new_project = workspace / "new-project"
    new_config = tomllib.loads(
        (new_project / ".danvas/config.toml").read_text(encoding="utf-8")
    )
    assert new_config["sources"]["layout"] == "standard-v1"
    assert new_config["sources"]["assignments"]["include"] == [
        "content/assignments/*.md"
    ]
    assert not (new_project / "content").exists()

    existing_config = tomllib.loads(
        (workspace / "existing-project/.danvas/config.toml").read_text(encoding="utf-8")
    )
    assert "sources" not in existing_config


def test_public_beta_quickstart_refuses_nonempty_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace", str(workspace)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "workspace must be empty" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "preserve"
