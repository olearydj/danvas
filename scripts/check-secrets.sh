#!/bin/sh

set -eu

GITLEAKS_VERSION="8.30.1"

usage() {
    cat <<'EOF'
Usage: scripts/check-secrets.sh [--mode all|current|history]

Download the pinned Gitleaks release after verifying its published SHA-256,
then scan the current working tree, all reachable Git history, or both. Scan
output is fully redacted and no report artifact is retained.
EOF
}

MODE="all"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --mode)
            shift
            if [ "$#" -eq 0 ] || [ -z "$1" ]; then
                echo "secret scan: --mode requires all, current, or history" >&2
                exit 2
            fi
            MODE=$1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "secret scan: unsupported argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

case "$MODE" in
    all|current|history) ;;
    *)
        echo "secret scan: unsupported mode: $MODE" >&2
        exit 2
        ;;
esac

SCRIPT_DIR=$(CDPATH='' cd -P "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH='' cd -P "$SCRIPT_DIR/.." && pwd)

SYSTEM=$(uname -s)
MACHINE=$(uname -m)
case "$SYSTEM:$MACHINE" in
    Darwin:arm64|Darwin:aarch64)
        PLATFORM="darwin_arm64"
        ARCHIVE_SHA256="b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5"
        ;;
    Darwin:x86_64|Darwin:amd64)
        PLATFORM="darwin_x64"
        ARCHIVE_SHA256="dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709"
        ;;
    Linux:aarch64|Linux:arm64)
        PLATFORM="linux_arm64"
        ARCHIVE_SHA256="e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080"
        ;;
    Linux:x86_64|Linux:amd64)
        PLATFORM="linux_x64"
        ARCHIVE_SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
        ;;
    *)
        echo "secret scan: unsupported platform: $SYSTEM $MACHINE" >&2
        exit 1
        ;;
esac

if ! command -v curl >/dev/null 2>&1; then
    echo "secret scan: curl is required" >&2
    exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
    echo "secret scan: tar is required" >&2
    exit 1
fi

TEMP_BASE=${TMPDIR:-/tmp}
SCAN_ROOT=$(mktemp -d "$TEMP_BASE/danvas-gitleaks.XXXXXX")
case "$SCAN_ROOT" in
    "$TEMP_BASE"/danvas-gitleaks.*) ;;
    *)
        echo "secret scan: refusing unexpected temporary path: $SCAN_ROOT" >&2
        exit 1
        ;;
esac

cleanup() {
    cleanup_code=$?
    trap - 0
    case "${SCAN_ROOT:-}" in
        "$TEMP_BASE"/danvas-gitleaks.*)
            if [ -d "$SCAN_ROOT" ]; then
                rm -rf "$SCAN_ROOT"
            fi
            ;;
    esac
    exit "$cleanup_code"
}
trap cleanup 0
trap 'exit 1' 1 2 15

ARCHIVE_NAME="gitleaks_${GITLEAKS_VERSION}_${PLATFORM}.tar.gz"
ARCHIVE_PATH="$SCAN_ROOT/$ARCHIVE_NAME"
CHECKSUM_PATH="$SCAN_ROOT/checksums.txt"
DOWNLOAD_URL="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${ARCHIVE_NAME}"

echo "secret scan: downloading Gitleaks $GITLEAKS_VERSION for $PLATFORM"
curl --fail --silent --show-error --location \
    --proto '=https' --tlsv1.2 \
    "$DOWNLOAD_URL" --output "$ARCHIVE_PATH"

printf '%s  %s\n' "$ARCHIVE_SHA256" "$ARCHIVE_PATH" > "$CHECKSUM_PATH"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$CHECKSUM_PATH" >/dev/null
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c "$CHECKSUM_PATH" >/dev/null
else
    echo "secret scan: sha256sum or shasum is required" >&2
    exit 1
fi

tar -xzf "$ARCHIVE_PATH" -C "$SCAN_ROOT" gitleaks
GITLEAKS="$SCAN_ROOT/gitleaks"
if [ ! -x "$GITLEAKS" ]; then
    echo "secret scan: verified archive did not contain the gitleaks executable" >&2
    exit 1
fi

ACTUAL_VERSION=$($GITLEAKS version)
if [ "$ACTUAL_VERSION" != "$GITLEAKS_VERSION" ]; then
    echo "secret scan: expected Gitleaks $GITLEAKS_VERSION, found $ACTUAL_VERSION" >&2
    exit 1
fi

if [ "$MODE" = "all" ] || [ "$MODE" = "current" ]; then
    echo "secret scan: scanning current working tree"
    "$GITLEAKS" dir \
        --redact=100 \
        --no-banner \
        --no-color \
        "$PROJECT_ROOT"
fi

if [ "$MODE" = "all" ] || [ "$MODE" = "history" ]; then
    echo "secret scan: scanning all reachable Git history"
    "$GITLEAKS" git \
        --redact=100 \
        --no-banner \
        --no-color \
        --log-opts=--all \
        "$PROJECT_ROOT"
fi

echo "secret scan: $MODE scan passed with Gitleaks $GITLEAKS_VERSION"
