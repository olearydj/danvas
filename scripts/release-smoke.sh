#!/bin/sh

set -eu

usage() {
    cat <<'EOF'
Usage: scripts/release-smoke.sh [--expected-version X.Y.Z]

Build danvas, install the checkout and wheel into separate temporary uv tool
directories, and run non-network startup checks. The global tool installation
is never modified.
EOF
}

EXPECTED_VERSION=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --expected-version)
            shift
            if [ "$#" -eq 0 ]; then
                echo "release smoke: --expected-version requires a value" >&2
                exit 2
            fi
            EXPECTED_VERSION=$1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "release smoke: unsupported argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

SCRIPT_DIR=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -P "$SCRIPT_DIR/.." && pwd)
PYPROJECT="$PROJECT_ROOT/pyproject.toml"

if [ ! -r "$PYPROJECT" ]; then
    echo "release smoke: cannot read $PYPROJECT" >&2
    exit 1
fi

PROJECT_VERSION=$(
    awk '
        $0 == "[project]" { in_project = 1; next }
        in_project && /^\[/ { exit }
        in_project && /^[[:space:]]*version[[:space:]]*=/ {
            line = $0
            sub(/^[^=]*=[[:space:]]*"/, "", line)
            sub(/".*$/, "", line)
            print line
            exit
        }
    ' "$PYPROJECT"
)

if [ -z "$PROJECT_VERSION" ]; then
    echo "release smoke: could not resolve [project].version from pyproject.toml" >&2
    exit 1
fi

if [ -z "$EXPECTED_VERSION" ]; then
    EXPECTED_VERSION=$PROJECT_VERSION
fi

if [ "$EXPECTED_VERSION" != "$PROJECT_VERSION" ]; then
    echo "release smoke: expected version $EXPECTED_VERSION does not match package version $PROJECT_VERSION" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "release smoke: uv is required" >&2
    exit 1
fi

TEMP_BASE=${TMPDIR:-/tmp}
SMOKE_ROOT=$(mktemp -d "$TEMP_BASE/danvas-release-smoke.XXXXXX")
case "$SMOKE_ROOT" in
    "$TEMP_BASE"/danvas-release-smoke.*) ;;
    *)
        echo "release smoke: refusing unexpected temporary path: $SMOKE_ROOT" >&2
        exit 1
        ;;
esac

cleanup() {
    case "${SMOKE_ROOT:-}" in
        "$TEMP_BASE"/danvas-release-smoke.*)
            if [ -d "$SMOKE_ROOT" ]; then
                rm -rf "$SMOKE_ROOT"
            fi
            ;;
    esac
}
trap cleanup 0
trap 'exit 1' 1 2 15

DIST_DIR="$SMOKE_ROOT/dist"
EDITABLE_TOOL_DIR="$SMOKE_ROOT/editable-tools"
EDITABLE_BIN_DIR="$SMOKE_ROOT/editable-bin"
WHEEL_TOOL_DIR="$SMOKE_ROOT/wheel-tools"
WHEEL_BIN_DIR="$SMOKE_ROOT/wheel-bin"
mkdir -p \
    "$DIST_DIR" \
    "$EDITABLE_TOOL_DIR" \
    "$EDITABLE_BIN_DIR" \
    "$WHEEL_TOOL_DIR" \
    "$WHEEL_BIN_DIR"

echo "release smoke: building danvas $PROJECT_VERSION"
(
    cd "$PROJECT_ROOT"
    uv build --out-dir "$DIST_DIR"
)

WHEEL_PATH=""
WHEEL_COUNT=0
for candidate in "$DIST_DIR"/danvas-"$PROJECT_VERSION"-*.whl; do
    if [ ! -f "$candidate" ]; then
        continue
    fi
    WHEEL_PATH=$candidate
    WHEEL_COUNT=$((WHEEL_COUNT + 1))
done
if [ "$WHEEL_COUNT" -ne 1 ]; then
    echo "release smoke: expected one wheel for $PROJECT_VERSION, found $WHEEL_COUNT" >&2
    exit 1
fi

SDIST_COUNT=0
for candidate in "$DIST_DIR"/danvas-"$PROJECT_VERSION".tar.gz; do
    if [ -f "$candidate" ]; then
        SDIST_COUNT=$((SDIST_COUNT + 1))
    fi
done
if [ "$SDIST_COUNT" -ne 1 ]; then
    echo "release smoke: expected one source distribution for $PROJECT_VERSION, found $SDIST_COUNT" >&2
    exit 1
fi

echo "release smoke: installing editable checkout in isolation"
(
    cd "$SMOKE_ROOT"
    UV_LINK_MODE=copy \
    UV_TOOL_DIR="$EDITABLE_TOOL_DIR" \
    UV_TOOL_BIN_DIR="$EDITABLE_BIN_DIR" \
    PATH="$EDITABLE_BIN_DIR:$PATH" \
        uv tool install --force --editable "$PROJECT_ROOT"
)

echo "release smoke: installing built wheel in isolation"
(
    cd "$SMOKE_ROOT"
    UV_LINK_MODE=copy \
    UV_TOOL_DIR="$WHEEL_TOOL_DIR" \
    UV_TOOL_BIN_DIR="$WHEEL_BIN_DIR" \
    PATH="$WHEEL_BIN_DIR:$PATH" \
        uv tool install --force --from "$WHEEL_PATH" danvas
)

check_install() {
    label=$1
    bin_dir=$2
    executable="$bin_dir/danvas"
    xdg_config="$SMOKE_ROOT/$label-xdg"

    if [ ! -x "$executable" ]; then
        echo "release smoke: $label executable is missing: $executable" >&2
        exit 1
    fi

    actual=$(PYTHONPATH= "$executable" --version)
    if [ "$actual" != "danvas $PROJECT_VERSION" ]; then
        echo "release smoke: $label reported '$actual', expected 'danvas $PROJECT_VERSION'" >&2
        exit 1
    fi

    PYTHONPATH= "$executable" --help >/dev/null
    mkdir -p "$xdg_config"
    PYTHONPATH= \
    XDG_CONFIG_HOME="$xdg_config" \
    DANVAS_RELEASE_SMOKE_TOKEN="not-a-real-canvas-token" \
        "$executable" auth doctor \
            --secret-provider env \
            --api-key-env DANVAS_RELEASE_SMOKE_TOKEN >/dev/null
    echo "release smoke: $label install passed version, help, and auth doctor"
}

check_install editable "$EDITABLE_BIN_DIR"
check_install wheel "$WHEEL_BIN_DIR"

echo "release smoke: danvas $PROJECT_VERSION passed"
