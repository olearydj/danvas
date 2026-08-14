from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "anonymous-install-smoke.sh"
VERSION = "0.18.0"
COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def fake_uv_environment(
    tmp_path: Path, *, legacy_distribution: bool = False
) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log_path = tmp_path / "uv.log"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$DANVAS_TEST_UV_LOG"
if [ "$1 $2" = "tool install" ]; then
    mkdir -p "$UV_TOOL_BIN_DIR"
    cat > "$UV_TOOL_BIN_DIR/danvas" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "--version" ]; then
    echo "danvas 0.18.0"
fi
exit 0
EOF
    chmod 755 "$UV_TOOL_BIN_DIR/danvas"
elif [ "$1 $2" = "tool list" ]; then
    echo "danvas-cli v0.18.0"
    echo "- danvas"
    if [ "${DANVAS_TEST_LEGACY:-0}" = "1" ]; then
        echo "danvas v0.17.0"
        echo "- danvas"
    fi
else
    exit 9
fi
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["TMPDIR"] = str(temp_root)
    env["DANVAS_TEST_UV_LOG"] = str(log_path)
    if legacy_distribution:
        env["DANVAS_TEST_LEGACY"] = "1"
    return env, log_path


def run_smoke(
    tmp_path: Path, ref: str, *, legacy_distribution: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path]:
    env, log_path = fake_uv_environment(tmp_path, legacy_distribution=legacy_distribution)
    result = subprocess.run(
        [str(SCRIPT), "--ref", ref, "--expected-version", VERSION],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log_path


def test_script_is_executable_and_valid_shell() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    result = subprocess.run(
        ["sh", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_candidate_install_uses_anonymous_https_and_exact_sha(tmp_path: Path) -> None:
    result, log_path = run_smoke(tmp_path, COMMIT_SHA)

    assert result.returncode == 0, result.stderr
    log = log_path.read_text(encoding="utf-8")
    assert (
        "tool install danvas-cli @ "
        f"git+https://github.com/olearydj/danvas.git@{COMMIT_SHA}"
    ) in log
    assert "git+ssh" not in log
    assert "tool list" in log


def test_tag_install_requires_tag_matching_expected_version(tmp_path: Path) -> None:
    result, log_path = run_smoke(tmp_path, "v0.18.0")

    assert result.returncode == 0, result.stderr
    assert "@v0.18.0" in log_path.read_text(encoding="utf-8")


def test_floating_or_mismatched_refs_fail_before_uv(tmp_path: Path) -> None:
    for ref in ("main", "v0.17.0", "0123456"):
        case_root = tmp_path / ref.replace("/", "-")
        case_root.mkdir()
        result, log_path = run_smoke(case_root, ref)
        assert result.returncode == 2
        assert "full lowercase commit SHA or v0.18.0" in result.stderr
        assert not log_path.exists()


def test_smoke_rejects_legacy_and_new_distributions_sharing_command(tmp_path: Path) -> None:
    result, _log_path = run_smoke(tmp_path, COMMIT_SHA, legacy_distribution=True)

    assert result.returncode == 1
    assert "legacy danvas distribution is also installed" in result.stderr
