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
5. Resolve and launch one distinct read-only QA identity through the selected adapter. Record its agent ID and route. Do not give QA implementation ownership.
6. Record `rtk git status --short`, local `HEAD` (`rtk git rev-parse HEAD`), and the PR `headRefOid` before and after the lane. Any tracked QA change, or either head differing from the recorded target commit, fails the lane and makes the adapter result incomplete.

The Tech Lead resolves the branch before dispatch; the QA agent must not guess it.

## Result Handling

### QA passes

Require a PR comment containing `QA ✓ Health: [N]/100`, no Critical/High findings, and a passing score. Continue to Phase 4.

### QA fails

1. Read the QA report and turn each failing criterion or Critical/High finding into explicit fix instructions.
2. Re-dispatch a fix worker in the existing coding worktree when safe, or create and verify a replacement worktree when recovery is required.
3. Never rely on an `@mention` to reactivate a completed worker or QA session.
4. After fixes, invalidate QA and external-review evidence for the old head, then rerun the complete Phase 3.5 and Phase 4 sequence.

Treat QA agents as one-shot, read-only lanes: they require an unchanged checkout and an unchanged PR head and must leave zero tracked changes. They report evidence; they do not approve, merge, or modify code. A QA agent ID must differ from the implementation worker ID. A new push invalidates its result.
