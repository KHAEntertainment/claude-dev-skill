# Phase 5 — Retro & Technical-Debt Sweep

Trigger after all iteration PRs are merged. Complete the retro before the debt sweep; skip neither step.

---

## Step 1 — Retro

Produce:

```
## Retro — [Project] / [Iteration]
### Completed
### Known Issues
### Deferred
### Recommended Next Priorities
```

Update the current-status section of `PROJECT_CONTEXT.md` and the completed list in `docs/feature-log.md`. After repository initialization, make these tracked documentation changes in a docs-only worktree and PR; never push directly to main.

## Step 2 — Focused Debt Sweep

Limit the scan to directories changed in this iteration and their immediate callers/dependencies. Do not run an unbounded whole-repository sweep.

### Dead documentation

- Identify documents whose referenced feature or module no longer exists.
- Delete provably dead documents or update still-useful documents with `Last verified: YYYY-MM-DD`.
- When uncertain, record the item in the technical-debt section of `docs/feature-log.md`; do not present a guess as verified.
- Apply tracked document cleanup only through the docs-only worktree/PR path.

### Deprecated implementation

Inspect changed implementation files for:

```
□ Commented-out code blocks of at least three lines
□ Functions/classes with no callers after repository-wide reference verification
□ Fully resolved feature flags with constant branches
□ TODO/FIXME markers that are already resolved or need a follow-up Issue
```

The Tech Lead must not delete or edit implementation/test code. Create a narrowly scoped cleanup Issue, prepare a verified worker worktree, and dispatch `worker-fix.md`. Require tests and a cleanup PR before merge.

### Known broken features outside the iteration

Register them in `docs/feature-log.md` using:

`[Description] (source: PR #N, recorded: YYYY-MM-DD, target: next iteration/TBD)`

Do not delete untested implementation outside the iteration scope.

## Step 3 — Report

```
## Technical-Debt Sweep — [Iteration]

### Removed through merged PRs
### Updated through merged PRs
### Newly registered debt
### Skipped and why
```

## Step 4 — Cleanup and Standby

If Agent Teams were used, ask each teammate to shut down gracefully. Once none remain active, have the lead clean up the team and clear or archive the active-team section of `.agent/dev-state.md`.

Then report that the project is on standby and route the next request back through Phase 0.
