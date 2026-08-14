#!/bin/sh

set -eu

usage() {
    cat <<'EOF'
Usage: scripts/anonymous-install-smoke.sh --ref REF --expected-version X.Y.Z

Install danvas-cli from an exact full commit SHA or matching release tag over
anonymous GitHub HTTPS, then verify the isolated danvas command. The global uv
tool installation is never modified.
EOF
}

REF=""
EXPECTED_VERSION=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --ref)
            shift
            if [ "$#" -eq 0 ] || [ -z "$1" ]; then
                echo "anonymous install smoke: --ref requires a value" >&2
                exit 2
            fi
            REF=$1
            ;;
        --expected-version)
            shift
            if [ "$#" -eq 0 ] || [ -z "$1" ]; then
                echo "anonymous install smoke: --expected-version requires a value" >&2
                exit 2
            fi
            EXPECTED_VERSION=$1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "anonymous install smoke: unsupported argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ -z "$REF" ] || [ -z "$EXPECTED_VERSION" ]; then
    echo "anonymous install smoke: --ref and --expected-version are required" >&2
    exit 2
fi

case "$EXPECTED_VERSION" in
    *[!0-9.]*|.*|*..*|*.)
        echo "anonymous install smoke: invalid expected version: $EXPECTED_VERSION" >&2
        exit 2
        ;;
esac

EXACT_REF=0
if [ "$REF" = "v$EXPECTED_VERSION" ]; then
    EXACT_REF=1
elif [ "${#REF}" -eq 40 ]; then
    case "$REF" in
        *[!0-9a-f]*) ;;
        *) EXACT_REF=1 ;;
    esac
fi
if [ "$EXACT_REF" -ne 1 ]; then
    echo "anonymous install smoke: REF must be a full lowercase commit SHA or v$EXPECTED_VERSION" >&2
    exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "anonymous install smoke: uv is required" >&2
    exit 1
fi

TEMP_BASE=${TMPDIR:-/tmp}
SMOKE_ROOT=$(mktemp -d "$TEMP_BASE/danvas-anonymous-smoke.XXXXXX")
case "$SMOKE_ROOT" in
    "$TEMP_BASE"/danvas-anonymous-smoke.*) ;;
    *)
        echo "anonymous install smoke: refusing unexpected temporary path: $SMOKE_ROOT" >&2
        exit 1
        ;;
esac

cleanup() {
    case "${SMOKE_ROOT:-}" in
        "$TEMP_BASE"/danvas-anonymous-smoke.*)
            if [ -d "$SMOKE_ROOT" ]; then
                rm -rf "$SMOKE_ROOT"
            fi
            ;;
    esac
}
trap cleanup 0
trap 'exit 1' 1 2 15

TOOL_DIR="$SMOKE_ROOT/tools"
BIN_DIR="$SMOKE_ROOT/bin"
XDG_CONFIG="$SMOKE_ROOT/xdg"
mkdir -p "$TOOL_DIR" "$BIN_DIR" "$XDG_CONFIG"

INSTALL_SPEC="danvas-cli @ git+https://github.com/olearydj/danvas.git@$REF"
echo "anonymous install smoke: installing danvas-cli from exact ref $REF"
(
    cd "$SMOKE_ROOT"
    UV_LINK_MODE=copy \
    UV_TOOL_DIR="$TOOL_DIR" \
    UV_TOOL_BIN_DIR="$BIN_DIR" \
    PATH="$BIN_DIR:$PATH" \
        uv tool install "$INSTALL_SPEC"
)

EXECUTABLE="$BIN_DIR/danvas"
if [ ! -x "$EXECUTABLE" ]; then
    echo "anonymous install smoke: danvas executable is missing" >&2
    exit 1
fi

TOOL_LIST=$(
    UV_TOOL_DIR="$TOOL_DIR" \
    UV_TOOL_BIN_DIR="$BIN_DIR" \
        uv tool list
)
if ! printf '%s\n' "$TOOL_LIST" | grep -Eq "^danvas-cli v$EXPECTED_VERSION([[:space:]]|$)"; then
    echo "anonymous install smoke: uv tool list does not show danvas-cli v$EXPECTED_VERSION" >&2
    exit 1
fi
if printf '%s\n' "$TOOL_LIST" | grep -Eq '^danvas v'; then
    echo "anonymous install smoke: legacy danvas distribution is also installed" >&2
    exit 1
fi

ACTUAL=$(PYTHONPATH= "$EXECUTABLE" --version)
if [ "$ACTUAL" != "danvas $EXPECTED_VERSION" ]; then
    echo "anonymous install smoke: command reported '$ACTUAL'" >&2
    exit 1
fi

PYTHONPATH= "$EXECUTABLE" --help >/dev/null
PYTHONPATH= \
XDG_CONFIG_HOME="$XDG_CONFIG" \
DANVAS_ANONYMOUS_SMOKE_TOKEN="not-a-real-canvas-token" \
    "$EXECUTABLE" auth doctor \
        --secret-provider env \
        --api-key-env DANVAS_ANONYMOUS_SMOKE_TOKEN >/dev/null

echo "anonymous install smoke: danvas-cli $EXPECTED_VERSION passed from $REF"
