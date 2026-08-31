#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTALLER="$REPO_DIR/install.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/claude-dev-install.XXXXXX")"

cleanup() {
  chmod -R u+w "$TEST_ROOT" 2>/dev/null || true
  rm -rf -- "$TEST_ROOT"
}
trap cleanup EXIT

pass_count=0
pass() { printf 'PASS: %s\n' "$1"; pass_count=$((pass_count + 1)); }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
expect_file() { [[ -f "$1" ]] || fail "missing file $1"; }
expect_absent() { [[ ! -e "$1" ]] || fail "unexpected path $1"; }

# Fresh installation, compatibility argument, and path containing spaces.
fresh="$TEST_ROOT/fresh config"
bash "$INSTALLER" --config-dir "$fresh" --lang=en >/dev/null
expect_file "$fresh/skills/dev/SKILL.md"
expect_file "$fresh/skills/dev/phases/phase3.5.md"
expect_file "$fresh/skills/dev/phases/external-review.md"
expect_file "$fresh/skills/dev/phases/phase5.md"
expect_file "$fresh/skills/dev/scripts/inspect_external_reviews.py"
expect_file "$fresh/skills/dev/scripts/detect_execution_backend.py"
expect_file "$fresh/skills/dev/scripts/resolve_repository.py"
expect_file "$fresh/skills/dev/backends/contract.md"
expect_file "$fresh/skills/dev/backends/claude-native.md"
expect_file "$fresh/skills/dev/backends/traycer.md"
expect_file "$fresh/skills/dev/agents/report-back.md"
expect_file "$fresh/skills/dev/agents/reviewer.md"
expect_file "$fresh/skills/dev/templates/DEV_STATE_TEMPLATE.md"
pass "fresh install with path spaces"

# Dry run must not create the target.
dry="$TEST_ROOT/dry run config"
bash "$INSTALLER" --config-dir "$dry" --lang en --dry-run >/dev/null
expect_absent "$dry"
pass "dry run is non-mutating"

# English-only rejection must happen before mutation.
invalid="$TEST_ROOT/invalid language"
if bash "$INSTALLER" --config-dir "$invalid" --lang zh >/dev/null 2>&1; then fail "Chinese install unexpectedly succeeded"; fi
expect_absent "$invalid"
pass "unsupported language rejected before mutation"

# Explicit target is isolated and keeps a legacy command by default.
isolated_config="$TEST_ROOT/isolated config"
isolated_target="$TEST_ROOT/custom target/dev"
mkdir -p "$isolated_config/commands"
printf 'legacy\n' >"$isolated_config/commands/dev.md"
bash "$INSTALLER" --config-dir "$isolated_config" --target "$isolated_target" >/dev/null
expect_file "$isolated_target/SKILL.md"
expect_file "$isolated_config/commands/dev.md"
pass "explicit target does not migrate legacy command"

# Default target migrates legacy command files into a timestamped backup.
legacy="$TEST_ROOT/legacy config"
mkdir -p "$legacy/commands/dev"
printf 'legacy entry\n' >"$legacy/commands/dev.md"
printf 'legacy phase\n' >"$legacy/commands/dev/phase.md"
bash "$INSTALLER" --config-dir "$legacy" >/dev/null
expect_file "$legacy/skills/dev/SKILL.md"
expect_absent "$legacy/commands/dev.md"
expect_absent "$legacy/commands/dev"
legacy_backup="$(find "$legacy/backups/dev" -type f -name dev.md -print -quit)"
[[ -n "$legacy_backup" ]] || fail "legacy command backup missing"
pass "legacy command migration and backup"

# A rerun replaces the Skill and backs up the previous version.
printf 'old marker\n' >"$legacy/skills/dev/old-marker.txt"
bash "$INSTALLER" --config-dir "$legacy" >/dev/null
expect_absent "$legacy/skills/dev/old-marker.txt"
old_marker="$(find "$legacy/backups/dev" -type f -name old-marker.txt -print -quit)"
[[ -n "$old_marker" ]] || fail "previous Skill backup missing on rerun"
pass "idempotent rerun with previous-version backup"

# Failure after backup must restore both existing Skill and legacy command.
rollback="$TEST_ROOT/rollback config"
mkdir -p "$rollback/skills/dev" "$rollback/commands/dev"
printf 'old skill\n' >"$rollback/skills/dev/old.txt"
printf 'legacy entry\n' >"$rollback/commands/dev.md"
printf 'legacy phase\n' >"$rollback/commands/dev/old-phase.md"
if DEV_INSTALL_FAIL_AT=after-backup bash "$INSTALLER" --config-dir "$rollback" >/dev/null 2>&1; then fail "injected failure unexpectedly succeeded"; fi
expect_file "$rollback/skills/dev/old.txt"
expect_file "$rollback/commands/dev.md"
expect_file "$rollback/commands/dev/old-phase.md"
pass "rollback after backup"

# Symlink targets are refused without changing the link destination.
symlink_case="$TEST_ROOT/symlink case"
mkdir -p "$symlink_case/config/skills" "$symlink_case/real-dev"
printf 'sentinel\n' >"$symlink_case/real-dev/sentinel.txt"
ln -s "$symlink_case/real-dev" "$symlink_case/config/skills/dev"
if bash "$INSTALLER" --config-dir "$symlink_case/config" >/dev/null 2>&1; then fail "symlink target unexpectedly accepted"; fi
expect_file "$symlink_case/real-dev/sentinel.txt"
pass "symlink target refusal"

# Missing distribution files fail preflight without creating a target.
broken="$TEST_ROOT/broken distribution"
mkdir -p "$broken"
cp -R "$REPO_DIR/." "$broken/repo"
rm -- "$broken/repo/skills/dev/phases/phase5.md"
if bash "$broken/repo/install.sh" --config-dir "$broken/config" >/dev/null 2>&1; then fail "broken distribution unexpectedly installed"; fi
expect_absent "$broken/config"
pass "missing source file rejected before mutation"

printf 'All %d installer tests passed.\n' "$pass_count"
