#!/usr/bin/env sh
# Verify that the plugin root exposes only the intended auto-discovered pieces.

set -eu

SCRIPT_PATH=$0
while [ -L "$SCRIPT_PATH" ]; do
    SCRIPT_DIR=$(CDPATH='' cd -P "$(dirname "$SCRIPT_PATH")" && pwd)
    LINK_TARGET=$(readlink "$SCRIPT_PATH")
    case $LINK_TARGET in
        /*) SCRIPT_PATH=$LINK_TARGET ;;
        *) SCRIPT_PATH=$SCRIPT_DIR/$LINK_TARGET ;;
    esac
done

SCRIPT_DIR=$(CDPATH='' cd -P "$(dirname "$SCRIPT_PATH")" && pwd)
REPO_ROOT=$(CDPATH='' cd "$SCRIPT_DIR/.." && pwd)
status=0

# https://code.claude.com/docs/en/plugins-reference#file-locations-reference
for component in \
    commands agents hooks bin .mcp.json workflows output-styles themes \
    .lsp.json monitors settings.json; do
    path="$REPO_ROOT/$component"
    if [ -e "$path" ] || [ -L "$path" ]; then
        printf 'ERROR: unexpected plugin-root component: %s\n' "$component" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    exit 1
fi

printf '%s\n' 'OK: plugin root exposes only allowed auto-discovered components'
