#!/usr/bin/env bash
# Install the English /dev personal Skill for Claude Code.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_DIR="$SCRIPT_DIR/skills/dev"
VALIDATOR="$SCRIPT_DIR/scripts/validate_skill.py"

# When SCRIPT_DIR is itself the root of a git checkout that tracks
# skills/dev, stage from committed content instead of the working tree so
# untracked/ignored files and uncommitted edits never ship. A release
# tarball (or the Homebrew libexec copy, ADR-007) has no .git, so it falls
# back to the working-tree copy unchanged. Requiring SCRIPT_DIR to *be* the
# repo root (not merely inside one) matters: a plain `rev-parse --git-dir`
# search walks up to any ancestor .git, so a bare copy of this distribution
# dropped underneath an unrelated checkout would otherwise be misclassified
# as that ancestor repo, and `git archive HEAD -- skills/dev` would then
# either fail on an unmatched pathspec or, worse, archive that ancestor
# repo's unrelated tree. `--show-prefix` answers "is cwd the repo root"
# directly (empty output means yes), avoiding a path-string comparison that
# could otherwise be thrown off by symlink resolution.
IS_GIT_CHECKOUT=0
if command -v git >/dev/null 2>&1; then
  # The `if VAR=$(cmd)` form (rather than capturing output unconditionally)
  # is what lets an empty result be told apart from a failed lookup: git
  # exits non-zero with no output at all when SCRIPT_DIR isn't inside any
  # git repository, so a bare `-z "$GIT_PREFIX"` check alone would wrongly
  # treat that failure the same as "cwd is the repo root."
  if GIT_PREFIX="$(git -C "$SCRIPT_DIR" rev-parse --show-prefix 2>/dev/null)"; then
    if [[ -z "$GIT_PREFIX" ]] \
      && [[ -n "$(git -C "$SCRIPT_DIR" ls-tree -d HEAD -- skills/dev 2>/dev/null)" ]]; then
      IS_GIT_CHECKOUT=1
    fi
  fi
fi
INSTALL_COMMIT=""

LANGUAGE="en"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-${HOME:?HOME is required}/.claude}"
TARGET=""
TARGET_EXPLICIT=0
MIGRATE_LEGACY="auto"
DRY_RUN=0

usage() {
  printf '%s\n' \
    'Usage: ./install.sh [--lang en] [--config-dir DIR] [--target DIR] [--dry-run]' \
    '' \
    'Installs skills/dev as a personal Claude Code Skill.' \
    '--lang en and --lang=en are accepted for compatibility; Chinese is not distributed.' \
    'A custom --target installs in isolation and does not migrate legacy commands by default.'
}

while (($#)); do
  case "$1" in
    --lang)
      (($# >= 2)) || { printf 'ERROR: --lang requires a value\n' >&2; exit 2; }
      LANGUAGE="$2"
      shift 2
      ;;
    --lang=*) LANGUAGE="${1#*=}"; shift ;;
    --config-dir)
      (($# >= 2)) || { printf 'ERROR: --config-dir requires a value\n' >&2; exit 2; }
      CONFIG_DIR="$2"
      shift 2
      ;;
    --config-dir=*) CONFIG_DIR="${1#*=}"; shift ;;
    --target)
      (($# >= 2)) || { printf 'ERROR: --target requires a value\n' >&2; exit 2; }
      TARGET="$2"
      TARGET_EXPLICIT=1
      shift 2
      ;;
    --target=*) TARGET="${1#*=}"; TARGET_EXPLICIT=1; shift ;;
    --migrate-legacy) MIGRATE_LEGACY=1; shift ;;
    --keep-legacy) MIGRATE_LEGACY=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$LANGUAGE" != "en" ]]; then
  printf 'ERROR: this maintained distribution is English-only; use --lang en.\n' >&2
  exit 2
fi

if [[ -z "$TARGET" ]]; then TARGET="$CONFIG_DIR/skills/dev"; fi
if [[ "$MIGRATE_LEGACY" == "auto" ]]; then
  if ((TARGET_EXPLICIT)); then MIGRATE_LEGACY=0; else MIGRATE_LEGACY=1; fi
fi

case "$TARGET" in
  ''|'/'|"$HOME"|"$CONFIG_DIR")
    printf 'ERROR: unsafe install target: %s\n' "$TARGET" >&2
    exit 2
    ;;
esac
if [[ "$(basename -- "$TARGET")" != "dev" ]]; then
  printf 'ERROR: --target must be the exact dev Skill directory and end in /dev: %s\n' "$TARGET" >&2
  exit 2
fi
if [[ -L "$TARGET" ]]; then
  printf 'ERROR: refusing to replace symlink target: %s\n' "$TARGET" >&2
  exit 2
fi

command -v python3 >/dev/null || { printf 'ERROR: python3 is required for preflight validation.\n' >&2; exit 1; }
command -v rtk >/dev/null || { printf 'ERROR: RTK is required by this customized /dev workflow.\n' >&2; exit 1; }
if ((IS_GIT_CHECKOUT)) && ! command -v tar >/dev/null 2>&1; then
  printf 'ERROR: this is a git checkout of the Skill, but tar is required to stage it safely from git content. Install tar, or install from a release tarball instead.\n' >&2
  exit 1
fi
python3 "$VALIDATOR" --skill-dir "$SOURCE_DIR"

LEGACY_FILE="$CONFIG_DIR/commands/dev.md"
LEGACY_DIR="$CONFIG_DIR/commands/dev"
if [[ "$MIGRATE_LEGACY" == 1 && ( -L "$LEGACY_FILE" || -L "$LEGACY_DIR" ) ]]; then
  printf 'ERROR: refusing to migrate symlinked legacy command paths.\n' >&2
  exit 2
fi

printf 'Source: %s\nTarget: %s\n' "$SOURCE_DIR" "$TARGET"
if [[ "$MIGRATE_LEGACY" == 1 ]]; then
  printf 'Legacy migration: %s and %s\n' "$LEGACY_FILE" "$LEGACY_DIR"
else
  printf 'Legacy migration: disabled\n'
fi
if ((DRY_RUN)); then
  printf 'DRY RUN: validation passed; no files changed.\n'
  exit 0
fi

TARGET_PARENT="$(dirname -- "$TARGET")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
BACKUP_DIR="$CONFIG_DIR/backups/dev/$STAMP"
STAGE_DIR="$TARGET_PARENT/.dev-stage-$STAMP"
HAD_TARGET=0
HAD_LEGACY_FILE=0
HAD_LEGACY_DIR=0
INSTALLED_NEW=0
SUCCESS=0

rollback() {
  local status=$?
  if ((SUCCESS)); then return; fi
  printf 'Install failed; rolling back.\n' >&2
  if [[ -d "$STAGE_DIR" ]]; then rm -rf -- "$STAGE_DIR"; fi
  if ((INSTALLED_NEW)) && [[ -d "$TARGET" && ! -L "$TARGET" ]]; then rm -rf -- "$TARGET"; fi
  if ((HAD_TARGET)) && [[ -d "$BACKUP_DIR/skill" ]]; then mv -- "$BACKUP_DIR/skill" "$TARGET"; fi
  if ((HAD_LEGACY_FILE)) && [[ -f "$BACKUP_DIR/legacy/dev.md" ]]; then
    mkdir -p -- "$(dirname -- "$LEGACY_FILE")"
    mv -- "$BACKUP_DIR/legacy/dev.md" "$LEGACY_FILE"
  fi
  if ((HAD_LEGACY_DIR)) && [[ -d "$BACKUP_DIR/legacy/dev" ]]; then
    mkdir -p -- "$(dirname -- "$LEGACY_DIR")"
    mv -- "$BACKUP_DIR/legacy/dev" "$LEGACY_DIR"
  fi
  exit "$status"
}
trap rollback EXIT

mkdir -p -- "$TARGET_PARENT"
[[ -w "$TARGET_PARENT" ]] || { printf 'ERROR: target parent is not writable: %s\n' "$TARGET_PARENT" >&2; exit 1; }
mkdir -- "$STAGE_DIR"
if ((IS_GIT_CHECKOUT)); then
  INSTALL_COMMIT="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"
  git -C "$SCRIPT_DIR" archive HEAD -- skills/dev | tar -x -C "$STAGE_DIR" --strip-components=2
else
  cp -R -- "$SOURCE_DIR/." "$STAGE_DIR/"
fi
python3 "$VALIDATOR" --skill-dir "$STAGE_DIR"

if [[ "${DEV_INSTALL_FAIL_AT:-}" == "after-stage" ]]; then
  printf 'ERROR: injected failure after stage\n' >&2
  exit 97
fi

if [[ -e "$TARGET" ]]; then
  [[ -d "$TARGET" ]] || { printf 'ERROR: target exists and is not a directory: %s\n' "$TARGET" >&2; exit 2; }
  mkdir -p -- "$BACKUP_DIR"
  mv -- "$TARGET" "$BACKUP_DIR/skill"
  HAD_TARGET=1
fi

if [[ "$MIGRATE_LEGACY" == 1 && ( -e "$LEGACY_FILE" || -e "$LEGACY_DIR" ) ]]; then
  mkdir -p -- "$BACKUP_DIR/legacy"
  if [[ -e "$LEGACY_FILE" ]]; then mv -- "$LEGACY_FILE" "$BACKUP_DIR/legacy/dev.md"; HAD_LEGACY_FILE=1; fi
  if [[ -e "$LEGACY_DIR" ]]; then mv -- "$LEGACY_DIR" "$BACKUP_DIR/legacy/dev"; HAD_LEGACY_DIR=1; fi
fi

if [[ "${DEV_INSTALL_FAIL_AT:-}" == "after-backup" ]]; then
  printf 'ERROR: injected failure after backup\n' >&2
  exit 97
fi

mv -- "$STAGE_DIR" "$TARGET"
INSTALLED_NEW=1

if [[ "${DEV_INSTALL_FAIL_AT:-}" == "after-install" ]]; then
  printf 'ERROR: injected failure after install\n' >&2
  exit 97
fi

SUCCESS=1
trap - EXIT
printf 'Installed /dev Skill at %s\n' "$TARGET"
if ((IS_GIT_CHECKOUT)); then
  printf 'Installed from commit %s\n' "$INSTALL_COMMIT"
else
  printf 'Installed from: no git metadata (tarball install)\n'
fi
if [[ -d "$BACKUP_DIR" ]]; then printf 'Previous files backed up at %s\n' "$BACKUP_DIR"; fi
printf 'Restart Claude Code, then invoke /dev.\n'
