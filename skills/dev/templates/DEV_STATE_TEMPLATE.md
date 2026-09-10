---
schema_version: 2
execution:
  execution_backend: incomplete
  detection_status: incomplete
  detection_reason: not_checked
  backend_source: null
  topology: serial
  skill_dir: null
  traycer_agent_id: null
  traycer_epic_id: null
lead:
  agent_id: null
  harness: null
  model: null
  profile: null
  profile_source: null
  reasoning_effort: null
  route_source: null
reviewer:
  agent_id: null
  harness: null
  model: null
  profile: null
  profile_source: null
  reasoning_effort: null
  route_source: null
workers: []
pull_requests: []
blockers: []
next_action: run_backend_detection
updated_at: null
---

# /dev Recovery Log

The Tech Lead is the sole writer of this file. Append a timestamped entry after every verified transition. Do not let workers edit the ledger.

## Execution record schema

Each `execution` entry records: `execution_backend`, `detection_status`, `detection_reason`, `backend_source`, `topology`, `skill_dir`, `traycer_agent_id`, and `traycer_epic_id`.

`skill_dir` is the absolute path `${CLAUDE_SKILL_DIR}` resolved to at dispatch time. Dispatched agents do not inherit `CLAUDE_SKILL_DIR`, so the lead substitutes this path into worker, QA, and reviewer prompts before sending them. Re-resolve it at the start of each run rather than trusting a stored value: the path changes when the Skill is reinstalled, and it is version-stamped when the Skill is installed as a plugin.

Allowed `backend_source` values: `null` (not yet resolved), `detected` (the detector chose the backend), and `lead_resolved` (the lead overrode an `incomplete` result, e.g. `claude-native`).

## Worker record schema

Each `workers` entry records: `role`, `issue`, `agent_id`, `harness`, `model`, `profile`, `profile_source`, `reasoning_effort`, `permission_mode`, `route_source`, `branch`, `base_oid`, `source_workspace`, `worktree`, `ownership`, `status`, `pr`, `communication_response_id`, `report_back`, `report_back_termination`, `report_back_cause`, `created_at`, and `updated_at`.

Allowed status values: `planned`, `worktree_ready`, `active`, `blocked`, `pr_created`, `qa`, `review`, `complete`, `stopped`.

## Report-back record schema

`report_back` records whether the lane's report-back was observed and verified; `report_back_cause` records why it was not. The pair takes the same shape as `profile` / `profile_source` above — a value and the qualifier that explains it — rather than a nested record, which nothing else in a `workers` entry uses.

Allowed `report_back` values: `pending` (the lane has been dispatched and no report-back has been observed yet), `complete` (a reply correlated to `communication_response_id` carried all seven required sections), and `incomplete` (it did not).

Allowed `report_back_termination` values: `null` (no bounded read ran, because no correlated reply was observed), `completed` (the transport declared the reply complete), `stalled` (a page returned no new content, or a cursor that did not advance), `page_cap` (the adapter's page or re-read cap was reached), and `time_bound` (the adapter's time bound elapsed). These are the four conditions named in the report-back enforcement section of `${CLAUDE_SKILL_DIR}/backends/contract.md`, under one set of names for the contract, both adapters, and this ledger.

Allowed `report_back_cause` values: `null` when `report_back` is `pending` or `complete`, and otherwise exactly one of `absent`, `malformed`, or `truncated`, as defined in that same section. **A `report_back: incomplete` with a null cause is an invalid record.** The verdict only says the lane is unverified; the cause is the sole field that selects the remedy, so a verdict without one records that something failed while discarding what to do about it.

**`report_back_cause` is derived from `report_back_termination`, never authored beside it.** The lead records the termination condition it observed and reads the cause off this table; the two cannot disagree, because only one of them is written from evidence:

| `report_back_termination` | Sections present | `report_back` | `report_back_cause` |
|---|---|---|---|
| `null` | not examined | `incomplete` | `absent` |
| `completed` | all seven | `complete` | `null` |
| `completed` | any missing | `incomplete` | `malformed` |
| `stalled`, `page_cap`, `time_bound` | not judged | `incomplete` | `truncated` |

The mapping is total, so every observation has exactly one row, and any pairing not in this table is an invalid record — `truncated` beside `completed`, `malformed` beside a stall, or any non-null cause beside `report_back: complete`. A `pending` lane has not been observed at all: both fields are `null`.

The termination condition is kept because the cause is lossy on purpose. `truncated` covers three conditions that share one remedy — re-read — so the cause is sufficient to decide what to do next and insufficient to see a pattern across lanes. A transport that stalls on every lane and one that rarely hits the time bound are the same `truncated` in the cause and distinguishable only here.

`pending` is not a cosmetic default. Without it, a lane that reported cleanly and a lane nobody ever observed occupy the same absence in the ledger — which is the failure this field exists to make visible, one level up. A lane is never `complete` by never having been looked at.

## Pull request record schema

Each `pull_requests` entry records: `number`, `issue`, `branch`, `headRefOid`, `qa_status`, `qa_agent_id`, `internal_review_status`, `reviewer_agent_id`, `external_review_state`, `external_review_payload_snapshots`, `expected_reviewers`, `requested_reviewers`, `observed_reviewers`, `pending_reviewers`, `completed_reviewers`, `external_findings`, `unresolved_actionable_findings`, `review_deadline`, `wait_extensions`, `approved_review_requests`, `approved_bypasses`, `review_debt`, `required_checks`, `blockers`, `updated_at`, and `next_action`.

`external_review_payload_snapshots` is an append-only list of `{observed_at, headRefOid, path}` records, one per gate run, including disposition reruns. Each path points to the verbatim raw current-PR JSON saved by `--payload-snapshot` before inspection. Keep every snapshot unchanged, including its original formatting; do not replace it with a summary, diff, or interpretation. A missing or failed snapshot is an evidence failure, not a successful observation. The lead records the failure and resolves it before accepting the gate result.

Accepted reviews apply only to the recorded `headRefOid`. After any push, reset QA, internal review, and external-review completion to pending for the new head.

## Recovery entries

### YYYY-MM-DDTHH:MM:SSZ — event

- Verified state:
- Evidence:
- Transition:
- Next action:
