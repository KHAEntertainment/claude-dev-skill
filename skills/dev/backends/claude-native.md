# Claude-Native Execution Adapter

Use this adapter only when the lead has resolved the session as native Claude Code. Backend detection fails closed to `incomplete` when the Traycer identifiers are absent, because that absence cannot distinguish a native Claude session from a Traycer-managed child whose environment was not injected. Resolve the pause with positive evidence that `/dev` is running directly in Claude Code (not through Traycer), and record `backend_source: lead_resolved` in the ledger; a detector-chosen `traycer` records `backend_source: detected`.

## Preflight and topology

- `serial`: dispatch one ordinary Worker Agent for one Issue/lane.
- `parallel`: create one Claude Agent Team for 2+ independent Issues or review lanes with explicit, non-overlapping ownership.
- Agent Teams run in-process; tmux/iTerm are optional display integrations, not runtime requirements.
- If the selected Claude capability is disabled or unavailable, attempt the obvious configuration correction. If it remains unavailable, mark the backend incomplete and ask. Never silently change topology or switch to Traycer.

## Adapter operations

1. **Prepare worktree:** the lead fetches the integration branch, creates one branch/worktree per coding Issue, verifies absolute path/branch/base/cleanliness, and records it before launch. Read-only roles may use a verified checkout only if they leave it clean.
2. **Resolve route:** Claude-native uses the lead's available agent/subagent configuration. Record `harness: claude-code`, the selected role/agent type, model override if any, and source `claude-native`.
3. **Launch:** parallel maps to named Agent Teams teammates; serial maps to one worker. Map every identity to exactly one Issue or QA/review lane.
4. **Message:** provide the provider-neutral assignment envelope and full role prompt. The envelope embeds the report-back contract from `${CLAUDE_SKILL_DIR}/agents/report-back.md`, so the lane holds it as adapter payload rather than only through its role prompt. Record the dispatch message/result identifier when exposed.
5. **Observe:** use the native agent/team status and message surfaces. Do not infer completion from silence; a teammate the team surface reports as finished has not reported until its sections are read. Classify in the order the report-back enforcement section of `${CLAUDE_SKILL_DIR}/backends/contract.md` sets out, which is not the order the branches are easiest to write in:
   1. **Classify `absent` before anything else.** When the read ends, ask first whether a reply from that teammate was observed at all. If none was, record `report_back: incomplete` and the read's `report_back_termination` in `.agent/dev-state.md` — the read ran, so it ended somehow — then stop without checking sections. The cause is `absent` only when that condition was `completed`; a read cut by a stall, the re-read cap, or the time bound records `truncated`, because the reply may lie past the cut. An empty surface returning the message "complete" would otherwise reach the shape branch and record `malformed`, seven sections missing from nothing; a re-read of that same empty surface would stall and record `truncated`, a cut in a reply that never existed.
   2. **Bound the read** as that section requires: it ends on the first of the surface returning the message complete (`completed`), a re-read yielding no new content (`stalled`), **5 re-reads** (`page_cap`), or **120 seconds** (`time_bound`). Record which condition ended it as `report_back_termination`, and derive the cause from it rather than writing the two side by side; only `completed` permits a shape judgment, and the other three record cause `truncated` whatever sections are present.
   3. **Then verify the reply** carries all seven required sections by case-insensitive heading presence, each with content under it. A missing section marks the operation `incomplete` with cause `malformed`, recorded in `.agent/dev-state.md`.
6. **Shutdown:** ask every agent to stop gracefully. In parallel topology, only the lead cleans up the team after all teammates stop.
7. **Recover:** reconcile the ledger identities against live native agents/teams before sending follow-ups. Never reactivate a completed identity by mention alone; dispatch a new fix or review identity.

GitHub Issues and PRs remain canonical. Claude's team task list is never the source of truth.
