# Phase 4 — Code Review & Merge

---

## Command Output Rules

- Use `rtk gh ...` for PR review, PR merge, PR list, PR diff, and Issue operations, and scope every one of them with `--repo OWNER/REPO` from `repository.canonical` in `.agent/dev-state.md`. Merging and reviewing are the highest-cost operations to run against the wrong repository; never let the configured `gh` default choose the target. Confirm `repository.identity_status` is `ready` before the first GitHub command of this phase.
- Use compact fields for broad PR scans. Do not request PR bodies, comments, commits, files, or reviews unless reviewing exactly one PR.
- Use `rtk git ...`, `rtk diff`, `rtk test`, `rtk lint`, `rtk npm`, `rtk go`, `rtk pytest`, or equivalent RTK wrappers for local checks.
- If an exact wrapper is unavailable, use `rtk proxy <command> ...`.

---

## Pre-Review Preparation

Before starting Review, read `PROJECT_CONTEXT.md` for code style conventions, architecture decisions, and the optional External Review Policy. Read `${CLAUDE_SKILL_DIR}/phases/external-review.md`; its observation should already be running from Phase 3.5.

For large or risky PRs, the Tech Lead may use parallel topology through the selected adapter for focused review lanes before making the final rating:
- `review-security`: security implications, secrets, auth, injection, unsafe shell/database calls
- `review-performance`: obvious performance regressions, query loops, concurrency risks
- `review-tests`: acceptance criteria coverage, regression coverage, test output quality

Review agents are advisory only. They must report findings to the Tech Lead and leave PR comments when instructed, but the Tech Lead owns APPROVE / REQUEST CHANGES / COMMENT and all merge decisions.

Before any independent review, load `${CLAUDE_SKILL_DIR}/agents/reviewer.md`. Require a reviewer agent ID distinct from implementation/fix workers and the QA agent, no implementation ownership, the recorded current `headRefOid`, and clean worktree evidence before and after review.

---

## Step 0 — Scope-Drift Gate

Run `rtk gh pr diff [PR-number] --repo OWNER/REPO --name-only` before any checklist.

- Files clearly outside the Issue and ownership map → mark Scope Drift and REQUEST CHANGES; require the worker to revert unrelated changes.
- Missing files or behavior required by an acceptance criterion → record a completeness failure.
- Scope matches → continue.

The Tech Lead may directly correct review/planning documentation only in a docs-only or related PR. Never directly fix implementation/test code while reviewing.

---

## Static Analysis Gate (run before human review)

Run the project's **Verification Gate** recorded in `PROJECT_CONTEXT.md` when
present; otherwise run these defaults:
- Python: `rtk proxy flake8` / `rtk proxy pylint` / `rtk mypy`; security scan: `rtk proxy bandit -r .` (if not installed: ask before installing, then use `rtk pip install bandit`)
- JavaScript: `rtk lint` or `rtk npx eslint`

**Dependency vulnerability scan (mandatory):**
- Python: `rtk proxy pip-audit` (if not installed: ask before installing, then use `rtk pip install pip-audit`)
- Node.js: `rtk npm audit`

If static analysis reports significant errors (not nitpicks), send back to Worker Agent for fixes — do not proceed to human review.
If the dependency scans find High or Critical vulnerabilities, also send back and require dependency upgrades.

---

## Two-Pass Review

Classify each finding as:

- **DELEGATE-FIX**: the fix is clear, but must be performed by a Worker Agent in its assigned worktree.
- **ASK**: intent, interface semantics, permissions, or tradeoffs are unclear; batch these questions for the user or worker.

### Pass 1 — Critical (any unresolved failure blocks merge)

```
□ Scope Drift
  Verify modified files against the Issue and ownership map.

□ SQL and shell safety
  Reject concatenated SQL/shell input, unsafe eval, or unparameterized raw queries.

□ Secrets and sensitive logging
  Reject hardcoded credentials/tokens or logging of secrets.

□ Authentication/authorization boundaries
  Verify every new entry point enforces the intended identity and permission rules; ASK when intent is unclear.

□ Race conditions and side effects
  Trace concurrent calls to state-changing functions; ASK when locking/atomicity requirements are unclear.

□ Feature completeness
  Map every acceptance criterion to implementation evidence.

□ Error handling
  Trace DB/API/file failures; DELEGATE-FIX obvious omissions and ASK when failure semantics are ambiguous.

□ Tests and migrations
  Block when the project has a test framework but the new behavior has no tests, or when schema changes bypass the approved migration framework/rollback path.
```

### Pass 2 — Informational (record unless it exposes a Pass 1 defect)

```
□ Coverage gaps on non-critical paths
□ Magic numbers and configuration hardcoding
□ Dead code and unused imports
□ N+1 queries, looped I/O, or other performance smells
□ Style consistency with PROJECT_CONTEXT.md
□ Migration downgrade quality
```

Use `rtk gh pr review [PR-number] --repo OWNER/REPO` for concrete findings. Batch ASK items rather than interrupting one at a time.

## Coverage-Path Audit

Trace each changed entry point and show which paths have executed tests versus static evidence:

```
Coverage Audit — [PR title]
changed: src/auth.py

  register()
    ├── valid input → 201             [executed test]
    ├── duplicate email → 409         [executed test]
    ├── invalid format → 400          [missing test]
    └── database unavailable → 500    [static evidence only]
```

- Missing Critical-path tests block when a test framework exists.
- Missing non-critical paths are Pass 2 findings unless they reveal an acceptance-criteria gap.

## Adversarial Second Opinion

Trigger a focused read-only reviewer when any ASK finding remains. Give it only the uncertain findings and relevant diff sections. Require an independent judgment on whether the issue is real, its severity, and the recommended resolution. Skip this step when all findings are clearly passed or DELEGATE-FIX.

Launch and observe it through the selected adapter. If its identity, route, response correlation, target head, or clean-worktree result cannot be verified, mark internal review `incomplete` and do not merge.

---

## Review Rating

Before assigning a rating, rerun the external-review inspector, triage every active current-head trusted-reviewer finding, and verify that the PR's current `headRefOid` still matches `.agent/dev-state.md`.

If the head changed, invalidate QA, internal review, and external-review completion, update the ledger, and rerun Phase 3.5 and Phase 4 against the new commit.

- `blocking` external review → REQUEST CHANGES.
- `pending` or `incomplete` external review → do not merge; follow the explicit waiting/approval choices in the external-review gate.
- `clear` or `not_applicable` → continue to the internal rating below. This is not a substitute for the internal checklist.

Must give one explicit rating:

- **APPROVE**: Pass 1 is clear, all DELEGATE-FIX findings are resolved, external review is `clear` or `not_applicable`, and only non-blocking Pass 2 findings remain
  → `rtk gh pr merge [PR-number] --repo OWNER/REPO --squash`, then close the corresponding Issue with `rtk gh issue close [N] --repo OWNER/REPO`

- **REQUEST CHANGES**: any Pass 1 failure, confirmed Scope Drift, or unresolved ASK item
  → list each issue and expected fix in comments
  → re-dispatch Worker Agent to make changes
  → **after fixes, must re-run Phase 3.5 (QA) + Phase 4 (Review) — never skip**

- **COMMENT**: questions that don't block the merge (decide after user confirmation)

---

## Merge Order

Merge in dependency order: infrastructure Issue PRs merge first; dependent PRs wait until prerequisites are merged.

Update `PROJECT_CONTEXT.md` after all PRs are merged through a docs-only worktree/PR (completed features list, current status).

---

## Post-Merge: Affected PR Coordination (mandatory after every merge)

After a PR is merged into main, immediately:

1. `rtk gh pr list --repo OWNER/REPO --state open --json number,title,headRefName,updatedAt --jq '.[] | "#\(.number) \(.headRefName) — \(.title)"'` — list open PRs compactly
2. Compare this merge's file list against each open PR's modified files (`rtk gh pr diff <PR-number> --repo OWNER/REPO --name-only`). Check one PR at a time; do not dump all diffs into the conversation.
3. Open PRs with file overlap → comment: `This PR overlaps files with the just-merged #N. Please rebase: rtk git fetch origin && rtk proxy git rebase origin/main`
4. Open PRs with logical dependencies (e.g. this refactor changed module paths or interface signatures) → notify those PRs as well
