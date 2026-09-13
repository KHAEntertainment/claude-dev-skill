---
kind: spec
title: "Graft Adapter — Pinned Optional Code-Graph Evidence"
---

# Graft Adapter

Pinned optional code-graph evidence source via `rtk proxy graft`. Never an execution backend.

## Scope & Non-Goals

- **Scope**: Availability/version/capability check via `rtk proxy graft --version` vs pinned line; worktree verify + graph build + freshness (record graph OID vs head); approved queries (callers-of, dependents/impact, symbol search; structured output); evidence & degraded path with `graph_evidence: present | unavailable` and cause `not_installed | version_mismatch | build_failed | unparseable_output | query_failure` + manual fallback actually performed (silence never passes); ledger fields (additive to DEV_STATE_TEMPLATE: `graft_version`, `graph_evidence`, cause).
- **Non-goals**: Not a backend; never `graft init` in managed projects; internals never reproduced; no installer change, no CI stub (optional dep; no executable surface).

## Pinned Version

Pinned Graft version: 0.18.0

Update procedure: when a new version passes the four compatibility checks (version check passes, `rtk proxy graft check` exits 0, approved queries return structured output, `graph_evidence: present` at a gate), open a PR updating this line and the `required_policy` token in `scripts/validate_skill.py`.

## Availability & Capability Check

Run at each gate that requests graph evidence:

```bash
# Version check (exact match required)
rtk proxy graft --version

# Worktree verify + graph build + freshness
rtk proxy graft check --json
```

Evaluation order (stops at first match):

1. **Binary missing**: If the `graft` binary is not found, record cause `not_installed` and take the degraded path.
2. **Version mismatch**: Record `graft_version` from the version check. If the version output does not contain the pinned line exactly, record cause `version_mismatch` and take the degraded path.
3. **Invalid JSON from `graft check`**: If the JSON output cannot be parsed, record cause `unparseable_output` and take the degraded path.
4. **Build failed**: If `graft check` exits non-zero with valid JSON, record cause `build_failed` and take the degraded path.

## Approved Queries

Only these queries are approved for gate evidence. All run with `--json` for structured output.

| Query | Purpose | Command |
|-------|---------|---------|
| Callers-of / Dependents (impact) | Who calls/references a symbol; blast radius | `rtk proxy graft callers <symbol> -d N --json` |
| Symbol search | Exhaustive regex search grouped by enclosing symbol | `rtk proxy graft grep "<regex>" --json` |
| Repo orientation | Directory clusters, hubs, hotspots | `rtk proxy graft map --json` |

No other queries (e.g., `graft ask`, `graft skeleton`, `graft blast`, `graft viz`) are approved for gate evidence.

## Evidence & Degraded Path

At every gate that requests graph evidence, the lane must produce:

```
graph_evidence: present | unavailable
graph_evidence_cause: null | not_installed | version_mismatch | build_failed | unparseable_output | query_failure
```

When `graph_evidence: present`, include the relevant query output (trimmed to the gate's token budget) and the `graft check` freshness result.

When `graph_evidence: unavailable`, the lane **must actually perform the manual fallback** (e.g., `rg`, `git grep`, manual call-tree trace) and record what was done. Silence never passes — a lane that records `unavailable` without a manual fallback is incomplete.

### Query Failure Classification

When an approved query (`rtk proxy graft callers`, `rtk proxy graft grep`, `rtk proxy graft map`) exits non-zero or produces invalid JSON:

- Record cause `query_failure`
- Set `graph_evidence: unavailable`
- Perform and record the manual fallback (`rg`, `git grep`, manual call-tree trace)
- Preserve the existing output and freshness requirements when evidence is present

## Ledger Fields (Additive to DEV_STATE_TEMPLATE)

Add to each `workers` entry:

- `graft_version`: string — the version string from `graft --version`, or `null` if not installed
- `graph_evidence`: `present` | `unavailable` — whether graph evidence was produced at the gate
- `graph_evidence_cause`: `null` | `not_installed` | `version_mismatch` | `build_failed` | `unparseable_output` | `query_failure` — cause when unavailable

## Gate Integration

Gates that request graph evidence (per the five prompt sites) must:

1. Run the availability/capability check
2. If `present`, run the approved query/queries and include output
3. If `unavailable`, perform and record the manual fallback
4. Record the three ledger fields above
5. Never treat silence as evidence