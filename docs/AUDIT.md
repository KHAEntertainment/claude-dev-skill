# Upstream and Customized `/dev` Audit

Audit baseline:

- Upstream repository: `hnaymyh123-henry/claude-dev-skill`
- Installed-era upstream: `3abcd9a75d3032e12a499afb464b56695a424cb9`
- Audited upstream HEAD: `3e87db0c71ff51ad19c932a6849777e66398f556`
- Customized source: the installed global command plus its pre-Agent-Teams RTK backup

## Feature Matrix

| Feature | Chinese HEAD | English HEAD | Customized installed copy |
|---|---|---|---|
| Phase 0 request routing | Complete | Complete, without Chinese lightweight direct-edit route | Complete; all code uses workers |
| Lightweight mode | Lead directly edits ≤2 files under constraints | Issue + single worker | Issue + single worker; preserved |
| Phase 1 module-progressive alignment | Complete | Complete | Complete after upstream merge |
| Phase 1 prototyping | Complete | Complete | Complete after upstream merge |
| Progressive project-context template | Complete | Complete | Complete after upstream merge |
| New-project repo/bootstrap sequence | Detailed clone + initial-main flow | Incomplete | Customized only indirectly before merge |
| Architecture checkpoint/dependency DAG | Complete | Complete | Complete with RTK output controls |
| Worker isolation | `isolation: "worktree"` instruction | Same | Explicit ownership and isolation intent |
| Agent Teams selection | None | None | Team/single-worker selection and specialists |
| Pre-created verified worktrees | None | None | Newly formalized in maintained Skill |
| Recovery state | None | None | `.agent/dev-state.md` |
| Quantitative Phase 3.5 trigger | `phase3.5.md` | Missing | Coarse large-change rule |
| QA diff focus and evidence honesty | Complete | Partial | RTK rules and specialist lane |
| QA severity and health score | Complete | Partial | Added by selective merge |
| Scope-drift gate | Complete | Missing | Added by selective merge |
| Two-pass review | Complete | Older single checklist | Added by selective merge |
| Fix-first review behavior | Lead directly fixes code | Missing | Adapted to delegated worker fixes |
| Adversarial second opinion | Complete | Missing | Added as read-only specialist lane |
| Retest after self-fix | Complete | Missing | Added to worker prompts |
| Bisectable commits | Complete | Missing | Added to worker prompts |
| Phase 5 debt sweep | `phase5.md` | Missing | Added with code cleanup delegated |
| RTK command/output efficiency | None | None | Complete and preserved |
| Agent Teams cleanup | None | None | Graceful teammate shutdown + lead cleanup |
| Installer completeness | Chinese Bash mostly complete | Bash fails on missing files; PowerShell incomplete | Replaced with canonical Skill installer |

## English Translation of Chinese-Only Behavior

The maintained English Skill includes these translations:

1. Route lightweight implementation changes through a single worker instead of allowing lead-session code edits.
2. Establish a real default branch for new repositories before creating worktrees. Use a server-generated README commit, then submit project context through a docs-only bootstrap PR.
3. Trigger Phase 3.5 when the diff reaches 50 lines, 3 files, a new external interface, a schema change, or auth/permission logic.
4. Resolve the PR branch and commit before QA dispatch; treat QA as a one-shot, read-only lane.
5. Distinguish executed tests from static code evidence in every QA report.
6. Grade Critical/High/Medium/Low findings and calculate the translated health score; require at least 80 with no Critical/High findings.
7. Run Scope Drift before the review checklist.
8. Review in Critical and Informational passes, including a coverage-path audit.
9. Trigger an adversarial read-only reviewer only for unresolved judgment calls.
10. Rerun tests whenever self-check causes code changes.
11. Produce semantic, bisectable commits in dependency order.
12. Run the retro before a focused dead-document, deprecated-code, feature-flag, and TODO/FIXME sweep.

## Conflicts and Decisions

| Conflict | Decision |
|---|---|
| Chinese lightweight mode lets the lead modify code | Reject. Keep the iron rule for implementation/tests. |
| Chinese review `AUTO-FIX` lets the lead patch code | Translate as `DELEGATE-FIX`; a worker performs the change. |
| Chinese Phase 5 directly deletes dead code | Create a cleanup Issue/worktree/PR and dispatch `worker-fix.md`. |
| Lead needs to maintain PRDs and context | Allow direct tracked planning/context edits, but use a docs-only or related PR after repo initialization. |
| Agent Teams do not automatically isolate files | Lead pre-creates and verifies one worktree/branch per coding teammate. Read-only reviewers may share a checkout. |
| tmux/iTerm treated as a team prerequisite | Corrected: only split panes require them; in-process teams do not. |
| Old TeamCreate/TeamDelete lifecycle assumptions | Use current natural-language team creation, graceful teammate shutdown, and lead-owned cleanup. |
| English source lacks older Chinese improvements | Maintain one canonical English Skill containing selective translations. |
| Legacy commands and Skills can both expose `/dev` | Default installer migrates legacy paths into a recoverable backup before installing the Skill. |

## Selective Merge Result

The customized lineage was reconstructed as reviewable commits:

1. Branch from installed-era upstream `3abcd9a`.
2. Apply the pre-Agent-Teams RTK/recovery delta.
3. Apply the installed Agent Teams/ownership/specialist delta.
4. Merge upstream `3e87db0` without flattening history.
5. Add the canonical English `skills/dev/` distribution and selectively translated behavior.
6. Replace the incomplete bilingual installers with validated English-only Skill installers.

The legacy `en/` and `zh/` trees remain upstream historical references. `skills/dev/` is the maintained release artifact and the installer never reads from the legacy trees.
