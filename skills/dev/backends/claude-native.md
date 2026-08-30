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
4. **Message:** provide the provider-neutral assignment envelope and full role prompt. Record the dispatch message/result identifier when exposed.
5. **Observe:** use the native agent/team status and message surfaces. Do not infer completion from silence.
6. **Shutdown:** ask every agent to stop gracefully. In parallel topology, only the lead cleans up the team after all teammates stop.
7. **Recover:** reconcile the ledger identities against live native agents/teams before sending follow-ups. Never reactivate a completed identity by mention alone; dispatch a new fix or review identity.

GitHub Issues and PRs remain canonical. Claude's team task list is never the source of truth.
