# Report-Back Contract

Every delegated lane ends by reporting back to the Tech Lead through the active
backend's messaging surface. A report-back is a fixed list, never freeform
prose, so the lead can verify completion mechanically and never infer it from
silence.

## Delivery

- Send the report-back through the same backend surface the assignment arrived on.
- Include the backend correlation/response ID recorded by the adapter when one
  was provided. A missing or mismatched correlation ID fails the lane closed.
- Read-only lanes (QA, reviewer) must also confirm they left zero tracked changes.
- This contract is enforced by the adapter, not only by this prompt. The
  assignment envelope carries it, and `observe` marks the operation `incomplete`
  when a reply is missing sections or never arrives. See the report-back
  enforcement section of `${CLAUDE_SKILL_DIR}/backends/contract.md`.

## Required sections (all lanes)

1. **Outputs** — files changed/created, PR URL, artifact + readout paths, or a
   finding list.
2. **Commands + exit codes** — every verification/gate command run, with its
   exit code.
3. **Deviations** — anything outside the assignment or assigned ownership;
   write `none` when clean.
4. **Quality-gate self-assessment** — syntax / types / lint / tests, each
   `pass` / `fail` / `n/a`.
5. **Acceptance criteria** — each criterion restated as
   `[trigger] → [behavior]`, marked ✓/✗ with a one-line result.
6. **Evidence** — the commit `headRefOid` (or local `HEAD`) the lane ran
   against, plus clean-worktree evidence for read-only lanes.
7. **Scope / ownership** — confirm no file outside assigned ownership was
   modified; list any exception and its reason.

A report-back with a missing section is flagged, not back-filled; never invent
evidence.

## Evidence discipline

- Every completion claim maps to an executed command's actual output. If you
  cannot name the command and what it printed, do not make the claim — record
  what was not run instead. An unrun check is reported as unrun, never omitted.
- After any fix, re-run the full Verification Gate rather than only the check
  that failed. A targeted re-run shows the one symptom went away; it does not
  show the fix left everything else intact.
- Every exit code you report comes from that final full run, at the head commit
  you report. Never carry an exit code forward from a run that preceded the
  change, and report a partial re-run as partial.
- What counts as "verified" is defined once, in the Tool Capability Boundary of
  `${CLAUDE_SKILL_DIR}/agents/qa-agent.md`. Every lane uses that definition;
  this contract does not restate it.

## Role-specific close-out

Role-specific close-outs are additive. They
never substitute for the seven required sections: a lane that posts its
role-specific artifact — a QA PR comment, a reviewer finding list — and replies
nothing has not reported.

- **Worker** (`worker-new` / `worker-fix`): report the created PR URL and the
  exact head commit, then stop and wait for review or shutdown.
- **QA** (`qa-agent`): use the QA report template as the role-specific form of
  the contract and finish with `QA ✓ Health: [N]/100`; a failing lane still
  reports its evidence and stops.
- **Reviewer** (`reviewer`): repeat the correlation ID, the reviewed commit,
  and clean-worktree evidence; classify findings `blocking` / `advisory` /
  `question` / `clear`.
- **Prototype** (`worker-prototype-*`): report the artifact + readout paths and
  the decision point answered; do not restate the full readout.

A change to `headRefOid` marks the new head pending and requires fresh review
results. Approval from the previous head does not apply to the new head; retain
the prior report-back only as historical evidence. A correction review issues a fresh report under **Review after
fixes** in `${CLAUDE_SKILL_DIR}/phases/phase4.md`, naming the reviewed base, target
head, scope, executed checks and remaining findings.
