# `/dev` — RTK + Multi-Harness Development Workflow

KHA Entertainment's maintained English fork of [`hnaymyh123-henry/claude-dev-skill`](https://github.com/hnaymyh123-henry/claude-dev-skill).

`/dev` turns the active Claude Code session into a Tech Lead that coordinates requirements, GitHub Issues, pre-created worktrees, delegated coding workers, QA, review, merge order, recovery state, and retrospectives. It runs in two execution modes: **Claude-native** (default, no Traycer required) or **Traycer** (optional multi-harness execution).

The canonical artifact is a user-invoked Skill at `skills/dev/`. The upstream `en/` and `zh/` command trees remain historical references and are not installed.

## Install

```bash
claude plugin marketplace add KHAEntertainment/claude-dev-skill
claude plugin install dev-skill@khaentertainment-dev-skill
```

Restart Claude Code, then invoke:

```text
/dev-skill:dev [optional project or feature description]
```

### Homebrew (alternative install)

If you prefer Homebrew, install via the [KHAEntertainment tap](https://github.com/KHAEntertainment/homebrew-tap):

```bash
brew tap KHAEntertainment/tap
brew install khaentertainment/tap/dev-skill
dev-skill-install --dry-run   # verify the install
brew test dev-skill            # run the formula's test block
```

The Homebrew formula and the plugin marketplace install the same payload but
follow independent release cadences. The formula may lag by one release while
`url`/`sha256` are bumped — see [`docs/RELEASING.md`](docs/RELEASING.md#homebrew-formula).

That is the whole install. To update later:

```bash
claude plugin marketplace update khaentertainment-dev-skill   # refresh the catalog
claude plugin update dev-skill                                # update the installed plugin
```

Both steps are needed — refreshing the catalog does not update an installed
plugin. Restart Claude Code afterwards to apply the update.

All of these commands are also available inside a session as `/plugin …`.

## Invocation

Type it yourself at any time:

```text
/dev-skill:dev [optional project or feature description]
```

The Skill is also model-invocable, so an explicit request survives the
plan-to-implementation transition. If you say during planning that you want the
dev skill — or the full Issue-to-PR workflow — once implementation starts, the
agent can invoke it for you after you accept the plan and before the first
implementation edit. You do not have to interrupt implementation to type the
command.

Explicit workflow intent is the trigger, not the subject matter. An ordinary
coding, debugging, refactoring, or review request with no stated `/dev` or
Issue-to-PR intent does not activate the Skill.

> Frontmatter is read when the Skill is loaded. A Claude Code session that was
> already running when you installed or updated the plugin keeps the previous
> invocation behavior until you reload the plugin or restart the session — the
> same reload the update steps above require. After a manual install, restart
> Claude Code before checking invocation behavior.

> The marketplace entry pins a release tag, so the plugin resolves only from a
> tagged release. See [Releasing](docs/RELEASING.md) for how a release is cut.

No SSH key is required — the marketplace entry fetches over HTTPS.

Prefer a bare `/dev` invocation, an air-gapped machine, or an isolated
evaluation target? See [Manual installation](#manual-installation).

## Execution Backends

`/dev` selects its execution substrate automatically and degrades gracefully when Traycer is absent.

### Claude-native — works without Traycer

When no Traycer session is present, the lead resolves the `claude-native` backend and records `backend_source: lead_resolved`. This mode runs entirely inside Claude Code and uses Agent Teams for parallel lanes — no Traycer, no tmux/iTerm. Anyone using `/dev` as a plain Claude Code skill stays on this path.

### Traycer — optional multi-harness

When both `TRAYCER_AGENT_ID` and `TRAYCER_EPIC_ID` are present, detection returns `traycer`/`ready` (`backend_source: detected`) and the lead loads the Traycer adapter. Traycer owns CLI worktree/session mechanics and launches receive-capable Chat/GUI child lanes on any supported harness (Claude Code, Codex, OpenCode, Cursor, …) through `rtk proxy traycer`, enabling cross-harness A2A coordination and managed transcript capture.

### Detection and fail-closed behavior

`skills/dev/scripts/detect_execution_backend.py` decides the backend from the environment only — it never probes binaries. Both identifiers present → `traycer`; otherwise it fails closed to `incomplete` (exit 2) and pauses rather than guessing. Because the absence of Traycer identifiers cannot distinguish a native Claude session from a Traycer child whose environment was not injected, `claude-native` is a **lead-resolved** choice backed by positive evidence, never an automatic fallback. The chosen backend is recorded in `.agent/dev-state.md` as `backend_source: detected | lead_resolved`.

## Customized Guarantees

### What's new in v2.1.1

- **Lead → user end-of-turn reply contract** — the Tech Lead summarizes, never relays: routine replies aim under 100 words; material failures, gate verdicts, decisions, and irreversible actions are surfaced first and in full. See [`skills/dev/reply-contract.md`](skills/dev/reply-contract.md) (WS1 / PR #55).
- **Post-merge verification step** — after every merge to `main`, the lead verifies the merged commit. When the merge commit's tree is identical to the verified PR head's tree, the PR-head Verification Gate result on record is re-used and the equivalence recorded; when the trees differ, the full gate re-runs on the merged commit in a clean worktree. The lead then re-checks the closed Issue's acceptance criteria against what shipped and reopens it for any unmet item. See [`skills/dev/phases/phase4.md`](skills/dev/phases/phase4.md) (Issue #26 / PR #46).
- **External-review rate-limit breakpoint** — after 3 consecutive rate-limited responses from a trusted reviewer on the same PR, the lead stops retrying and dispatches a fresh substitute reviewer whose model family differs from the implementation worker's, the QA lane's, and the internal reviewer's. The substitute must return a real verdict at the current head, and it takes that reviewer's seat as a review, not a bypass, so it creates no review debt. PR #46's manual substitute review after repeated CodeRabbit rate-limits is the precedent #48 codified. See [`skills/dev/phases/external-review.md`](skills/dev/phases/external-review.md) (Issue #48 / PR #68).
- **Scoped external-review bypass** — a bypass is only for a review that is pending or unavailable, never one invalidated by the author's own fix push, which instead obligates a re-request at the new head. It requires explicit user approval and records the reason, approver, timestamp, and review debt naming the exact unreviewed commit range (`<reviewed-head>..<merged-head>`, or `<base-head>..<merged-head>` when no review ever completed). Unlike a substitute review, a bypass is not a review (Issue #33 / PR #45).
- **Graft code-graph evidence adapter** — pinned optional code-graph evidence via `rtk proxy graft` with a four-step availability check, three approved queries (`callers`, `grep`, `map`), and a recorded manual fallback whenever `graph_evidence: unavailable`. See [`skills/dev/graft.md`](skills/dev/graft.md) (WS2 / PR #60).
- **Distribution: marketplace install plus Homebrew tap** — the [`KHAEntertainment/homebrew-tap`](https://github.com/KHAEntertainment/homebrew-tap) tap ships the `dev-skill` formula alongside the marketplace install. The formula follows its own release cadence and may lag a release; see [Homebrew (alternative install)](#homebrew-alternative-install) (Issue #39 / PR #65).
- **Child-harness capability checklist** — at first dispatch of a Traycer-managed lane, the child harness is checked against a four-item capability checklist and the result is recorded in `.agent/dev-state.md`. An unmet item fails the lane closed to `incomplete`; the remedy is a different route, never a trimmed prompt. ADR-012 in [`docs/architecture.md`](docs/architecture.md), checklist in [`skills/dev/backends/contract.md`](skills/dev/backends/contract.md) (WS4 / PR #61).

### Standing guarantees

- Never let the lead modify implementation or test code directly.
- Allow the lead to maintain tracked PRDs/context documents, using docs-only or related PRs after repository initialization.
- Use RTK wrappers and compact output for shell, Git, GitHub, tests, and linting.
- Persist recoverable runtime state in `.agent/dev-state.md` (execution backend, `backend_source`, reviewer/QA identities, correlation/response IDs).
- Detect Traycer only from a complete managed-session environment; partial context fails closed and binary presence never selects a backend.
- Select serial/parallel topology independently from the Claude-native/Traycer backend.
- Pre-create and verify one branch/worktree per coding agent; assign explicit file ownership.
- Use Claude Agent Teams for native parallel work and receive-capable Traycer Chat agents for cross-harness work. Keep GitHub Issues and PRs canonical.
- Route provider-neutral assignments to supported Traycer harnesses without duplicating the `/dev` SOP; native non-Claude lead entrypoints remain a separate packaging concern.
- Run quantitative QA, health scoring, scope-drift detection, two-pass review, coverage-path audit, and specialist review lanes.
- Detect, await, and triage current-head CodeRabbit, Kilo Code, and GitHub Copilot reviews before merge without replacing internal review.
- Ask agents to shut down gracefully, then have the lead perform adapter cleanup.

See [the full audit](docs/AUDIT.md), [upstream maintenance procedure](UPSTREAM.md), and [custom changelog](CHANGELOG.custom.md).

## Requirements

- Claude Code. Agent Teams are required only for Claude-native *parallel* topology.
- Git and an authenticated GitHub CLI (`gh`)
- [RTK](https://github.com/rtk-ai/rtk) — `brew install rtk`, or see the RTK README for other platforms
- Python 3 (used by the Skill at runtime, and by the manual installer's preflight validation)
- **Optional** Traycer CLI/Host for managed multi-harness execution; Traycer children use the Chat/GUI surface in v1. Without it, the skill runs Claude-native with no loss of core workflow.
- **Optional** [Graft](https://github.com/NanoNets/context-graph-engine) (`@nanonets/graft@0.18.0`) for pinned code-graph evidence at gates; accessed via `rtk proxy graft` per `skills/dev/graft.md`. Not installed by the Skill; each developer runs `graft init` locally if desired. Without it, gates record `graph_evidence: unavailable` and fall back to manual tracing — no loss of core workflow.
- Agent Teams run in-process and do not require tmux or iTerm

## Manual installation

The plugin above is the recommended path. Install manually when you want the
bare `/dev` invocation instead of `/dev-skill:dev`, when evaluating a change
against an isolated target, or on a machine that cannot reach the marketplace.

### Running both at once

The plugin and a manual install can coexist — they appear as `/dev-skill:dev`
and `/dev` respectively. They are two independent copies and will drift apart as
one is updated and the other is not. Pick one as your working path; if you
switch to the plugin, move the old Skill aside into the same backup location the
installer uses:

```bash
mkdir -p ~/.claude/backups/dev
mv ~/.claude/skills/dev ~/.claude/backups/dev/manual-$(date -u +%Y%m%dT%H%M%SZ)
```

This is the same `~/.claude/backups/dev/` directory the installer writes to, so
the restore instructions below apply unchanged.

### Validate before installing

```bash
python3 scripts/validate_skill.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
bash -n install.sh
shellcheck install.sh tests/test-install.sh
bash tests/test-install.sh
./install.sh --dry-run
```

### Isolated installation

Use an explicit target while another Claude Code session is active or while evaluating the Skill:

```bash
./install.sh --target "/tmp/claude-dev-test/skills/dev"
```

An explicit target does not migrate `~/.claude/commands/dev.md` or `~/.claude/commands/dev/` unless `--migrate-legacy` is also supplied.

### Live installation

When ready to swap the global `/dev` implementation:

```bash
./install.sh --dry-run
./install.sh
```

The default installation:

1. Validates every required Skill file and reference before mutation.
2. Stages the new Skill beside the destination.
3. Moves an existing `~/.claude/skills/dev` and legacy command paths into `~/.claude/backups/dev/<timestamp>/`.
4. Atomically renames the staged Skill into `~/.claude/skills/dev`.
5. Restores the previous Skill and command paths if installation fails.

Restart Claude Code after the swap, then invoke:

```text
/dev [optional project or feature description]
```

The restart is not optional if you are checking invocation behavior: a session
that was already running keeps the previously loaded frontmatter, including
whether the Skill is model-invocable.

Compatibility forms `--lang en` and `--lang=en` are accepted. Chinese installation is intentionally rejected before any filesystem mutation.

There is no uninstall command. To reverse an install, restore the most recent
directory under `~/.claude/backups/dev/`.

### Windows PowerShell

```powershell
.\install.ps1 -DryRun
.\install.ps1
```

Use `-Target C:\path\to\skills\dev` for an isolated target.

## Structure

```text
skills/dev/
├── SKILL.md
├── reply-contract.md
├── backends/
│   ├── contract.md
│   ├── claude-native.md
│   └── traycer.md
├── phases/
│   ├── phase1.md
│   ├── phase1-prototyping.md
│   ├── phase2.md
│   ├── phase3.md
│   ├── phase3.5.md
│   ├── external-review.md
│   ├── phase4.md
│   ├── phase5.md
│   └── repository-context.md
├── agents/
│   ├── report-back.md
│   ├── worker-new.md
│   ├── worker-fix.md
│   ├── qa-agent.md
│   ├── reviewer.md
│   ├── worker-prototype-frontend.md
│   └── worker-prototype-backend.md
├── templates/
│   ├── PROJECT_CONTEXT_TEMPLATE.md
│   └── DEV_STATE_TEMPLATE.md
└── scripts/
    ├── detect_execution_backend.py
    ├── inspect_external_reviews.py
    ├── dev_config.py
    └── resolve_repository.py
```

## Integrations

These are the third-party systems `/dev` invokes or composes with at runtime. RTK, Traycer, Graft, and CodeRabbit are wired into the Skill payload (`skills/dev/`) and gated by the verification harness. i-have-adhd is a documented composition only: the payload deliberately names no brevity skill (see [`docs/dogfooding.md`](docs/dogfooding.md#i-have-adhd)).

- **[RTK](https://github.com/rtk-ai/rtk)** — command transport for every shell, Git, GitHub, test, and lint invocation the Skill runs. Hard prerequisite at install time ([`install.sh`](install.sh) line 160); ambient thereafter and never version-checked at runtime.
- **[Traycer](https://github.com/traycerai/traycer)** — optional multi-harness execution backend. The lead loads the Traycer adapter at [`skills/dev/backends/traycer.md`](skills/dev/backends/traycer.md) only when both `TRAYCER_AGENT_ID` and `TRAYCER_EPIC_ID` are present in the environment; otherwise it resolves `claude-native`. Capability-verified: any gap in a child harness surfaces as `incomplete`, not as a silent fallback.
- **[i-have-adhd](https://github.com/ayghri/i-have-adhd)** — *composes with*, **not depends on**. A session brevity skill that `/dev` aligns with at the end-of-turn reply layer ([`skills/dev/reply-contract.md`](skills/dev/reply-contract.md) §6): `/dev` never claims a task-requirements override to justify verbosity. Per-session activation is required to enable i-have-adhd; `/dev` does not install, invoke, or require it.
- **[Graft](https://github.com/nanonets/graft) (`@nanonets/graft@0.18.0`)** — pinned optional code-graph evidence CLI used at gates via `rtk proxy graft`. Never an execution backend; `/dev` never runs `graft init` in a managed project. See [`skills/dev/graft.md`](skills/dev/graft.md).
- **[CodeRabbit](https://github.com/coderabbitai)** — trusted external reviewer for Phase 4 oversight ([`skills/dev/phases/external-review.md`](skills/dev/phases/external-review.md)). Substituted after the rate-limit breakpoint (#48) with a family-distinct reviewer from the review fallback chain; the substitute reviewer must post a real verdict — a clear status field is not a review.

## Concepts we learned from

These are systems `/dev` does *not* install. We borrow a discipline, cite the project that taught it to us, and stop there.

- **[Ponytail](https://github.com/dietrichgebert/ponytail)** by Dietrich Gebert — the reuse-first ladder borrowed in PR #30 (Issue #20) and stress-tested in the calibration experiment Issue #43. Also cited in [`docs/architecture.md`](docs/architecture.md) as the source of the config-leak problem that bounds the native non-Claude lead escape hatch. Not installed; `/dev` adapts the ladder only.
- The dogfooding distillation ([`docs/dogfooding.md`](docs/dogfooding.md), Issue #40 / PR #63) is `/dev`'s own codification, not a borrowed system — it captures seven lessons from this round's recovery log and is the method source for the rate-limit breakpoint (#48).

## Thank you

`/dev` is built on top of generous work by others. Thank you to:

- **RTK** and the RTK maintainers for the proxy command-transport primitives that the verification gate is built around.
- **Traycer** and the Traycer team for the multi-harness execution substrate that lets `/dev` coordinate Claude Code, Codex, OpenCode, Cursor, and other harnesses through one lead.
- **ayghri** for [i-have-adhd](https://github.com/ayghri/i-have-adhd) — a brevity-skill discipline that `/dev` aligns with rather than competes against.
- **NanoNets** for [Graft](https://github.com/nanonets/graft) — the code-graph evidence source whose pinned optional adapter gives `/dev` structured queries at every gate.
- **CodeRabbit** for the trusted external reviewer seat at Phase 4, and for the rate-limit substitution breakpoint that preserves the seat's intent under quota pressure.
- **Dietrich Gebert** for [Ponytail](https://github.com/dietrichgebert/ponytail) — the reuse-first ladder we adapted into the calibration workflow.
- The agents, maintainers, and reviewers who contributed to the upstream [`hnaymyh123-henry/claude-dev-skill`](https://github.com/hnaymyh123-henry/claude-dev-skill) lineage that this fork extends.

## License

MIT — see [LICENSE](LICENSE).
