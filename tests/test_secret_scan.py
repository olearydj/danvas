from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-secrets.sh"


def write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_secret_scan_script_is_executable_and_valid_shell() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR

    result = subprocess.run(
        ["sh", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_secret_scan_help_does_not_download(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--mode all|current|history" in result.stdout


def test_secret_scan_rejects_unknown_mode_before_download(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), "--mode", "other"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "unsupported mode" in result.stderr
    assert "downloading" not in result.stdout


def test_secret_scan_verifies_pin_and_runs_both_redacted_modes(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()

    write_executable(
        fake_bin / "uname",
        'if [ "$1" = "-s" ]; then echo Linux; else echo x86_64; fi',
    )
    write_executable(
        fake_bin / "curl",
        """
printf 'curl:%s\\n' "$*" >> "$DANVAS_FAKE_LOG"
output=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--output" ]; then
        shift
        output=$1
    fi
    shift
done
: > "$output"
""".strip(),
    )
    write_executable(
        fake_bin / "sha256sum",
        """
printf 'sha256sum:%s\\n' "$*" >> "$DANVAS_FAKE_LOG"
checksum_path=$2
IFS= read -r checksum_line < "$checksum_path"
printf 'checksum:%s\\n' "$checksum_line" >> "$DANVAS_FAKE_LOG"
exit 0
""".strip(),
    )
    write_executable(
        fake_bin / "tar",
        """
printf 'tar:%s\\n' "$*" >> "$DANVAS_FAKE_LOG"
destination=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-C" ]; then
        shift
        destination=$1
    fi
    shift
done
cat > "$destination/gitleaks" <<'EOF'
#!/bin/sh
set -eu
if [ "$1" = "version" ]; then
    echo 8.30.1
    exit 0
fi
printf 'gitleaks:%s\n' "$*" >> "$DANVAS_FAKE_LOG"
EOF
chmod 755 "$destination/gitleaks"
""".strip(),
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["TMPDIR"] = str(temp_root)
    env["DANVAS_FAKE_LOG"] = str(log)
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert (
        "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
        "gitleaks_8.30.1_linux_x64.tar.gz"
    ) in calls
    assert (
        "checksum:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
        in calls
    )
    assert "gitleaks:dir --redact=100 --no-banner --no-color" in calls
    assert "gitleaks:git --redact=100 --no-banner --no-color --log-opts=--all" in calls
    assert list(temp_root.glob("danvas-gitleaks.*")) == []
