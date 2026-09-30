---
kind: spec
title: "Dogfooding lessons"
---

# Dogfooding lessons

Short, evidence-anchored rules a maintainer or agent can use when running
`/dev` on a live repo. Sources, both kept outside this repo: lessons 1 to 7
come from the recovery log in `.agent/dev-state.md` for the v2.1.0 round (no
re-audit); lessons 8 to 12 come from the session dogfooding notes F-72 to F-76,
recorded during the v2.1.1 round and its real-project testing.

## Lessons

### 1. A quiet result is not a passing result
No review, no reply, an empty query, and a command that never ran all read as success unless the boundary distinguishes "no evidence" from "evidence of pass".
*Evidence*: recovery entry 2026-09-11T22:49:02Z — four consecutive CodeRabbit rate-limits on PR #46 looked like "no review yet" rather than "review couldn't run," requiring an explicit breakpoint rule (#48) to substitute a different reviewer instead of letting the gate sit indefinitely.

### 2. A mutation set that never edits the data an artifact carries cannot detect a wrong artifact
Mutate the rows, delete them, and permute them, not only the surrounding text.
*Evidence*: recovery entry 2026-09-12T20:30:00Z — PR #55 round-2 mutation proofs (bare-filename, variable-form, nested-subdir) were the only tests that proved the validator caught the wrong artifact; substring-only tests would have passed for both correct and incorrect artifacts.

### 3. A review is superseded only when the code it criticised has changed, never merely because the head moved
A review recorded at head X stays valid at head X; a new head Y does not supersede it unless the specific criticism was addressed.
*Evidence*: recovery entry 2026-09-11T21:05:21Z — after PR #45's fix moved head to cf7b4d2, prior reviews at 50e2e6c did not satisfy merge; the rule "merge only with all three clear at this exact head" was enforced even when only mechanical changes were made.

### 4. Test a filter against a known instance of the signal, not only against the noise it is meant to drop
A test set that exercises only the cases the filter is meant to reject proves the filter rejects them, not that it accepts the right thing.
*Evidence*: recovery entry 2026-09-11T23:20:35Z — PR #49 QA scored 100/100 against scripted cases but missed two adversarial setups (ancestor-.git misclassification, ps1 silent tar-missing degrade); the reviewer surfaced both via executed probes, finding what scripted QA tests missed.

### 5. When a check fires on correct input, ask whether its input still matters before retargeting its comparison
A check triggering on valid input is a clue that the comparator needs to change, not a licence to ignore the input.
*Evidence*: recovery entry 2026-09-12T13:18:00Z — PR #55 round-1 reconciliation found `validate_skill.py` checking "reply-contract" as an unscoped substring; the substring fired on the right input but the comparator needed retargeting (per-section check in SKILL.md's Session State Anchor + Global Rules) — the input still mattered, the comparison location needed to change.

### 6. Read a document whole, or search it for the specific rule, before asserting what it says
An assertion about a document's content is unverified until the document has been read or searched at the location the assertion concerns.
*Evidence*: recovery entry 2026-09-11T21:00:36Z — PR #45 round-1 inspector with `--trusted-reviewer coderabbitai` broke identity mapping and false-read `not_applicable`; earlier snapshots before `snap-x` were false negatives because the inspector's assertion wasn't tied to the right config source — the inspector asserted without reading the config source that controlled the assertion's meaning.

### 7. A green status check or an acknowledgement is not a review
A passing status field or an "acknowledged" event is evidence of no findings so far, not evidence that a reviewer actually inspected the work.
*Evidence*: recovery entry 2026-09-12T06:29:38Z — PR #46 reached merge only by enforcing substitute review (kimi k3,thinking, APPROVE) after 4 CodeRabbit rate-limits; the "0 external-review bypasses" record required an actual reviewer verdict, not just a clear status field — a green status with no reviewer would have satisfied the gate's text but not its intent.

### 8. Learn how a reviewer signals a clean pass before writing the gate's wording
A reviewer that files a verdict only when its verdict changes can never satisfy a gate that demands a fresh verdict at every head.
*Evidence*: session note F-72 (2026-09-11) — CodeRabbit's APPROVED reviews on PRs #32, #35, and #36 all had empty bodies, and each lifted its own earlier CHANGES_REQUESTED at an older head. At `a03a285`, with nothing of its own to lift, its clean pass arrived only as a walkthrough comment ("No merge-blocking risk remains") and no review object, while GitHub's review decision still read APPROVED. An inference from three data points, not documented vendor behaviour.

### 9. A successful write is not a durable write
A tool call that reports success proves the write happened, not that it survived the next sync.
*Evidence*: session note F-73 (2026-09-11) — the Traycer artifact store rewrote the round's session notes from an older version, discarding about 84 minutes of edits that had each reported success. There was no conflict, error, or notice; the loss surfaced only when a later edit could not find its anchor. For anything the user asked to have recorded, re-check it after the next sync and keep a copy outside the store until it is confirmed.

### 10. Cleanup deferred to one end-of-run step never happens when runs rarely end
If the only collection point is the retro, every lane's agents and worktree outlive the run.
*Evidence*: session note F-74 (2026-09-15) — 98 agents in this repo's Traycer epic, 9 of them unarchived and idle, and 42 Traycer worktrees (20 GB) on the host. `phases/phase5.md` step 4 was the only cleanup point, and Phase 5 rarely completes in the same session. The audit itself is an absence-of-signal trap: the worktree CLI failed on the host, and a naive gauge would have read that failure as zero debt. Tracked as #73.

### 11. A supplied document should answer questions, not feed them
When the user hands over a design document, extract its decisions and ask only the gaps.
*Evidence*: session note F-75 (2026-09-15) — in the first greenfield run of v2.1.1, Phase 1 asked Module 1's 9 questions one at a time; 6 were already answered by the supplied document. When the user asked to fast-forward, the lead extracted Modules 2 to 5 in one turn: 24 decisions, one cross-module correction, one genuine question. The gap questions still mattered, so the fix is document-first, not skipping Phase 1. Tracked as #74.

### 12. Verifying an account is not routing it, and an untested failure claim is not evidence
A verify-and-stop layer leaves the routing to whoever runs it, who will improvise.
*Evidence*: session note F-76 (2026-09-15) — on a host with two `gh` logins, the Skill's account check passed, then the lead set up routing from its own know-how with five changes: two machine-wide and one that duplicated a token, which the Skill forbids. It also reported that a cross-account push "fails closed" without making a dry-run. On 2026-09-29 another process switched the host's active `gh` account mid-session: `git` stayed correct because its credentials route by repository owner, but `gh` failed silently, returning "Could not resolve to a Repository" for a private repo with no account-mismatch hint. A project-scoped `GH_CONFIG_DIR` now keeps `gh` on the right account (evidence on #75). Tracked as #75, paired with #37.

## Compatibility notes

Named notes for third-party skills `/dev` composes with. They live here, not
under `skills/dev/`, so the shipped payload stays third-party-agnostic.

### i-have-adhd
[i-have-adhd](https://github.com/ayghri/i-have-adhd) is a session brevity skill that `/dev` *composes with* and does **not depend on**. It requires per-session activation; `/dev` does not install, invoke, or require it.
*Composition point*: `skills/dev/reply-contract.md` §6 — "`/dev` never claims a task-requirements override to justify verbosity." With i-have-adhd active, the lead-to-user reply stays short (under 100 words for routine replies), while worker report-backs stay full in `.agent/dev-state.md` and the PR record.