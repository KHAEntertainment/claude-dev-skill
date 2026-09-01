# Phase 2 — Technical Breakdown & Project Initialization

---

## Command Output Rules

- Resolve the canonical repository before the first GitHub operation of this phase (`rtk proxy python3 "${CLAUDE_SKILL_DIR}/scripts/resolve_repository.py"`), and pause on `incomplete` rather than creating an Issue against whatever repository `gh` resolves. The only exception is `gh repo create --clone` on the new-project path: create the repository first, then immediately resolve and record the new repository identity before any further `gh` or `git push` operation.
- Use `rtk gh ...` for every GitHub CLI operation in this phase, and scope each one explicitly: `--repo OWNER/REPO` for `gh issue …` and `gh pr …`, the positional argument for `gh repo view`.
- Use `rtk git ...` or `rtk proxy git ...` for every git operation in this phase.
- Broad GitHub scans must use `--json` with summary fields and `--jq` one-line output. Do not request PR/Issue bodies, commits, comments, files, or reviews during broad scans.
- Deep-read a full Issue/PR body only for the specific item being created, revised, or implemented.

---

## Architecture Decision Checkpoint (run for all modes, before task decomposition)

Before decomposing tasks, the following architecture decisions must be confirmed and recorded in `PROJECT_CONTEXT.md`.
**Do not proceed to task decomposition until all decisions are complete.**

For each decision: follow the user's preference if stated; **if the user has no preference, Tech Lead gives a recommendation with reasoning, adopts it, and continues — do not block the flow.**

```
Architecture Decision Checklist:
□ Auth scheme: [JWT / Session / None] + token storage method
□ API design spec: [endpoint naming convention / unified error format / pagination structure]
□ Database schema: [core tables and fields (draft level)]
□ Database migration: [is there existing data? Yes → must specify a migration framework (Python: Alembic / Node: Knex / Java: Flyway)]
□ Full-stack project: does it need an API Contract document? (OpenAPI / endpoint list)
□ Code style conventions: [naming rules / directory structure conventions]

Confirm all decisions with the user before proceeding to task decomposition.
```

**Update PROJECT_CONTEXT.md immediately after architecture decisions are confirmed — do not wait for Phase 5.**

---

## Full Mode (New Project / New Feature)

### For Architectural Changes: Run Change Impact Assessment First

When requirements conflict with existing architecture decisions in PROJECT_CONTEXT.md (e.g. replacing the auth system, rewriting a core module), **before task decomposition** you must:

1. List affected merged PRs with a compact summary scan, e.g. `rtk gh pr list --repo OWNER/REPO --state merged --limit 20 --json number,title,mergedAt,headRefName --jq '.[] | "#\(.number) \(.headRefName) — \(.title)"'`, then deep-read only the likely affected PRs
2. Create a fix Issue for each affected merged PR (label: `[Arch Change] Fix code affected by PR #N`)
3. Review all open Issues with compact summary output, then close or revise any that conflict with the new architecture (explain why in Issue comments)
4. Immediately update the architecture decisions section of PROJECT_CONTEXT.md (do not wait for Phase 5)

### Execution Steps

1. Based on confirmed architecture decisions, decompose requirements into independent, parallelizable development tasks:
   - Completable by a single Agent independently
   - Has clear inputs, outputs, and completion criteria
   - Dependencies on other tasks are clear
   - **Identify cross-task shared infrastructure** (DB connection layer, auth middleware, shared utils, API client wrappers) — create a separate Issue for each, marking them as prerequisites for other tasks

2. **For new projects**, establish a real default branch before creating worktrees:

   1. Create and clone the repository with a server-generated initial commit: `rtk gh repo create [project-name] --private --add-readme --clone`. This establishes `main` without a direct lead-session push. `gh repo create` takes the project name positionally; it has no `--repo` flag.
   2. Enter the clone and verify readiness with `rtk git status --short`, `rtk git branch --show-current`, and `rtk git rev-parse HEAD`. Require `main`, a real commit, and a clean tree.
   3. Immediately resolve and record the new repository's identity with `rtk proxy python3 "${CLAUDE_SKILL_DIR}/scripts/resolve_repository.py"` before any further GitHub operation. A freshly cloned repository has a new `origin`, so the previous run's `repository.canonical` is stale until this succeeds.
   4. Create a docs-only bootstrap branch/worktree. In that worktree, create `PROJECT_CONTEXT.md` from `${CLAUDE_SKILL_DIR}/templates/PROJECT_CONTEXT_TEMPLATE.md`; add `API_CONTRACT.md` when required; submit and merge the bootstrap PR before implementation work starts.
   5. Create Issue #1 containing the frozen PRD (title: `[PRD] Product Requirements Document`), scoped with `--repo OWNER/REPO`.
   6. Create one Issue per development task using the template below, then create a milestone linking all Issues. Scope each creation explicitly.

   Do not create coding worktrees until the bootstrap PR is merged and `origin/main` contains the project context.

3. **For existing projects**:
   - Read `PROJECT_CONTEXT.md` to restore context
   - Create Issues for new requirements (use the Issue template below)
   - Update milestone

4. Present the task list for user confirmation using the explicit dependency format:
   ```
   Task List (N total):

   [Infrastructure Layer — must complete first, other tasks depend on it]
   □ Issue #1 [Infrastructure task] — output: xxx — blocks: #3, #4, #5

   [Parallel Development Layer]
   □ Issue #3 [Feature A] — output: xxx — depends on: #1 — can parallel with #4
   □ Issue #4 [Feature B] — output: xxx — depends on: #1 — can parallel with #3

   [Closing Layer — after all features complete]
   □ Issue #6 [Integration] — depends on: #3, #4, #5
   ```

5. **Enter Phase 3 after user confirms priorities/order**

---

## Express Mode (Emergency Hotfix)

**Skip the architecture decision checkpoint. Skip QA (Phase 3.5).**

1. Create one Hotfix Issue directly, title format: `[Hotfix] [incident description]`
2. Acceptance criteria only needs to cover: incident reproduction path + fix verification
3. Present the Issue to the user for confirmation, then **immediately enter Phase 3 (single Agent, using `worker-fix.md`)**
4. After PR is merged, **must run the affected PR coordination step** (see Phase 4 merge section)

---

## Lightweight Mode (Small Change / Bug Fix)

1. Create one Issue directly (use the Issue template below)
2. No task decomposition or milestone needed
3. Present the Issue to the user for confirmation, then **immediately enter Phase 3 (single Agent)**

---

## Refactoring Mode

Refactoring tasks must satisfy:
1. Issue acceptance criteria use the **dual-dimension format**:
   - Structural metric: `[file/module] lines/dependencies/complexity → target value` (e.g. `utils.py lines → no more than 200`)
   - Regression metric: `full test pass rate → 100%, no new lint errors`
2. Refactoring Issues **must be placed in the Infrastructure Layer**; all feature Issues that depend on the refactored module are marked as depending on it, **must not be parallelized**; feature Issues that do NOT depend on the refactored module may run in parallel
3. Worker Agent uses `worker-fix.md`; self-check must focus on: no breaking changes to any existing callers

---

## Issue Template

```markdown
## Task Description
[Background and goal]

## Acceptance Criteria (engineering-verifiable format)
Each criterion must follow: [trigger condition] → [expected response/state/side effect]
Example: POST /auth/register with existing email → returns 409, body contains error_code

- [ ] [trigger 1] → [expected result 1]
- [ ] [trigger 2] → [expected result 2]
- [ ] [edge case: empty input / extreme value] → [expected result]
- [ ] [if test framework exists: all tests pass, no regression]

## Architecture Constraint Reference
[Reference relevant decisions from PROJECT_CONTEXT.md or API_CONTRACT.md]

## Technical Notes
[Key implementation constraints or considerations]

## Out of Scope
[Explicit exclusions to prevent scope creep]
```
