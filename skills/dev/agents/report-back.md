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

## Role-specific close-out

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

A new push invalidates the report-back for the prior head.
