# External Review Oversight Gate

Use trusted third-party review as an independent signal. It supplements the internal QA, specialist lanes, and Tech Lead review; it never replaces them.

## Default Policy

Unless `PROJECT_CONTEXT.md` overrides the policy:

- Mode: `auto`
- Trusted reviewers: `coderabbit`, `kilo`, `github-copilot`
- Required reviewers: none
- Ignored reviewers: none
- Default wait: 10 minutes
- Allow automatic review requests: `false`

Known identities include CodeRabbit review/check identities, Kilo Code review/check identities, and GitHub Copilot's API request identity `copilot-pull-request-reviewer[bot]`. GitHub review authorship may surface the same account as `copilot-pull-request-reviewer` without the suffix; both map to `github-copilot`. The `@copilot` name is only a request alias. Do not treat generic Copilot coding-agent activity as code-review evidence.

An ignored reviewer overrides every default, required, or detected setting. Unknown bots are evidence to surface to the user, not trusted reviewers. Ask before adding an unknown login or check-app slug to the current repository policy.

If Mode is `off`, record that external review was disabled by repository policy and treat the gate as `not_applicable` without running the inspector. Internal QA and review still run.

## Start Observation in Phase 3.5

After resolving the PR's operation target (`rtk proxy python3 "${CLAUDE_SKILL_DIR}/scripts/resolve_repository.py" --repo-dir "<selected-worktree>" --operation pr --target <github.pullRequestRepository>` per `${CLAUDE_SKILL_DIR}/phases/repository-context.md`) and its branch, resolve its exact head commit:

```bash
rtk gh pr view [N] --repo github.com/<confirmed pullRequestRepository> --json headRefName,headRefOid --jq '{branch: .headRefName, head: .headRefOid}'
```

Record the PR number, `headRefOid`, expected/requested/observed reviewers, the default deadline, and the next observation time in `.agent/dev-state.md`. Begin the deadline when this state is written. Continue internal QA and review while external reviewers work.

## Inspect One PR

Run the deterministic inspector from the target repository:

```bash
rtk proxy python3 "${CLAUDE_SKILL_DIR}/scripts/inspect_external_reviews.py" --repo OWNER/REPO --pr N --payload-snapshot NEW_SNAPSHOT_PATH
```

For every gate run, including disposition reruns, the lead supplies a new snapshot path and records it in `external_review_payload_snapshots` in `.agent/dev-state.md`, together with the observation timestamp and `headRefOid`. The inspector writes the verbatim current-PR JSON it actually parses before deriving a verdict. Existing files are never overwritten; a persistence failure is `incomplete`. Create the parent directory first. Preserve the raw file unchanged: do not summarise, diff, or interpret it in place. The snapshot includes the fields from `gh pr view N --repo github.com/OWNER/REPO --json statusCheckRollup,reviews,latestReviews,comments`, plus the PR number, head, and review requests needed by the inspector. Record retrieval failures as failures, never as an empty successful snapshot. Thread evidence and recent-PR inference are separate from this current-PR snapshot.

Translate the External Review Policy from `PROJECT_CONTEXT.md` into arguments:

- `Trusted reviewers` → repeat `--trusted-reviewer NAME`; omit these arguments only when using all three defaults
- `Required reviewers` → repeat `--required-reviewer NAME`
- `Ignored reviewers` → repeat `--ignored-reviewer NAME`
- `Additional reviewer identities` → repeat `--identity NAME=LOGIN[,CHECK-APP-SLUG]`; also include `NAME` as a trusted reviewer

A required reviewer must also be trusted and have an identity mapping. Invalid policy is `incomplete`; do not silently widen or weaken trust.

The helper deep-reads only the target PR. For inference, it lists a maximum of five recent PR numbers and inspects them one at a time. It paginates target-PR review threads and emits compact JSON with one state:

- `not_applicable`: no trusted reviewer is configured or detected
- `pending`: an expected reviewer has not completed on the current head, or a current finding still needs a Tech Lead disposition
- `clear`: every expected reviewer is current and every active finding has a non-blocking disposition
- `blocking`: at least one active current-head finding is classified as blocking
- `incomplete`: permissions, pagination, malformed data, or a failed check without readable findings prevented a reliable decision

A trusted reviewer's status check alone never satisfies this gate.
A submitted review that requests changes at the current head is `blocking`; review evidence alone never establishes satisfaction. A green check without a submitted current-head review or a review-thread comment at head is `pending`. Status checks still inform pending and failed states; they never establish review completion or erase stale reviews. A reviewer without a published check can complete through review evidence, as with Copilot. `check_only_reviewers` and `pending_reasons` name reviewers whose checks completed without current-head review evidence. `parked_comments` reports their PR-level comment existence and URLs only; it does not establish a cause or count as review evidence. Never infer parked status from vendor wording or regex comment bodies.

Never reinterpret `incomplete` as no reviewers. Required branch-protection checks remain hard gates independently of this helper.

Active finding bodies are capped at 2,000 characters and inactive findings omit their bodies. Use `--max-body-chars N` (200–20,000) only when the truncated context is insufficient; prefer opening the single finding URL over expanding every result.

## Triage Current-Head Findings

Only active findings participate in the gate. Resolved, outdated, minimized/hidden, or old-head threads do not block.

Classify every active finding:

- `blocking`: correctness, security, authorization, test, migration, acceptance-criteria, or serious performance defect. Convert it to `DELEGATE-FIX` when the resolution is clear or `ASK` when intent is ambiguous.
- `advisory`: style, wording, optional refactor, or other non-blocking improvement.
- `false_positive`: not applicable or factually incorrect; record a concise evidence-based rationale.

Write a temporary JSON object mapping finding IDs to `blocking`, `advisory`, or `false_positive`, rerun the inspector with `--dispositions PATH`, and copy the results and rationale into `.agent/dev-state.md`. The temporary file is runtime state, never a tracked project artifact.

GitHub Copilot always leaves comment reviews rather than APPROVED or CHANGES_REQUESTED reviews. Never use its review state to clear the gate; triage its current-head threads directly.

## Head-Commit Invariant

Immediately before the final Phase 4 rating, query `headRefOid` again. If it differs from the recorded value:

1. Reset QA, internal review, and external-review completion to pending for the new head; retain old reports as historical evidence.
2. Update `.agent/dev-state.md` with the new head. Carry any unfinished wait episode's deadline and remaining retry budget forward.
3. Run Phase 3.5 and Phase 4 using **Review after fixes** in `${CLAUDE_SKILL_DIR}/phases/phase4.md`, including a fresh run of this gate.

Copilot does not necessarily re-review new pushes unless the repository enables **Review new pushes**. A stale Copilot review is `pending`, never `clear`.

## Waiting and Explicit Decisions

Observe a pending review through the selected backend. Continue independent work
permitted by the existing dependencies and ownership map; a blocked merge does
not block unrelated work or change the approved merge order. When nothing useful
can proceed, record the next wake/action and yield. Use a scheduled wake when the
backend supports it; otherwise report the due time for the next observation.
Do not hold an active turn open for the wait. During active work, keep the user
updated at least every 60 seconds.

A bypass is only for a review that never arrived or is unavailable. It is never for a review that arrived and was invalidated by the author's own response to it: fixing findings and pushing moves the head, and per the Head-Commit Invariant above that obligates a re-request at the new head, not a bypass. The default is to wait for that re-request, using the deadlines and bounded-wait machinery already defined in this file. When a review did complete before the fix commits, the unreviewed range is `<reviewed-head>..<merged-head>`; when no review ever completed on the PR, there is no reviewed head to anchor that range, and every commit is unreviewed, so the range is `<base-head>..<merged-head>` instead.

### Rate-limited review retries

Use this bounded path only after an explicit rate-limit response to a request
and only when repository policy or explicit approval authorizes re-requesting
that specific reviewer. One lead owns retries for each PR/reviewer.

Before scheduling or sending a retry, read submitted reviews, review threads,
and substantive PR comments, including those at earlier heads whose findings
may still apply. A substantive response ends this wait episode for triage and
cancels redundant retries; a PR comment does not itself satisfy the inspector.
Acknowledgements and green status checks are not review completion.

Measure from the unsuccessful request, not from when its status was last read:

| Elapsed from original request | Action if no substantive response |
|---|---|
| 15 minutes | First retry |
| 30 minutes | Second and final retry |
| 45 minutes | End the response window and surface the explicit deadline choices once |

There is no third automatic retry. Observe an actively progressing review
without sending a duplicate request; the deadline still applies. If a wake is
late, do not send catch-up requests: send at most one eligible retry, never less
than 15 minutes after the last request, and surface the deadline choices if the
45-minute window has expired. A terminal error can surface the choices sooner.
If the vendor specifies a later retry time, offer that longer wait explicitly;
do not retry early or silently extend the window.

This authorized rate-limit path replaces the ordinary initial wait deadline
for that episode. Other pending/unavailable cases retain the configured deadline.
The 15-minute interval is an operational default, not a vendor quota guarantee.
A status is a dated observation, not a live signal: do not wait for an old
rate-limit status to change on its own.

Record request time, target head, attempts used, next observation and deadline in
`approved_review_requests`, `review_deadline`, `next_action` and timestamped
recovery entries. Polling or an acknowledgement never resets the budget.
A push cancels the request scheduled for the old head; verify the new
`headRefOid` before requesting and carry the remaining budget and deadline
forward. After a substantive response and a later fix batch, a new episode may
start with the prior history retained. Only an explicit extension renews an
exhausted episode.

### Deadline choices

At the configured deadline, stop before merge and offer these explicit choices:

1. Wait an additional user-specified duration. Record the extension and new deadline.
2. Request or re-request a trusted review. This requires explicit approval unless `Allow automatic review requests` enables that specific reviewer; record potential credit usage.
3. Bypass only a pending or unavailable review — never one invalidated by the author's own response. Require explicit approval and record the reason, approver, timestamp, and review debt — naming the exact unreviewed commit range: `<reviewed-head>..<merged-head>` when a review completed at that head, or `<base-head>..<merged-head>` when no review ever completed on the PR — in `.agent/dev-state.md` and a PR comment.
4. Stop without merging.

Never issue CodeRabbit full-review commands, Kilo review requests, or Copilot
review/re-review requests automatically without the reviewer-specific authority
above. A timeout bypass cannot clear a known actionable finding. Such a finding
must be fixed or explicitly dispositioned as a false positive with rationale.
A current-head `CHANGES_REQUESTED` remains blocking even when its threads are
dispositioned advisory or false positive; seek reviewer follow-up rather than
silently overriding the inspector.

## Result Routing

- `not_applicable` or `clear` → continue to the final internal Review Rating.
- `pending` → continue permitted independent work, then observe, retry when authorized, or use the explicit deadline choices.
- `blocking` → REQUEST CHANGES; batch fixes and run Phase 3.5 plus Phase 4 under **Review after fixes** in `${CLAUDE_SKILL_DIR}/phases/phase4.md`.
- `incomplete` → stop and resolve the evidence failure or obtain an explicit pending-review bypass; never merge silently.
