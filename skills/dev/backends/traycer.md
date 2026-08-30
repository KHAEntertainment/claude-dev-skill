# Traycer Execution Adapter

Use this adapter only when detection returns `traycer`. All CLI operations run through `rtk proxy traycer`. Any missing CLI/Host/authentication/permission/A2A capability, malformed JSON or NDJSON, missing page, or unverified response makes the operation `incomplete`; never fall back to Claude-native.

## Preflight

1. Confirm both session identifiers were recorded by the detector.
2. Run `rtk proxy traycer whoami --json` and `rtk proxy traycer host status --json`; authentication and Host must be verified rather than inferred.
3. Query the current lead with `rtk proxy traycer agent list --epic-id <epic-id> --sender-agent-id <lead-agent-id> --json` and verify `TRAYCER_AGENT_ID`, harness, model, and reasoning effort.
4. Query available values with `agent list-harnesses`, `agent list-harness-models`, and `agent list-profiles` before launching a configured route.
5. Read workspace `.traycer/agent-selection-guide.md` directly when present. The current CLI `agent selection-guide` exposes the global guide; query it only after the workspace guide.
6. Verify the selected Chat/GUI surface can receive A2A messages. V1 must create managed children with `--surface gui`; Terminal agents for Codex/OpenCode can send/read but are not valid receive-capable v1 children.

## Route resolution

Resolve each role in this order:

1. Explicit `PROJECT_CONTEXT.md` Execution Routing Policy.
2. Workspace `.traycer/agent-selection-guide.md`, read directly.
3. Global `rtk proxy traycer agent selection-guide --json`.
4. Lead route from the lead row in `rtk proxy traycer agent list --json`.

Validate harness, model, profile, reasoning effort, and permission mode against the preflight lists before launch. An invalid field, unavailable model/profile, or unsupported reasoning/permission value makes route resolution `incomplete`; do not substitute another route. On lead fallback, inherit harness/model/reasoning. Omit profile intentionally so Traycer uses `last_used`, and record profile as `value: omitted`, `source: traycer_last_used`. Do not add cost, rate-limit, or performance routing heuristics.

Traycer currently defaults creation to `full_access` unless an explicit selection guide chooses `supervised` or `auto_accept_edits`. Do not invent `read_only`. QA/review safety is enforced by their prompts and verified by a clean worktree check plus immutable local `HEAD` and PR `headRefOid` checks against the recorded target commit.

## Worktree preparation

The lead owns branch/base/path requirements; Traycer owns creation mechanics:

```text
rtk proxy traycer worktree create --workspace <source-workspace> --source-branch <verified-base> --branch <assigned-branch> --json
```

The adapter must never use `--carry-uncommitted`. Parse the structured response, then independently verify absolute source/run paths, assigned branch, base OID, and clean status. Record the exact source-workspace/worktree relationship before launch.

## Launch and messaging

Create one Chat/GUI agent bound to the exact source/run relationship:

```text
rtk proxy traycer agent create --epic-id <epic-id> --sender-agent-id <lead-agent-id> --surface gui --workspace-entry <source-workspace>=<worker-worktree> --harness <harness> --model <model> [--profile <profile>] [--reasoning-effort <level>] [--permission-mode <mode>] --json
```

Do not combine `--cwd` with the same workspace entry. Parse and record the new agent ID; require reviewer and QA IDs to differ from implementation IDs.

Send the full provider-neutral assignment and require a correlated reply:

```text
rtk proxy traycer agent send --epic-id <epic-id> --sender-agent-id <lead-agent-id> --to <agent-id> --message <assignment> --expect-reply --json
```

Record the returned response ID. Absence of an ID or an incomplete structured stream is `incomplete`.

## Observation, shutdown, and recovery

- Read `agent inbox --agent-id <lead-agent-id> --json`, passing each returned cursor/page token according to the installed CLI contract until the response declares completion; never treat the first page as complete.
- Use `agent transcript --json` and `agent list --json` to verify replies and live state. Correlate replies to the recorded response ID.
- When replying in the opened thread, pass its `--response-id`; a mismatched or absent correlation fails closed.
- Send a final status/report request before `agent stop`. Archive with `agent archive` only after the result is recorded. During preflight, verify the installed CLI exposes both commands and their current target-ID flags; if not, mark shutdown capability incomplete rather than guessing syntax.
- Delete worktrees only through the existing post-merge safety gate; stopping or archiving an agent does not authorize deletion.
- On recovery, load the YAML ledger and verify both `execution.traycer_agent_id` and `execution.traycer_epic_id` (not `lead.agent_id`) with `agent list`, consume pending inbox pages, reconcile transcript evidence, and update state before sending anything. Never duplicate an agent whose live state cannot be determined.

## Harness compatibility boundary

Traycer adapts launch, model/profile selection, worktree binding, and A2A transport. It does not translate Claude slash-command syntax or install `/dev` in another harness. Codex, OpenCode, Cursor, and other supported harnesses can execute provider-neutral worker/QA/reviewer assignments without their own `/dev` copy. A native non-Claude lead entrypoint would be a separate thin distribution over this same contract.
