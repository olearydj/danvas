#!/usr/bin/env python3
"""Enforce a combined branch-aware coverage floor for one source module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def module_percent(report: dict[str, Any], module: str) -> float:
    files = report.get("files")
    if not isinstance(files, dict) or module not in files:
        raise SystemExit(f"Coverage report does not contain module: {module}")
    summary = files[module].get("summary")
    if not isinstance(summary, dict) or summary.get("percent_covered") is None:
        raise SystemExit(f"Coverage report has no percentage for module: {module}")
    return float(summary["percent_covered"])


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: check-module-coverage.py REPORT.json MODULE.py MINIMUM_PERCENT"
        )
    report_path = Path(sys.argv[1])
    module = sys.argv[2]
    minimum = float(sys.argv[3])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    actual = module_percent(report, module)
    print(f"{module}: {actual:.2f}% branch-aware coverage (minimum {minimum:.2f}%)")
    if actual < minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
