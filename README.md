# `/dev` — RTK + Agent Teams Development Workflow

KHA Entertainment's maintained English fork of [`hnaymyh123-henry/claude-dev-skill`](https://github.com/hnaymyh123-henry/claude-dev-skill).

`/dev` turns the active Claude Code session into a Tech Lead that coordinates requirements, GitHub Issues, pre-created worktrees, coding workers, Agent Teams, QA, review, merge order, recovery state, and retrospectives.

The canonical artifact is a user-invoked personal Skill at `skills/dev/`. The upstream `en/` and `zh/` command trees remain historical references and are not installed.

## Customized Guarantees

- Never let the lead modify implementation or test code directly.
- Allow the lead to maintain tracked PRDs/context documents, using docs-only or related PRs after repository initialization.
- Use RTK wrappers and compact output for shell, Git, GitHub, tests, and linting.
- Persist recoverable runtime state in `.agent/dev-state.md`.
- Pre-create and verify one branch/worktree per coding teammate; assign explicit file ownership.
- Use Agent Teams only for genuinely parallel work. Keep GitHub Issues and PRs canonical.
- Run quantitative QA, health scoring, scope-drift detection, two-pass review, coverage-path audit, and specialist review lanes.
- Detect, await, and triage current-head CodeRabbit, Kilo Code, and GitHub Copilot reviews before merge without replacing internal review.
- Ask teammates to shut down gracefully, then have the lead clean up the team.

See [the full audit](docs/AUDIT.md), [upstream maintenance procedure](UPSTREAM.md), and [custom changelog](CHANGELOG.custom.md).

## Requirements

- Claude Code with personal Skills and Agent Teams support
- Git and authenticated GitHub CLI (`gh`)
- [RTK](https://github.com/rtk-ai/rtk)
- Python 3 for installer preflight validation
- Agent Teams enabled when team mode is desired; in-process mode does not require tmux or iTerm

## Validate Before Installing

```bash
python3 scripts/validate_skill.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
bash -n install.sh
shellcheck install.sh tests/test-install.sh
bash tests/test-install.sh
./install.sh --dry-run
```

## Isolated Installation

Use an explicit target while another Claude Code session is active or while evaluating the Skill:

```bash
./install.sh --target "/tmp/claude-dev-test/skills/dev"
```

An explicit target does not migrate `~/.claude/commands/dev.md` or `~/.claude/commands/dev/` unless `--migrate-legacy` is also supplied.

## Live Installation

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

Compatibility forms `--lang en` and `--lang=en` are accepted. Chinese installation is intentionally rejected before any filesystem mutation.

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
│   ├── worker-new.md
│   ├── worker-fix.md
│   ├── qa-agent.md
│   ├── worker-prototype-frontend.md
│   └── worker-prototype-backend.md
├── templates/
│   └── PROJECT_CONTEXT_TEMPLATE.md
└── scripts/
    └── inspect_external_reviews.py
```

## License

MIT — see [LICENSE](LICENSE).
