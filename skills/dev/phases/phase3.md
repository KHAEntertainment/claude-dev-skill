# Phase 3 — Multi-Agent Parallel Development (Execution Rules)

---

## Execution Mode Selection

Choose exactly one execution mode before dispatch:

- **Agent Team mode**: use when there are 2+ independent GitHub Issues, each with clear file ownership and no unresolved dependency between them.
- **Single Worker mode**: use for one small Issue, same-file edits, tightly coupled refactors, sequential migrations, hotfixes, or any task where one worker would block another.

Do not silently change modes. Agent Teams can run in-process without tmux or iTerm; those tools are required only for split-pane display. If Agent Teams are unavailable or disabled, stop and ask before falling back.

## Worktree Preparation (coding workers only)

Before spawning any worker or coding teammate, the Tech Lead must:

1. Fetch `origin`, verify the integration branch, and require a clean lead worktree.
2. Create one named branch and one separate worktree per coding Issue, based on the correct integration branch (`origin/main` for ordinary work and hotfixes unless an approved dependency branch is explicitly required).
3. Verify each worktree's absolute path, branch, base commit, and clean status.
4. Record the mapping in `.agent/dev-state.md` before dispatch.
5. Pass the absolute worktree path and branch to the assigned worker. The worker must `cd` there and verify the mapping before any read or edit; it must not create or switch branches itself.

Read-only research, QA, and review teammates may share a checkout only when they make no file changes. Give them an explicit read-only lane and target commit/PR.

---

## Agent Team Mode

- Create one Agent Team with the Tech Lead as lead and named teammates such as `worker-auth`, `worker-api`, `worker-tests`, or `qa-reviewer`.
- Assign exactly one GitHub Issue to each Worker teammate before work starts.
- Give each coding teammate one pre-created, verified branch/worktree and explicit file ownership in the spawn prompt.
- GitHub Issues and PRs remain canonical. Claude's shared team task list is only runtime coordination.
- Teammates must not self-claim arbitrary tasks. Self-claiming is allowed only after the Tech Lead maps unblocked tasks to GitHub Issues and file ownership.
- Require plan approval before teammate code edits for architecture, database, auth, shared interfaces, migrations, or broad refactors.
- Each teammate must receive the relevant Worker Agent prompt content, with `[N]` replaced by its assigned Issue number.
- The Tech Lead must update `.agent/dev-state.md` after team creation with team name, teammate names, Issue/PR mapping, branches/worktrees, file ownership, blockers, and next action.
- When all teammate PRs are created or a teammate blocks, update the Task Board and `.agent/dev-state.md`.
- After all active teammate work is complete, ask each teammate to shut down gracefully. Once none remain active, have the lead clean up the team. Never ask a teammate to perform cleanup.

## Single Worker Mode

- Pre-create and verify one isolated worktree/branch, then dispatch one Worker Agent with the appropriate prompt file.
- The Worker Agent submits a PR from that assigned branch.
- Even with only one task, the Tech Lead never writes implementation or test code directly in the main conversation.

## Task Board Format

Output after all teammates/workers are launched, and re-output after each PR is created or blocker appears:

```
## Agent Task Board

| # | Mode | Teammate/Worker | Branch | Issue | Ownership | Status |
|---|------|------------------|--------|-------|-----------|--------|
| 1 | Team | worker-auth | feat/auth | #3 User login | src/auth/** | In progress |
| 2 | Team | worker-api | feat/user-api | #4 User profile API | src/api/user/** | In progress |
| 3 | Single | worker-fix | fix/cache-bug | #8 Cache bug | src/cache.ts | PR #12 created |
```

Status values:
- `In progress` — teammate/worker is running
- `PR #N created` — PR submitted, waiting for QA/review
- `Blocked: [reason]` — Tech Lead action needed

## Dispatching Workers Or Teammates

Pass the full content of the corresponding prompt file into the worker/teammate prompt, replacing `[N]` with the actual Issue number:

- New feature: read `${CLAUDE_SKILL_DIR}/agents/worker-new.md`, pass into the Worker Agent or teammate
- Fix / improvement: read `${CLAUDE_SKILL_DIR}/agents/worker-fix.md`, pass into the Worker Agent or teammate

Spawn prompt must also include:
- teammate name
- assigned Issue number
- branch name
- absolute pre-created worktree path and verified branch
- owned files/directories
- RTK-first command requirement
- whether plan approval is required before edits
