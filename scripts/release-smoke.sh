#!/bin/sh

set -eu

usage() {
    cat <<'EOF'
Usage: scripts/release-smoke.sh [--expected-version X.Y.Z]

Build the danvas-cli distribution, inspect its metadata and contents, install
the checkout and wheel into separate temporary uv tool directories, and run
non-network startup checks. The global tool installation is never modified.
EOF
}

EXPECTED_VERSION=""
EXPECTED_VERSION_PROVIDED=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --expected-version)
            shift
            if [ "$#" -eq 0 ] || [ -z "$1" ]; then
                echo "release smoke: --expected-version requires a non-empty value" >&2
                exit 2
            fi
            EXPECTED_VERSION=$1
            EXPECTED_VERSION_PROVIDED=1
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

SCRIPT_DIR=$(CDPATH='' cd -P "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(CDPATH='' cd -P "$SCRIPT_DIR/.." && pwd)
PYPROJECT="$PROJECT_ROOT/pyproject.toml"
DIST_CHECK="$PROJECT_ROOT/scripts/check-distributions.py"

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

PROJECT_NAME=$(
    awk '
        $0 == "[project]" { in_project = 1; next }
        in_project && /^\[/ { exit }
        in_project && /^[[:space:]]*name[[:space:]]*=/ {
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

if [ "$PROJECT_NAME" != "danvas-cli" ]; then
    echo "release smoke: expected distribution name danvas-cli, found '$PROJECT_NAME'" >&2
    exit 1
fi

if [ ! -r "$DIST_CHECK" ]; then
    echo "release smoke: cannot read $DIST_CHECK" >&2
    exit 1
fi

if [ "$EXPECTED_VERSION_PROVIDED" -eq 0 ]; then
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
    cleanup_code=$?
    trap - 0
    case "${SMOKE_ROOT:-}" in
        "$TEMP_BASE"/danvas-release-smoke.*)
            if [ -d "$SMOKE_ROOT" ]; then
                rm -rf "$SMOKE_ROOT"
            fi
            ;;
    esac
    exit "$cleanup_code"
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

echo "release smoke: building $PROJECT_NAME $PROJECT_VERSION"
(
    cd "$PROJECT_ROOT"
    uv build --out-dir "$DIST_DIR"
)

WHEEL_PATH=""
WHEEL_COUNT=0
for candidate in "$DIST_DIR"/danvas_cli-"$PROJECT_VERSION"-*.whl; do
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

SDIST_PATH="$DIST_DIR/danvas_cli-$PROJECT_VERSION.tar.gz"
SDIST_COUNT=0
if [ -f "$SDIST_PATH" ]; then
    SDIST_COUNT=1
fi
if [ "$SDIST_COUNT" -ne 1 ]; then
    echo "release smoke: expected one source distribution for $PROJECT_VERSION, found $SDIST_COUNT" >&2
    exit 1
fi

uv run --project "$PROJECT_ROOT" python "$DIST_CHECK" \
    "$WHEEL_PATH" "$SDIST_PATH" --expected-version "$PROJECT_VERSION"

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
        uv tool install --force --from "$WHEEL_PATH" "$PROJECT_NAME"
)

check_install() {
    label=$1
    bin_dir=$2
    executable="$bin_dir/danvas"
    xdg_config="$SMOKE_ROOT/$label-xdg"
    clean_home="$SMOKE_ROOT/$label-home"

    if [ ! -x "$executable" ]; then
        echo "release smoke: $label executable is missing: $executable" >&2
        exit 1
    fi

    mkdir -p "$xdg_config" "$clean_home"
    actual=$(
        cd "$SMOKE_ROOT"
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" --version
    )
    if [ "$actual" != "danvas $PROJECT_VERSION" ]; then
        echo "release smoke: $label reported '$actual', expected 'danvas $PROJECT_VERSION'" >&2
        exit 1
    fi

    (
        cd "$SMOKE_ROOT"
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" --help >/dev/null
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            DANVAS_RELEASE_SMOKE_TOKEN="not-a-real-canvas-token" \
            "$executable" auth doctor \
                --api-url https://canvas.example.invalid/ \
                --api-key-env DANVAS_RELEASE_SMOKE_TOKEN >/dev/null
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" guide list >/dev/null
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" describe assignments create --format json >/dev/null
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" skill show >/dev/null
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" skill install --agent shared --dry-run >/dev/null
        if [ -e "$clean_home/.agents" ]; then
            echo "release smoke: $label skill dry-run wrote to the temporary home" >&2
            exit 1
        fi
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" skill install --agent shared >/dev/null
        if [ ! -f "$clean_home/.agents/skills/danvas/SKILL.md" ]; then
            echo "release smoke: $label skill install missed its confined target" >&2
            exit 1
        fi
        env -i \
            PATH="$bin_dir:$PATH" \
            HOME="$clean_home" \
            XDG_CONFIG_HOME="$xdg_config" \
            PYTHONPATH= \
            "$executable" skill doctor \
                --agent shared --project-root "$SMOKE_ROOT" >/dev/null
    )
    echo "release smoke: $label install passed CLI, guide, description, and skill checks"
}

check_install editable "$EDITABLE_BIN_DIR"
check_install wheel "$WHEEL_BIN_DIR"

echo "release smoke: danvas $PROJECT_VERSION passed"
