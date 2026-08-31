# Customized Distribution Changelog

Release tags follow plain semver (`vX.Y.Z`) starting at `v2.0.0`. Upstream
occupies `v1.0.0`–`v1.3.0` in this repository's history and continues to
publish on that line, so the fork's releases begin at 2.x to stay
collision-free. Upstream provenance is retained as semver build metadata in
`skills/dev/SKILL.md` (`2.0.0+upstream.3e87db0`) and in the `### Upstream`
block of each entry below.

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
  ordinary tooling and can be shared verbatim with the plugin manifests.
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
