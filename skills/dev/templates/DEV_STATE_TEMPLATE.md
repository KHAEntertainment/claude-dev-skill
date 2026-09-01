---
schema_version: 2
repository:
  canonical: null
  origin_url: null
  gh_default: null
  identity_status: incomplete
  identity_reason: not_checked
  verified_at: null
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

## Repository record schema

The `repository` entry records: `canonical`, `origin_url`, `gh_default`, `identity_status`, `identity_reason`, and `verified_at`.

`canonical` is the `OWNER/REPO` value returned by `${CLAUDE_SKILL_DIR}/scripts/resolve_repository.py`, normalized from the `origin` remote and reconciled with the configured `gh` default repository. Allowed `identity_status` values are `incomplete` (nothing may touch GitHub yet) and `ready`. `identity_reason` keeps the resolver's emitted reason code — `missing_origin`, `non_github_origin`, `ambiguous_origin`, `push_mismatch`, `default_conflicts_with_origin`, `ambiguous_default`, `inaccessible_repository`, `origin_redirects`, `expected_mismatch`, `git_cli_missing`, `gh_cli_missing`, `origin_matches_default`, or `origin_is_only_github_remote`.

`origin_url` is the resolver's redacted `remote_url` output with any userinfo removed; never persist a raw remote URL that may contain credentials.

Every GitHub command carries `canonical` explicitly, and every assignment envelope repeats it. Re-resolve after creating or cloning a repository, and whenever remotes or the `gh` default change; a stale `ready` is not evidence.

## Execution record schema

Each `execution` entry records: `execution_backend`, `detection_status`, `detection_reason`, `backend_source`, `topology`, `skill_dir`, `traycer_agent_id`, and `traycer_epic_id`.

`skill_dir` is the absolute path `${CLAUDE_SKILL_DIR}` resolved to at dispatch time. Dispatched agents do not inherit `CLAUDE_SKILL_DIR`, so the lead substitutes this path into worker, QA, and reviewer prompts before sending them. Re-resolve it at the start of each run rather than trusting a stored value: the path changes when the Skill is reinstalled, and it is version-stamped when the Skill is installed as a plugin.

Allowed `backend_source` values: `null` (not yet resolved), `detected` (the detector chose the backend), and `lead_resolved` (the lead overrode an `incomplete` result, e.g. `claude-native`).

## Worker record schema

Each `workers` entry records: `role`, `issue`, `agent_id`, `harness`, `model`, `profile`, `profile_source`, `reasoning_effort`, `permission_mode`, `route_source`, `branch`, `base_oid`, `source_workspace`, `worktree`, `ownership`, `status`, `pr`, `communication_response_id`, `created_at`, and `updated_at`.

Allowed status values: `planned`, `worktree_ready`, `active`, `blocked`, `pr_created`, `qa`, `review`, `complete`, `stopped`.

## Pull request record schema

Each `pull_requests` entry records: `number`, `issue`, `branch`, `headRefOid`, `qa_status`, `qa_agent_id`, `internal_review_status`, `reviewer_agent_id`, `external_review_state`, `expected_reviewers`, `requested_reviewers`, `observed_reviewers`, `pending_reviewers`, `completed_reviewers`, `external_findings`, `unresolved_actionable_findings`, `review_deadline`, `wait_extensions`, `approved_review_requests`, `approved_bypasses`, `review_debt`, `required_checks`, `blockers`, `updated_at`, and `next_action`.

Accepted reviews apply only to the recorded `headRefOid`. After any push, reset QA, internal review, and external-review completion to pending for the new head.

## Recovery entries

### YYYY-MM-DDTHH:MM:SSZ — event

- Verified state:
- Evidence:
- Transition:
- Next action:
