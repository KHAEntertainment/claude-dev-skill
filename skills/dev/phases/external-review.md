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

After resolving the PR branch, resolve its exact head commit:

```bash
rtk gh pr view [N] --json headRefName,headRefOid --jq '{branch: .headRefName, head: .headRefOid}'
```

Record the PR number, `headRefOid`, expected/requested/observed reviewers, the default deadline, and the next observation time in `.agent/dev-state.md`. Begin the deadline when this state is written. Continue internal QA and review while external reviewers work.

## Inspect One PR

Run the deterministic inspector from the target repository:

```bash
rtk proxy python3 "${CLAUDE_SKILL_DIR}/scripts/inspect_external_reviews.py" --repo OWNER/REPO --pr N
```

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

1. Invalidate all QA and external-review completion recorded for the old commit.
2. Update `.agent/dev-state.md` with the new head and deadline.
3. Re-run Phase 3.5 and the complete Phase 4, including this gate.

Copilot does not necessarily re-review new pushes unless the repository enables **Review new pushes**. A stale Copilot review is `pending`, never `clear`.

## Waiting and Explicit Decisions

Poll a pending expected review every 30 seconds while continuing safe internal review work. Do not leave the user without a progress update for more than 60 seconds.

At the configured deadline, stop before merge and offer these explicit choices:

1. Wait an additional user-specified duration. Record the extension and new deadline.
2. Request or re-request a trusted review. This requires explicit approval unless `Allow automatic review requests` enables that specific reviewer; record potential credit usage.
3. Bypass only a pending or unavailable review. Require explicit approval and record the reason, approver, timestamp, and review debt in `.agent/dev-state.md` and a PR comment.
4. Stop without merging.

Never automatically issue CodeRabbit full-review commands, Kilo review requests, or Copilot review/re-review requests. A timeout bypass cannot clear a known actionable finding. Such a finding must be fixed or explicitly dispositioned as a false positive with rationale.

## Result Routing

- `not_applicable` or `clear` → continue to the final internal Review Rating.
- `pending` → continue internal work, then poll or use the explicit deadline choices.
- `blocking` → REQUEST CHANGES, dispatch a fix worker, and rerun Phase 3.5 plus Phase 4 after the push.
- `incomplete` → stop and resolve the evidence failure or obtain an explicit pending-review bypass; never merge silently.
