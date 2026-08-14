from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def test_pypi_publish_workflow_is_manual_and_least_privilege() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "release:" not in workflow
    assert "pull_request" not in workflow
    assert "permissions: {}" in workflow
    assert "contents: read" in workflow
    assert "id-token: write" in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "${{ secrets." not in workflow
    assert "persist-credentials: false" in workflow


def test_pypi_publish_workflow_reuses_verified_release_assets() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'gh release download "$RELEASE_TAG"' in workflow
    assert "sha256sum -c SHA256SUMS" in workflow
    assert "scripts/check-distributions.py" in workflow
    assert "git describe --tags --exact-match" in workflow
    assert "pypi-distributions" in workflow
    assert "https://pypi.org/p/danvas-cli" in workflow


def test_pypi_publish_actions_are_reviewed_full_sha_pins() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    uses = Counter(re.findall(r"^\s*- uses:\s+(\S+)", workflow, flags=re.MULTILINE))

    assert uses == Counter(
        {
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1": 1,
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": 1,
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c": 1,
            "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33": 1,
        }
    )
    assert "# v7.0.1" in workflow
    assert "# v8.0.1" in workflow
    assert "# v1.14.2" in workflow
