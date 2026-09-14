---
kind: spec
title: "v2.1.0 dogfooding lessons"
---

# v2.1.0 dogfooding lessons

Short, evidence-anchored rules a maintainer or agent can use when running
`/dev` on a live repo. Source: the recovery log in `.agent/dev-state.md`
for the v2.1.0 round (kept outside this repo). No re-audit.

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

## Compatibility notes

Named notes for third-party skills `/dev` composes with. They live here, not
under `skills/dev/`, so the shipped payload stays third-party-agnostic.

### i-have-adhd
[i-have-adhd](https://github.com/ayghri/i-have-adhd) is a session brevity skill that `/dev` *composes with* and does **not depend on**. It requires per-session activation; `/dev` does not install, invoke, or require it.
*Composition point*: `skills/dev/reply-contract.md` §6 — "`/dev` never claims a task-requirements override to justify verbosity." With i-have-adhd active, the lead-to-user reply stays short (under 100 words for routine replies), while worker report-backs stay full in `.agent/dev-state.md` and the PR record.