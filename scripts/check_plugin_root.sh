#!/usr/bin/env sh
# Verify that the plugin root exposes only the intended auto-discovered pieces.

set -eu

SCRIPT_DIR=$(CDPATH='' cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd "$SCRIPT_DIR/.." && pwd)
status=0

for component in commands agents hooks bin .mcp.json; do
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
