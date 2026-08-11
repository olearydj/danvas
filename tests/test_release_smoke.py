from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release-smoke.sh"


def test_release_smoke_script_is_executable_and_valid_shell() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR

    result = subprocess.run(
        ["sh", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_release_smoke_help_works_outside_repository(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--expected-version X.Y.Z" in result.stdout


def test_release_smoke_rejects_version_mismatch_before_uv(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"

    result = subprocess.run(
        [str(SCRIPT), "--expected-version", "999.999.999"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "does not match package version" in result.stderr
    assert "uv is required" not in result.stderr


def test_release_smoke_requires_expected_version_value(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--expected-version"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "requires a non-empty value" in result.stderr


def test_release_smoke_rejects_empty_expected_version(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--expected-version", ""],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "requires a non-empty value" in result.stderr


def test_release_smoke_cleans_temporary_root_after_build_failure(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["TMPDIR"] = str(temp_root)

    result = subprocess.run(
        [str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 7
    assert list(temp_root.glob("danvas-release-smoke.*")) == []
