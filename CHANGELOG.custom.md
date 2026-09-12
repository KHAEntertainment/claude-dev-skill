# Customized Distribution Changelog

Release tags follow plain semver (`vX.Y.Z`) starting at `v2.0.0`. Upstream
occupies `v1.0.0`–`v1.3.0` in this repository's history and continues to
publish on that line, so the fork's releases begin at 2.x to stay
collision-free. From `v2.0.0` onward, upstream provenance is retained as semver
build metadata in `skills/dev/SKILL.md` (`2.0.0+upstream.3e87db0`). Entries below
`v2.0.0` predate that scheme: they use `custom-vX.Y.Z-upstream.SHA` headings and
record upstream SHAs as plain text in their `### Upstream` blocks.

## v2.1.1 — Unreleased

### Added

- Unconditional post-merge verification step (#26), owned by the lead and run
  after every merge regardless of how clean pre-merge review looked. It never
  blocks the merge; its outputs are a ledger entry or a reopened Issue. When
  the merge commit's tree hash matches the verified PR head's tree hash, the
  PR-head Verification Gate result applies to `main` verbatim; otherwise the
  gate is re-run against `main` checked out at the merge commit, which the
  gate had otherwise only ever run against the PR branch. The closed Issue's
  acceptance criteria are then re-read against the merged code and confirmed,
  or the Issue is reopened naming the specific unmet items — auto-closure by
  a merge keyword is never evidence of completion. The result (`merge_sha`,
  `gate_result`, `criteria_verdict`) is recorded in `.agent/dev-state.md`;
  Phase 5's retro now reads these records instead of trusting a merge to mean
  done. A bypassed merge's debt still lives in `external-review.md`'s
  commit-range rule, cross-referenced rather than duplicated.
  `validate_skill.py` and the doc-assertion test suite pin the new
  load-bearing sentences.

### Fixed

- `install.sh` and `install.ps1` no longer ship whatever is sitting on disk
  under `skills/dev` (#44). Whether the installer's own directory *looks
  like* a git checkout (a `.git` entry — directory, symlink (dangling or
  not), or for a linked worktree the `gitdir: ...` file — is present) and
  whether it can actually be *validated* as one are checked separately,
  and a directory that looks like a checkout but can't be validated always
  aborts rather than silently copying: doing otherwise would ship
  possibly-dirty working-tree content while looking, from the outside,
  exactly like the safe case. The full matrix, implemented identically in
  both installers:
  - own `.git` + validates (git present; `git rev-parse --show-prefix` is
    empty, meaning the installer's own directory *is* the repo root and
    not merely inside one; `git ls-tree -d HEAD -- skills/dev` is
    non-empty) + `tar` available → stage via `git archive <commit> --
    skills/dev` (piped through `tar` for `install.sh`; written to a temp
    file and extracted for `install.ps1`, avoiding PowerShell's
    native-to-native pipe binary corruption risk). Untracked/ignored files
    (`scripts/__pycache__/*.pyc` and similar) and uncommitted edits to
    tracked files never reach the installed Skill this way; the exec bit
    is preserved via git's stored file mode. The commit is captured once,
    as part of the same validation chain, and every archive of it — the
    preflight check below and the real staging step — reuses that exact
    value rather than re-resolving `HEAD`, which would otherwise leave a
    window where a concurrent commit on the checkout could make the
    archived content disagree with the commit the install reports.
  - own `.git` + validates + `tar` missing → abort with an actionable
    error, never fall back to the copy path while still claiming git
    provenance.
  - own `.git` + does not validate (git binary missing, or `SCRIPT_DIR`
    isn't actually the repo root, or `skills/dev` isn't tracked at HEAD)
    → abort with an actionable error. (Checking `--show-prefix` for
    emptiness, rather than comparing `--show-toplevel`'s output against
    `SCRIPT_DIR`/`PSScriptRoot` as a string, sidesteps a real symlink
    resolution mismatch hit during development — PowerShell's
    `Resolve-Path` doesn't resolve macOS's `/var` → `/private/var` the way
    git's internal realpath handling does, which produced a false
    negative for a legitimate self-checkout under a symlinked temp path.)
  - no own `.git` → copy path, unchanged from before this fix (the release
    tarball or the Homebrew `libexec` copy, ADR-007 case; also covers a
    bare copy of this distribution — no `.git` of its own — dropped
    underneath an unrelated ancestor checkout, which a plain
    `rev-parse --git-dir` walk-up would otherwise misclassify as that
    ancestor's repo).

  Preflight validation — the check that runs before any mutation, so
  `--dry-run` can report pass/fail without touching disk — validates the
  tree that will actually be installed, not always the raw working
  directory: in git mode that means archiving and validating the captured
  commit (the same commit staging will use), so an uncommitted local edit
  or deletion under the working tree never blocks installing a perfectly
  valid committed tree, while a file genuinely missing from the committed
  tree is still caught before any mutation. `install.sh`'s `.git`
  detection also recognizes a dangling `.git` symlink — a plain `-e` check
  follows the link and reports false when its target is missing, which
  would otherwise read as "no git metadata at all" and silently take the
  copy path (`install.ps1`'s `Test-Path` already reported a dangling
  symlink as present, so it needed no equivalent fix).

  Both installers print the commit staged from (`Installed from commit
  <sha>`) or, for the no-git case, `Installed from: no git metadata
  (tarball install)`. `tests/test-install.sh` gained cases for: a dirty
  checkout (uncommitted edit plus an ignored file both excluded), the
  converse — an uncommitted deletion of a required file not blocking
  install of the valid committed tree — and its own converse — a file
  actually missing from the committed tree still being rejected — a
  dangling `.git` symlink (aborts, installs nothing), a no-`.git` source
  (copy path, tarball provenance), a source with no `.git` of its own
  nested underneath an unrelated ancestor checkout (copy path, not
  misclassified as the ancestor's repo), a git checkout with the `git`
  binary unavailable (aborts, installs nothing), a git checkout with `tar`
  unavailable (aborts, installs nothing), a clean checkout (installed tree
  diffed byte-for-byte against `git archive HEAD -- skills/dev`, commit
  provenance reported), and a static guard that the archive call in
  `install.sh` pins the captured commit rather than `HEAD`.
  `tests/test-install.ps1` mirrors all of these except the tree-diff
  comparison, which has no direct PowerShell equivalent in this suite — a
  recorded sh/ps1 asymmetry (the dangling-symlink case is bash-only, since
  `install.ps1` never had that gap) — and additionally asserts the exact
  error text for both the missing-git and missing-tar aborts. Fixture
  commits in both suites (the unrelated-ancestor-repo and
  committed-missing-file cases) pass an explicit
  `-c user.name=test -c user.email=test@example.com` so they stay hermetic
  on a CI runner with no git identity configured, rather than failing with
  "Please tell me who you are." The missing-tar test's scratch `PATH`
  gives `git` (and the other carried-through tools) a delegating shim
  rather than a relocated copy of the resolved executable: Git for
  Windows' `git.exe` depends on sibling directories at its real install
  location, so a copy alone broke it outright on `windows-latest` instead
  of merely hiding `tar` from it, which made that CI job misreport the
  breakage as the guard under test. The test now self-checks that the
  shimmed `git` actually runs before asserting anything, and skips with a
  stated reason rather than asserting the wrong error if it can't.
- External-review bypass no longer excuses a review invalidated by the
  author's own response to it (#33). The bypass path had become the routine
  path (4 of 4 PRs in one round) because fixing findings and pushing moves
  the head, and that self-invalidated review was read as "unavailable." The
  policy now states the bypass is only for a review that never arrived or is
  genuinely unavailable; a review the author's own commits moved past
  obligates a re-request at the new head, and the default is to wait. Where
  a bypass is still used, the recorded debt must name the exact unreviewed
  commit range, not just the PR: `<reviewed-head>..<merged-head>` when a
  review completed at that head, or `<base-head>..<merged-head>` when no
  review ever completed on the PR (there is no reviewed head to anchor the
  range, so every commit is unreviewed). The Phase 5 retro now reports the
  count of external-review bypasses per round
  (`0` reported explicitly) so repeated bypass is visible as a pattern
  rather than only per-PR. `validate_skill.py` and the doc-assertion test
  suite pin the new load-bearing sentences.
- Closed two test-coverage gaps found after PR #30 merged (#31, #25). The
  recorded-gate coverage test now rejects an indented Markdown continuation
  line under a `## Verification Gate` bullet by name instead of silently
  skipping it, so a wrapped gate command cannot go invisible to the drift
  check again; `PROJECT_CONTEXT.md` already complies, so no gate content
  changed. `test_external_review_inspector.py` now exercises the live
  `fetch_threads` GraphQL fetch path directly against a stubbed `run_json` —
  no network access — covering outer-page pagination, the query's required
  `pageInfo{hasNextPage}` and `state` fields, the nested full-page
  `InspectionError`, and the comment `state` field reaching the
  submitted-state gate. Previously every test reached `inspect()` only
  through a loaded fixture, so `fetch_threads` returning `[]` left all 40
  tests green.

## v2.1.0 — 2026-09-11

### Added

- Adapter-layer report-back enforcement (#3, PR #32). Assignments carry the
  seven-section contract; observation checks the correlated reply and records
  incomplete reports with the termination and evidence-derived cause.
- Local, Git-excluded `.dev.json` project configuration (#19, PR #36). Confirmed
  account, push repository, PR repository, and remote are checked before supported
  writes using existing credential stores. Independent-fork and upstream-contributor
  presets keep task Issues and pushes on the fork while allowing a separately
  confirmed PR destination. Every documented resolver call selects its project or
  worktree explicitly. Checks validate all push URLs, transport and CLI accounts,
  assigned branches and refspecs, and a push dry run; ambiguity stops the workflow.
- Committed Verification Gate (#22), role-prompt completion and code-minimalism
  discipline (#20), CI workflow (#6), and plugin-root/version-sync guards (#5).

### Changed

- External-review evidence must apply to the current head; green status checks
  do not constitute reviews (#16). Current-head requested changes block (#27).
- Bounded review recovery (PR #35): authorized rate-limit retries at 15 and 30
  minutes, decision at 45, with deadlines retained across pushes and substantive
  responses inspected before retrying. Corrections receive focused review while
  retaining independent lanes and the full final gate; there is no implicit bypass.
- Restored model invocation for explicit dev-workflow requests (PR #18).

### Documentation

- ADR-010 supersedes ADR-008's rejected credential-boundary plan with the shipped
  verification scope. ADR-009 retains the authorship-lint classification; its
  unshipped follow-ups remain debt (#17, #38).
- Recorded the completed iteration, outstanding limitations, and planned controlled
  real-world test. Updated Phase 5 retro guidance and installer/detector documentation.

### Known limitations

- Live SSH account verification remains unexercised (#37); unsupported or
  unavailable identities fail closed. Local and mocked tests are not live SSH proof.
- Pre-write verification covers the supported workflow, not containment of arbitrary
  commands. No GitHub App, replacement credential store, or SSH rewrite is required.
- Review timing is an operational default, not a vendor quota guarantee. Live
  requests encountered rate limits during dogfooding; the user adjusted the final
  retry schedule. This does not prove autonomous adherence in a fresh plugin session.
- A green reviewer check or acknowledgement is not review evidence. Non-default
  PR bases can skip automatic review, and substantive comments may arrive without
  a formal review event. PR #36 landed with explicit user acceptance of its clean
  current-head substantive review plus the preceding formal approval.
- Fresh-session model selection and the post-tag installation check remain pending.
  Existing sessions need to reload the plugin to pick up changed instructions.

### Upstream

Base unchanged: `2.1.0+upstream.3e87db0`; no new upstream source incorporated.

## v2.0.1 — 2026-08-31

### Fixed

- Plugin install no longer requires a GitHub SSH key. The marketplace entry now
  uses `source: "url"` with an explicit `https://` URL. A `source: "github"`
  entry made `claude plugin install` clone `git@github.com:` with no fallback,
  failing `Permission denied (publickey)` on any machine without an SSH key —
  even though `claude plugin marketplace add` falls back to HTTPS and succeeds,
  and even with an authenticated `gh`. Found by running the release verification
  against the live `v2.0.0` tag.
- Reverted an inaccurate documentation change that presented SSH as a blanket
  requirement for `claude plugin` and directed users to generate a key they do
  not need.

### Note

`v2.0.0` is left in place rather than moved, per the immutability rule in
`docs/RELEASING.md`. Anyone who installed it should update to `v2.0.1`.

## v2.0.0 — 2026-08-30

### Added

- Claude Code plugin distribution: `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`, installable with
  `/plugin marketplace add KHAEntertainment/claude-dev-skill` followed by
  `/plugin install dev-skill@khaentertainment-dev-skill`, invoked as
  `/dev-skill:dev`. The marketplace entry pins an explicit tag so releases
  are deliberate rather than tracking `main`.
- `skill_dir` field in the execution record of `DEV_STATE_TEMPLATE.md`,
  recording the resolved absolute `${CLAUDE_SKILL_DIR}` used for dispatch.
- Canonical provider-neutral report-back contract (`agents/report-back.md`)
  shared by worker, QA, reviewer, and prototype prompts.
- Provider-independent execution adapter contract with Claude-native and Traycer adapters.
- Deterministic environment-only backend detection with incomplete-session fail-closed behavior.
- Traycer worktree, Chat-agent, route-resolution, A2A messaging, observation, recovery, stop, and archive contracts through `rtk proxy traycer`.
- Provider-neutral independent reviewer prompt and YAML-front-matter `DEV_STATE_TEMPLATE.md`.
- Optional per-role Execution Routing Policy with project, workspace guide, global guide, and lead-route precedence.

### Changed

- Version scheme moved from `custom-vX.Y.Z-upstream.SHA` to plain semver with
  build metadata (`2.0.0+upstream.3e87db0`), so the value is parseable by
  ordinary tooling. The Skill value and the manifests are not byte-identical:
  they share the same core version, the part before `+`. Comparison strips build
  metadata.
- Dispatch now requires the lead to resolve `${CLAUDE_SKILL_DIR}` to an
  absolute path and substitute it into pasted worker, QA, and reviewer
  prompts. Dispatched agents do not inherit the variable, so an
  unsubstituted reference reached the delegate as unexpandable literal text.
  The defect predates plugin packaging; plugin installation makes it worse by
  placing the Skill at a version-stamped path.
- Record the project's Verification Gate in `PROJECT_CONTEXT.md` and have
  Phase 4 run it in place of the inline language defaults.
- Separate serial/parallel topology from backend selection throughout Phase 1, Phase 3, QA, review, and cleanup.
- Make worker, prototype, QA, and reviewer dispatch provider-neutral while retaining Agent Teams for Claude-native parallel execution.
- Preserve one canonical Claude Code Skill; Traycer-managed child harnesses consume assignments and do not require duplicate `/dev` installations.

### Upstream

- No new upstream merges. Base remains `3e87db0`.

## custom-v1.1.0-upstream.3e87db0 — 2026-08-29

### Added

- Conditional external-review oversight for CodeRabbit, Kilo Code, and GitHub Copilot.
- Current-head review-thread normalization, trusted-review inference from five recent PRs, explicit finding dispositions, and incomplete-evidence fail-closed behavior.
- Per-project trusted/required/ignored reviewer policy, configurable wait duration, explicit paid-review approval, and recorded timeout bypass debt.
- Fixture-testable GitHub review inspector distributed with the Skill.

### Changed

- Run external review concurrently with internal QA/review, then reconcile it before the final rating.
- Invalidate stale external review after every new PR head commit.
- Clarify that in-process Agent Teams do not require tmux or iTerm.

## custom-v1.0.0-upstream.3e87db0 — 2026-08-26

### Added

- Canonical user-invoked personal Skill at `skills/dev/`.
- RTK-first command and compact-output policy.
- `.agent/dev-state.md` recovery contract.
- Agent Team versus single-worker selection.
- Lead-prepared worktree/branch verification and explicit file ownership.
- QA, security, performance, and test-review specialist lanes.
- English translations of upstream's Chinese-only Phase 3.5, Phase 4, QA, worker, bootstrap, and Phase 5 behavior.
- English-only staged installer with dry-run, custom targets, preflight validation, legacy backup/migration, rollback, and failure injection tests.
- Static Skill reference validator and isolated installer test suite.

### Changed

- Allow the lead to maintain tracked planning/context documents while preserving the prohibition on direct implementation/test edits.
- Adapt Chinese lightweight, review auto-fix, and debt-deletion behavior to worker-owned Issue/worktree/PR flows.
- Use current Agent Teams lifecycle language: graceful teammate shutdown followed by lead cleanup.
- Treat tmux/iTerm as optional split-pane dependencies, not Agent Teams prerequisites.

### Upstream

- Reconstructed customization from base `3abcd9a75d3032e12a499afb464b56695a424cb9`.
- Merged upstream `3e87db0c71ff51ad19c932a6849777e66398f556`.
