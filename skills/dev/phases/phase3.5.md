# Phase 3.5 — QA Verification

---

## Quantitative Trigger

Run QA when any condition is true; otherwise record why QA was skipped and continue to Phase 4:

| Condition | QA required |
|---|---|
| Added or modified diff lines ≥ 50 | Yes |
| Modified files ≥ 3 | Yes |
| New external interface, API endpoint, or public function signature | Yes |
| Database schema change | Yes |
| Authentication or authorization logic | Yes |

Use compact diff statistics first. Do not substitute subjective judgment for these thresholds. The Tech Lead may also require QA for lower-volume but high-risk changes.

## Prepare the QA Lane

1. Resolve the exact PR head branch and commit with `rtk gh pr view [N] --json headRefName,headRefOid --jq '{branch: .headRefName, head: .headRefOid}'`.
2. Record PR number, Issue number, head branch, `headRefOid`, and target commit in `.agent/dev-state.md`.
3. Read `${CLAUDE_SKILL_DIR}/phases/external-review.md`, resolve the repository policy, start its review deadline, and record expected/requested/observed reviewers. Do not wait here; continue QA while external review proceeds.
4. Load `${CLAUDE_SKILL_DIR}/agents/qa-agent.md` and fill every placeholder before dispatch.
5. In Agent Team mode, assign one read-only QA teammate to the PR. Otherwise dispatch one read-only QA worker. Do not give QA implementation ownership.

The Tech Lead resolves the branch before dispatch; the QA agent must not guess it.

## Result Handling

### QA passes

Require a PR comment containing `QA ✓ Health: [N]/100`, no Critical/High findings, and a passing score. Continue to Phase 4.

### QA fails

1. Read the QA report and turn each failing criterion or Critical/High finding into explicit fix instructions.
2. Re-dispatch a fix worker in the existing coding worktree when safe, or create and verify a replacement worktree when recovery is required.
3. Never rely on an `@mention` to reactivate a completed worker or QA session.
4. After fixes, invalidate QA and external-review evidence for the old head, then rerun the complete Phase 3.5 and Phase 4 sequence.

Treat QA agents as one-shot, read-only lanes. They report evidence; they do not approve, merge, or modify code.
