# Traycer Execution Adapter

Use this adapter only when detection returns `traycer`. All CLI operations run through `rtk proxy traycer`. Any missing CLI/Host/authentication/permission/A2A capability, malformed JSON or NDJSON, missing page, or unverified response makes the operation `incomplete`; never fall back to Claude-native.

## Preflight

1. Confirm both session identifiers were recorded by the detector.
2. Run `rtk proxy traycer whoami --json` and `rtk proxy traycer host status --json`; authentication and Host must be verified rather than inferred.
3. Query the current lead with `rtk proxy traycer agent list --json` and verify `TRAYCER_AGENT_ID`, harness, model, reasoning effort, and that the session's epic matches the recorded `TRAYCER_EPIC_ID`; otherwise mark the operation `incomplete`. The CLI derives epic and caller from the current session; it accepts no `--epic-id` or `--sender-agent-id` flags.
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
rtk proxy traycer agent create --surface gui --workspace-entry <source-workspace>=<worker-worktree> --harness <harness> --model <model> [--profile <profile>] [--reasoning-effort <level>] [--permission-mode <mode>] --json
```

Do not combine `--cwd` with the same workspace entry. Parse and record the new agent ID; require reviewer and QA IDs to differ from implementation IDs.

Send the full provider-neutral assignment and require a correlated reply:

```text
rtk proxy traycer agent send --to <agent-id> --message <assignment> --expect-reply --json
```

The assignment must embed the report-back contract from `${CLAUDE_SKILL_DIR}/agents/report-back.md`, so the lane receives it as adapter payload and not only through its role prompt. Sending without `--expect-reply` is never a way to dispatch a lane that is not expected to report.

Record the returned response ID. Absence of an ID or an incomplete structured stream is `incomplete`.

## Observation, shutdown, and recovery

- Read `agent inbox --agent-id <lead-agent-id> --json`, passing each returned cursor/page token according to the installed CLI contract until the response declares completion; never treat the first page as complete.
- **Classify `absent` before anything else.** When the bounded inbox read ends, first ask whether it produced a reply correlated to the recorded response ID. If it did not, record `report_back: incomplete` and the read's `report_back_termination` — the read ran, so it ended somehow — then stop without checking sections. The cause is `absent` only when that condition was `completed`, meaning the inbox declared itself exhausted and the reply was not in it; a read cut by a stall, the 20-page cap, or the 120-second bound records `truncated`, because the reply may lie past the cut and nothing about the lane has been established. An empty inbox stalls on its second page like any other non-advancing cursor, so without this the commonest failure in this round — a lane that never replied — would record `truncated`, sending the lead to re-read a reply that was never sent.
- **Bound that read.** It ends on the first of: the response declares the reply complete (`completed`); a page returns no new content or a cursor equal to the one just sent (`stalled`); **20 pages** consumed (`page_cap`); **120 seconds** elapsed across the read (`time_bound`). Record which of the four ended it as `report_back_termination` — that recorded condition, not the reply's text, is what selects the cause below, and the cause is derived from it rather than written alongside it. The stall condition is the one that fires in practice: a transport that never declares completion returns a non-advancing cursor rather than an error, and without it the other two bounds only delay the same loop.
- Use `agent transcript --json` and `agent list --json` to verify replies and live state. Correlate replies to the recorded response ID.
- Having correlated a reply, verify it carries all seven required sections — Outputs; Commands + exit codes; Deviations; Quality-gate self-assessment; Acceptance criteria; Evidence; Scope / ownership — by case-insensitive heading presence, each with content under it. A missing section fails the lane closed per the report-back enforcement section of `${CLAUDE_SKILL_DIR}/backends/contract.md`: record `report_back: incomplete` with cause `malformed`. A lane whose recorded response ID never produced a reply was already recorded `absent` by the precedence rule above and never reaches this check; `agent list` showing the agent alive and idle is not a completion signal. Check shape only when the bounded read above ended on the completion signal. If it ended on a stall, the 20-page cap, or the 120-second bound, record cause `truncated` regardless of which sections are present, and re-read rather than re-request.
- When replying in the opened thread, pass its `--response-id`; a mismatched or absent correlation fails closed.
- Send a final status/report request before `agent stop`. Archive with `agent archive` only after the result is recorded. During preflight, verify the installed CLI exposes both commands and their current target-ID flags; if not, mark shutdown capability incomplete rather than guessing syntax.
- Delete worktrees only through the existing post-merge safety gate; stopping or archiving an agent does not authorize deletion.
- On recovery, load the YAML ledger and verify both `execution.traycer_agent_id` and `execution.traycer_epic_id` (not `lead.agent_id`) with `agent list`, consume pending inbox pages, reconcile transcript evidence, and update state before sending anything. Never duplicate an agent whose live state cannot be determined.

## Harness compatibility boundary

Traycer adapts launch, model/profile selection, worktree binding, and A2A transport. It does not translate Claude slash-command syntax or install `/dev` in another harness. Codex, OpenCode, Cursor, and other supported harnesses can execute provider-neutral worker/QA/reviewer assignments without their own `/dev` copy. A native non-Claude lead entrypoint would be a separate thin distribution over this same contract.
