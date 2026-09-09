# Execution Backend Adapter Contract

The Tech Lead selects `topology` (`serial` or `parallel`) independently from `execution_backend` (`claude-native`, `traycer`, or `incomplete`). Backend selection is deterministic; topology never changes it.

Run `${CLAUDE_SKILL_DIR}/scripts/detect_execution_backend.py` before dispatch. Treat exit status 2 or backend `incomplete` as a pause condition. The detector returns `traycer` only when both `TRAYCER_AGENT_ID` and `TRAYCER_EPIC_ID` are present and otherwise fails closed to `incomplete`; `claude-native` is selected by the lead for a known native Claude Code session, never inferred from absent identifiers. To discharge the pause as `claude-native`, the lead must have positive evidence the session is native Claude Code (the lead is running `/dev` directly in Claude Code, not through Traycer) and record `backend_source: lead_resolved` in the ledger; a detector-chosen `traycer` records `backend_source: detected`. Never use binary presence, model availability, or a failed Traycer preflight to select or fall back to another backend.

Each adapter must implement these operations and either return verified state for the ledger or fail closed:

| Operation | Required verified result |
|---|---|
| `preflight` | Backend identity, host/auth/capability status, and usable launch surfaces |
| `prepare_worktree` | Absolute source and worker paths, assigned branch, base OID, and clean status |
| `resolve_route` | Harness, model, profile behavior/source, reasoning effort, and permission mode |
| `launch` | Distinct agent identity, role, Issue/lane, exact worktree binding, and ownership |
| `message` | Assignment payload — including the report-back contract — and backend response/correlation ID |
| `observe` | Agent state, complete cursor-aware replies/transcript evidence, and a report-back shape verdict |
| `shutdown` | Graceful stop result; archive result when requested |
| `recover` | Reconciled live state from `.agent/dev-state.md` without duplicating agents |

## Common invariants

- **Resolve `${CLAUDE_SKILL_DIR}` to its absolute path and substitute it into every prompt before dispatch, in every phase.** Dispatched agents do not inherit `CLAUDE_SKILL_DIR`, so an unsubstituted reference reaches the delegate as literal text it cannot expand. This applies to every lane that pastes prompt content — prototype, worker, QA, and reviewer alike — and to the assignment envelope itself. Record the resolved value as `skill_dir` in `.agent/dev-state.md` and re-resolve it at the start of each run rather than trusting a stored value; the path changes when the Skill is reinstalled, and it is version-stamped when the Skill is installed as a plugin.
- The lead never modifies implementation or test code.
- Every coding agent receives a pre-created, verified branch/worktree and explicit ownership.
- GitHub Issues and PRs are canonical; backend task lists are runtime coordination only.
- Worker → PR → QA → Review is unchanged for both adapters.
- QA and review are distinct, one-shot read-only SOP roles. They receive no implementation ownership and must leave zero tracked changes.
- The reviewer and QA must have agent IDs distinct from each other and from every implementation worker; the reviewer reviews the recorded current `headRefOid`.
- A new push invalidates QA, internal review, and external-review evidence for the prior head.
- RTK-first command rules apply everywhere. Traycer CLI calls use `rtk proxy traycer`.
- Record every transition in `.agent/dev-state.md`; the lead is its sole writer.

## Provider-neutral assignment envelope

Every backend sends the full role prompt plus: role, Issue or review lane, topology, backend, route and route source, branch, absolute worktree, base OID, target `headRefOid` when applicable, ownership, acceptance criteria, plan-approval requirement, RTK rules, reporting channel, the report-back contract from `${CLAUDE_SKILL_DIR}/agents/report-back.md`, and stop condition.

The assignment must not depend on Claude-specific tool names. Native packaging for a non-Claude lead may reuse this contract later; it is not required for Codex, OpenCode, Cursor, or smaller harnesses to serve as Traycer-managed children.

## Report-back enforcement

The report-back is a defect-detection mechanism, not a courtesy. A lane that finishes silently is indistinguishable from one that crashed, and the silence hides whatever the report would have shown. `message` and `observe` therefore enforce it at the adapter layer, in every backend.

- **`message`** embeds the report-back contract from `${CLAUDE_SKILL_DIR}/agents/report-back.md` in the assignment envelope, so the receiving lane carries it as adapter payload rather than only through its role prompt.
- **`observe`** verifies the reply carries all seven required sections by name: Outputs; Commands + exit codes; Deviations; Quality-gate self-assessment; Acceptance criteria; Evidence; Scope / ownership.
- **Recognition is section-heading presence, matched case-insensitively.** A heading with no content under it is a missing section, not a present one — otherwise seven empty headings satisfy the check. Presence is judged mechanically; content is judged by the lead. The adapter never grades what a section says: a stricter parse over free-form prose produces false `incomplete` verdicts, and a check that cries wolf trains the lead to ignore it.
- A reply missing any of the seven sections is malformed adapter output. Mark the operation `incomplete`, record it in `.agent/dev-state.md`, and never infer completion. **A lane that never replied at all is the same verdict, not a lesser case.** Absence of a report is not a report.
- **The verdict never varies; the recorded cause does.** Record `report_back: incomplete` with cause `absent` (no reply arrived), `malformed` (a reply arrived without every section), or `truncated` (pagination exhausted and the transport still declares the reply incomplete). The verdict is identical because all three leave the lane unverified. The cause differs because the remedy does: `absent` questions whether the lane is alive at all and is answered by inspecting live state before re-requesting or replacing the lane; `malformed` comes from a demonstrably alive lane and is answered by re-requesting the shape at the recorded response ID; `truncated` is re-read before it is re-requested, because the missing sections may already exist upstream of the cut.
- **Judge shape only after the reply is complete per the transport's own completion signal.** Consume every cursor/page first. Calling a first page malformed manufactures a lane defect out of pagination.
- Role-specific close-outs in `${CLAUDE_SKILL_DIR}/agents/report-back.md` are additive and never substitute for the seven required sections. A QA lane that posts its PR-comment template and replies nothing has not reported.
