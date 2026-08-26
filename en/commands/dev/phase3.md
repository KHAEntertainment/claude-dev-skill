# Phase 3 — Multi-Agent Parallel Development (Execution Rules)

---

## Execution Mode Selection

Choose exactly one execution mode before dispatch:

- **Agent Team mode**: use when there are 2+ independent GitHub Issues, each with clear file ownership and no unresolved dependency between them.
- **Single Worker mode**: use for one small Issue, same-file edits, tightly coupled refactors, sequential migrations, hotfixes, or any task where one worker would block another.

Do not silently change modes. If Agent Team mode was requested but cannot start because the feature is disabled, tmux/iTerm support is missing, or another dependency is blocked, attempt the obvious fix first. If not possible, stop and ask before falling back.

---

## Agent Team Mode

- Create one Agent Team with the Tech Lead as lead and named teammates such as `worker-auth`, `worker-api`, `worker-tests`, or `qa-reviewer`.
- Assign exactly one GitHub Issue to each Worker teammate before work starts.
- Give each teammate explicit branch/worktree/file ownership in the spawn prompt.
- GitHub Issues and PRs remain canonical. Claude's shared team task list is only runtime coordination.
- Teammates must not self-claim arbitrary tasks. Self-claiming is allowed only after the Tech Lead maps unblocked tasks to GitHub Issues and file ownership.
- Require plan approval before teammate code edits for architecture, database, auth, shared interfaces, migrations, or broad refactors.
- Each teammate must receive the relevant Worker Agent prompt content, with `[N]` replaced by its assigned Issue number.
- The Tech Lead must update `.agent/dev-state.md` after team creation with team name, teammate names, Issue/PR mapping, branches/worktrees, file ownership, blockers, and next action.
- When all teammate PRs are created or a teammate blocks, update the Task Board and `.agent/dev-state.md`.
- After all active teammate work is complete, ask teammates to shut down and then clean up the team.

## Single Worker Mode

- Dispatch one Worker Agent with the appropriate prompt file.
- The Worker Agent still uses an isolated worktree/branch and submits a PR.
- Even with only one task, the Tech Lead never writes project code directly in the main conversation.

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

- New feature: read `~/.claude/commands/dev/worker-new.md`, pass into the Worker Agent or teammate
- Fix / improvement: read `~/.claude/commands/dev/worker-fix.md`, pass into the Worker Agent or teammate

Spawn prompt must also include:
- teammate name
- assigned Issue number
- branch name
- worktree or isolation expectation
- owned files/directories
- RTK-first command requirement
- whether plan approval is required before edits