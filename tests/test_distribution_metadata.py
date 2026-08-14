from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "check-distributions.py"


@pytest.fixture(scope="module")
def built_distributions(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    output = tmp_path_factory.mktemp("distributions")
    result = subprocess.run(
        [
            "uv",
            "--cache-dir",
            str(output / "cache"),
            "build",
            "--offline",
            "--no-build-isolation",
            "--out-dir",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    wheels = list(output.glob("danvas_cli-0.19.0-*.whl"))
    sdists = list(output.glob("danvas_cli-0.19.0.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1
    return wheels[0], sdists[0]


def test_built_distributions_match_public_contract(
    built_distributions: tuple[Path, Path],
) -> None:
    wheel, sdist = built_distributions
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            str(wheel),
            str(sdist),
            "--expected-version",
            "0.19.0",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "danvas-cli 0.19.0" in result.stdout


def test_distribution_checker_rejects_wrong_expected_version(
    built_distributions: tuple[Path, Path],
) -> None:
    wheel, sdist = built_distributions
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            str(wheel),
            str(sdist),
            "--expected-version",
            "9.9.9",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "METADATA Version" in result.stderr
