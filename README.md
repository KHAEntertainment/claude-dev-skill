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
│   └── phase5.md
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
    └── resolve_repository.py
```

## License

MIT — see [LICENSE](LICENSE).
