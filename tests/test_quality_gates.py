from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_COVERAGE_SCRIPT = ROOT / "scripts" / "check-module-coverage.py"


def run_module_coverage_check(
    tmp_path: Path,
    report: dict[str, object],
    *,
    module: str = "src/danvas/example.py",
    minimum: str = "82",
) -> subprocess.CompletedProcess[str]:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(MODULE_COVERAGE_SCRIPT), str(report_path), module, minimum],
        check=False,
        capture_output=True,
        text=True,
    )


def test_module_coverage_gate_accepts_floor_exactly(tmp_path: Path) -> None:
    result = run_module_coverage_check(
        tmp_path,
        {
            "files": {
                "src/danvas/example.py": {"summary": {"percent_covered": 82.0}}
            }
        },
    )

    assert result.returncode == 0
    assert "82.00% branch-aware coverage" in result.stdout


def test_module_coverage_gate_rejects_below_floor(tmp_path: Path) -> None:
    result = run_module_coverage_check(
        tmp_path,
        {
            "files": {
                "src/danvas/example.py": {"summary": {"percent_covered": 81.99}}
            }
        },
    )

    assert result.returncode == 1
    assert "minimum 82.00%" in result.stdout


def test_module_coverage_gate_rejects_missing_module(tmp_path: Path) -> None:
    result = run_module_coverage_check(tmp_path, {"files": {}})

    assert result.returncode == 1
    assert "does not contain module" in result.stderr
