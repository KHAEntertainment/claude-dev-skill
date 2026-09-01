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
| `message` | Assignment payload and backend response/correlation ID |
| `observe` | Agent state plus complete, cursor-aware replies/transcript evidence |
| `shutdown` | Graceful stop result; archive result when requested |
| `recover` | Reconciled live state from `.agent/dev-state.md` without duplicating agents |

## Common invariants

- **Resolve `${CLAUDE_SKILL_DIR}` to its absolute path and the canonical repository `OWNER/REPO` from the current checkout, and substitute both into every prompt before dispatch, in every phase.** Dispatched agents do not inherit `CLAUDE_SKILL_DIR`, and an unsubstituted `OWNER/REPO` reaches the delegate as a literal string it cannot interpret. This applies to every lane that pastes prompt content — prototype, worker, QA, and reviewer alike — and to the assignment envelope itself. Record the resolved values as `skill_dir` and `repository.canonical` in `.agent/dev-state.md` and re-resolve them at the start of each run rather than trusting a stored value.
- **Resolve the canonical repository before the first GitHub operation and pass it explicitly to every GitHub command.** `${CLAUDE_SKILL_DIR}/scripts/resolve_repository.py` normalizes HTTPS and SSH `origin` syntax to `OWNER/REPO` and fails closed when `origin` is missing, non-GitHub, unreadable, or disagrees with the configured `gh` default or another GitHub remote. Record the result as `repository.canonical` in `.agent/dev-state.md`, carry it in the assignment envelope, and have each delegate re-verify it with `--expect OWNER/REPO`. An unresolved or conflicting identity is a pause condition before any remote write, not a warning.
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

Every backend sends the full role prompt plus: role, canonical repository (`OWNER/REPO`), Issue or review lane, topology, backend, route and route source, branch, absolute worktree, base OID, target `headRefOid` when applicable, ownership, acceptance criteria, plan-approval requirement, RTK rules, reporting channel, and stop condition.

The canonical repository is mandatory in the envelope. A delegate that receives no canonical repository, or whose checkout resolves to a different one, reports a blocker instead of guessing.

The assignment must not depend on Claude-specific tool names. Native packaging for a non-Claude lead may reuse this contract later; it is not required for Codex, OpenCode, Cursor, or smaller harnesses to serve as Traycer-managed children.
