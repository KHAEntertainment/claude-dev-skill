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

# Builds a scratch PATH containing everything reachable on the real PATH
# except the named tool, so a test can prove "X is unavailable" without
# actually uninstalling anything on the host.
build_path_without() {
  local exclude="$1" scratch dir target base
  scratch="$(mktemp -d "$TEST_ROOT/fakebin-no-$exclude.XXXXXX")"
  local saved_ifs="$IFS"
  IFS=':'
  for dir in $PATH; do
    IFS="$saved_ifs"
    [[ -d "$dir" ]] || continue
    for target in "$dir"/*; do
      [[ -x "$target" ]] || continue
      base="$(basename -- "$target")"
      [[ "$base" == "$exclude" ]] && continue
      [[ -e "$scratch/$base" ]] && continue
      ln -s -- "$target" "$scratch/$base" 2>/dev/null || true
    done
    IFS=':'
  done
  IFS="$saved_ifs"
  printf '%s\n' "$scratch"
}

# Fresh installation, compatibility argument, and path containing spaces.
fresh="$TEST_ROOT/fresh config"
bash "$INSTALLER" --config-dir "$fresh" --lang=en >/dev/null
expect_file "$fresh/skills/dev/SKILL.md"
expect_file "$fresh/skills/dev/phases/phase3.5.md"
expect_file "$fresh/skills/dev/phases/external-review.md"
expect_file "$fresh/skills/dev/phases/phase5.md"
expect_file "$fresh/skills/dev/scripts/inspect_external_reviews.py"
expect_file "$fresh/skills/dev/scripts/detect_execution_backend.py"
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
# No .git here: this simulates a broken release-tarball-style copy, where
# whatever is on disk is what would ship, so a genuinely missing file must
# be caught (contrast with the git-mode "committed tree is still rejected"
# case further down, which covers the analogous git-mode failure).
broken="$TEST_ROOT/broken distribution"
mkdir -p "$broken"
cp -R "$REPO_DIR/." "$broken/repo"
rm -rf -- "$broken/repo/.git"
rm -- "$broken/repo/skills/dev/phases/phase5.md"
if bash "$broken/repo/install.sh" --config-dir "$broken/config" >/dev/null 2>&1; then fail "broken distribution unexpectedly installed"; fi
expect_absent "$broken/config"
pass "missing source file rejected before mutation"

# Dirty checkout: uncommitted edits to tracked files and ignored/untracked
# files under skills/dev must not ship (Issue #44).
dirty_source="$TEST_ROOT/dirty-source"
mkdir -p "$dirty_source"
cp -R -- "$REPO_DIR/." "$dirty_source/repo"
printf '\n<!-- local edit: must not ship -->\n' >>"$dirty_source/repo/skills/dev/SKILL.md"
mkdir -p "$dirty_source/repo/skills/dev/scripts/__pycache__"
printf 'compiled\n' >"$dirty_source/repo/skills/dev/scripts/__pycache__/x.pyc"
dirty_target="$TEST_ROOT/dirty target"
bash "$dirty_source/repo/install.sh" --config-dir "$dirty_target" --lang en >/dev/null
expect_file "$dirty_target/skills/dev/SKILL.md"
if grep -q 'local edit: must not ship' "$dirty_target/skills/dev/SKILL.md"; then
  fail "uncommitted edit to a tracked file shipped in the install"
fi
expect_absent "$dirty_target/skills/dev/scripts/__pycache__"
pass "dirty checkout excludes uncommitted edits and ignored files"

# The converse of the exclusion case above: an uncommitted *deletion* of a
# required tracked file must not block installing the perfectly valid
# committed tree. Preflight has to validate what will actually be
# installed (the committed content at HEAD), not the mutable working tree
# (Issue #44 follow-up).
dirty_deletion_source="$TEST_ROOT/dirty-deletion-source"
mkdir -p "$dirty_deletion_source"
cp -R -- "$REPO_DIR/." "$dirty_deletion_source/repo"
rm -- "$dirty_deletion_source/repo/skills/dev/phases/phase5.md"
dirty_deletion_target="$TEST_ROOT/dirty-deletion target"
bash "$dirty_deletion_source/repo/install.sh" --config-dir "$dirty_deletion_target" --lang en >/dev/null
expect_file "$dirty_deletion_target/skills/dev/phases/phase5.md"
pass "uncommitted deletion of a tracked file does not block installing the committed tree"

# The other side of that fix: a file *actually* missing from the committed
# tree (removed and committed, not just deleted on disk) must still be
# caught by preflight in git mode, before any mutation — the fix above
# must not have quietly turned preflight validation off for git checkouts.
committed_broken_source="$TEST_ROOT/committed-broken-source"
git clone --quiet -- "$REPO_DIR" "$committed_broken_source"
git -c user.name=test -c user.email=test@example.com \
  -C "$committed_broken_source" rm --quiet -- skills/dev/phases/phase5.md
git -c user.name=test -c user.email=test@example.com \
  -C "$committed_broken_source" commit --quiet -m "remove a required file"
committed_broken_target="$TEST_ROOT/committed-broken target"
if bash "$committed_broken_source/install.sh" --config-dir "$committed_broken_target" --lang en >/dev/null 2>&1; then
  fail "install with a required file missing from the committed tree unexpectedly succeeded"
fi
expect_absent "$committed_broken_target"
pass "a required file missing from the committed tree is still rejected before mutation"

# A dangling .git symlink is still a .git entry: -e alone follows the link
# and reports false when its target doesn't exist, which would otherwise
# read as "no git metadata" and take the copy path, shipping whatever is
# on disk (Issue #44 follow-up).
dangling_source="$TEST_ROOT/dangling-git-source"
mkdir -p "$dangling_source"
cp -R -- "$REPO_DIR/." "$dangling_source/repo"
rm -rf -- "$dangling_source/repo/.git"
ln -s -- "/nonexistent/path/to/a/gitdir" "$dangling_source/repo/.git"
mkdir -p "$dangling_source/repo/skills/dev/scripts/__pycache__"
printf 'compiled\n' >"$dangling_source/repo/skills/dev/scripts/__pycache__/x.pyc"
dangling_target="$TEST_ROOT/dangling-git target"
if bash "$dangling_source/repo/install.sh" --config-dir "$dangling_target" --lang en >/dev/null 2>&1; then
  fail "install with a dangling .git symlink unexpectedly succeeded"
fi
expect_absent "$dangling_target"
pass "dangling .git symlink aborts instead of falling back to the copy path"

# No .git source: falls back to the working-tree copy and reports tarball
# provenance instead of a commit (Issue #44, ADR-007 tarball/libexec case).
nogit_source="$TEST_ROOT/nogit-source"
mkdir -p "$nogit_source"
cp -R -- "$REPO_DIR/." "$nogit_source/repo"
rm -rf -- "$nogit_source/repo/.git"
nogit_target="$TEST_ROOT/nogit target"
nogit_output="$(bash "$nogit_source/repo/install.sh" --config-dir "$nogit_target" --lang en)"
expect_file "$nogit_target/skills/dev/SKILL.md"
if ! grep -q 'Installed from: no git metadata (tarball install)' <<<"$nogit_output"; then
  fail "no-.git install did not report tarball provenance"
fi
pass "no-.git source installs via the copy path with tarball provenance"

# A source with no .git of its own, sitting underneath an unrelated git
# checkout, must not be misclassified as that ancestor's repo: it has to
# install via the copy path too, not attempt (and fail) a git archive of
# the ancestor's unrelated tree (Issue #44 follow-up).
nested_parent="$TEST_ROOT/nested-parent"
mkdir -p "$nested_parent"
git init --quiet -- "$nested_parent"
# -c user.name/user.email keep this fixture hermetic: a CI runner with no
# git identity configured (no ~/.gitconfig, no GECOS full name) otherwise
# fails this commit with "Please tell me who you are."
git -c user.name=test -c user.email=test@example.com \
  -C "$nested_parent" commit --quiet --allow-empty -m "unrelated ancestor root commit"
mkdir -p "$nested_parent/nested"
cp -R -- "$REPO_DIR/." "$nested_parent/nested/repo"
rm -rf -- "$nested_parent/nested/repo/.git"
nested_target="$TEST_ROOT/nested target"
nested_output="$(bash "$nested_parent/nested/repo/install.sh" --config-dir "$nested_target" --lang en)"
expect_file "$nested_target/skills/dev/SKILL.md"
if ! grep -q 'Installed from: no git metadata (tarball install)' <<<"$nested_output"; then
  fail "nested no-own-.git install did not report tarball provenance"
fi
pass "nested source with no own .git installs via the copy path"

# A source with its own .git but no git binary on PATH must abort with an
# actionable error and install nothing — never silently fall back to the
# copy path, which would ship possibly-dirty working-tree content while
# looking, from the outside, exactly like the safe case (Issue #44
# follow-up).
no_git_bin_path="$(build_path_without git)"
no_git_bin_target="$TEST_ROOT/no-git-bin target"
if PATH="$no_git_bin_path" bash "$INSTALLER" --config-dir "$no_git_bin_target" --lang en >/dev/null 2>&1; then
  fail "install unexpectedly succeeded with git unavailable in a git checkout"
fi
expect_absent "$no_git_bin_target"
pass "git checkout with git binary unavailable aborts and installs nothing"

# A genuine git checkout with tar unavailable must abort the same way,
# rather than silently shipping the working tree with false git provenance
# (Issue #44 follow-up; PowerShell has the mirrored case already).
no_tar_bin_path="$(build_path_without tar)"
no_tar_bin_target="$TEST_ROOT/no-tar-bin target"
if PATH="$no_tar_bin_path" bash "$INSTALLER" --config-dir "$no_tar_bin_target" --lang en >/dev/null 2>&1; then
  fail "install unexpectedly succeeded with tar unavailable in a git checkout"
fi
expect_absent "$no_tar_bin_target"
pass "git checkout with tar unavailable aborts and installs nothing"

# Clean checkout: the installed tree matches a plain git archive of HEAD,
# and the install reports the staged commit (Issue #44).
clean_target="$TEST_ROOT/clean target"
clean_output="$(bash "$INSTALLER" --config-dir "$clean_target" --lang en)"
expected_commit="$(git -C "$REPO_DIR" rev-parse HEAD)"
if ! grep -q "Installed from commit $expected_commit" <<<"$clean_output"; then
  fail "clean checkout install did not report the staged commit"
fi
archive_check="$TEST_ROOT/archive-check"
mkdir -p "$archive_check"
git -C "$REPO_DIR" archive HEAD -- skills/dev | tar -x -C "$archive_check" --strip-components=2
diff -r "$archive_check" "$clean_target/skills/dev" >/dev/null || fail "installed tree differs from git archive of HEAD"
pass "clean checkout install matches git archive and reports commit provenance"

# Static guard against the provenance race regressing: both archive calls
# must pin the commit already captured and validated (INSTALL_COMMIT), not
# re-resolve HEAD at staging time, which would reopen a window where a
# concurrent commit could make the archived content disagree with the
# commit the install reports (Issue #44 follow-up).
# shellcheck disable=SC2016 # literal source text to grep for, not expansion
if grep -Eq 'git -C "\$SCRIPT_DIR" archive HEAD\b' "$INSTALLER"; then
  fail "install.sh archives HEAD directly instead of the captured INSTALL_COMMIT"
fi
# shellcheck disable=SC2016 # literal source text to grep for, not expansion
if ! grep -Fq 'archive "$INSTALL_COMMIT"' "$INSTALLER"; then
  fail "install.sh does not archive the captured INSTALL_COMMIT"
fi
pass "install.sh archives the captured commit, not HEAD, at staging time"

# GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR inherited from the caller's
# environment override `-C`'s repository discovery entirely, so without
# neutralizing them a perfectly valid own-.git checkout could silently
# validate, archive, and install a completely different repository's
# committed tree while reporting *its* commit (Issue #44 follow-up).
# GIT_COMMON_DIR is the linked-worktree analog of GIT_DIR; poisoning it
# alongside the other two is defense in depth even though it did not
# independently redirect this worktree-less checkout. Point all three at
# a disposable repo carrying a planted marker file and confirm the real
# source's own tree and commit are what actually gets installed.
env_hijack_alt="$TEST_ROOT/env-hijack-alt"
mkdir -p "$env_hijack_alt"
cp -R -- "$REPO_DIR/skills" "$env_hijack_alt/skills"
rm -rf -- "$env_hijack_alt/.git"
git init --quiet -- "$env_hijack_alt"
printf 'planted by an unrelated repo; must never ship\n' >"$env_hijack_alt/skills/dev/ENV_HIJACK_MARKER.txt"
git -C "$env_hijack_alt" add -A
git -c user.name=test -c user.email=test@example.com \
  -C "$env_hijack_alt" commit --quiet -m "alt repo commit carrying a planted marker"
env_hijack_target="$TEST_ROOT/env-hijack target"
expected_real_commit="$(git -C "$REPO_DIR" rev-parse HEAD)"
env_hijack_output="$(GIT_DIR="$env_hijack_alt/.git" GIT_WORK_TREE="$env_hijack_alt" GIT_COMMON_DIR="$env_hijack_alt/.git" \
  bash "$INSTALLER" --config-dir "$env_hijack_target" --lang en)"
expect_file "$env_hijack_target/skills/dev/SKILL.md"
expect_absent "$env_hijack_target/skills/dev/ENV_HIJACK_MARKER.txt"
if ! grep -q "Installed from commit $expected_real_commit" <<<"$env_hijack_output"; then
  fail "install reported the wrong commit under an inherited GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR"
fi
pass "inherited GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR cannot redirect install to another repository"

printf 'All %d installer tests passed.\n' "$pass_count"
