# PROJECT_CONTEXT.md — Index File

> This is the master index — it only routes, it does not pile up content.
> Detailed content is spread across sub-documents in `docs/`.
> The `/dev` skill reads this file at every Phase to restore context.

---

## Repository Info

- **Repo URL**: https://github.com/KHAEntertainment/claude-dev-skill
- **Main branch**: `main` (maintained customized distribution)
- **Mirror branch**: `master` (upstream mirror, retained for comparison — never release from it)
- **Upstream**: https://github.com/hnaymyh123-henry/claude-dev-skill
- **Created**: fork maintained since 2026-08-26

## What this project is

A maintained English fork of an upstream Claude Code Skill. The canonical shipped
artifact is `skills/dev/` — 23 files of Markdown plus two stdlib-only Python
scripts. The repository is therefore **content-first**: almost every change is
prose that an agent reads at runtime, not code that executes. `en/` and `zh/` are
historical upstream command trees and are never installed.

See [UPSTREAM.md](UPSTREAM.md) for the fork/merge procedure and
[docs/AUDIT.md](docs/AUDIT.md) for the upstream-vs-fork feature matrix.

---

## Sub-document Index

| File | Content | Update timing |
|------|---------|---------------|
| `docs/architecture.md` | Architecture Decision Records for packaging and distribution | Immediately when a decision is made |
| `docs/feature-log.md` | Completed features (PR number, merge date) and known tech debt | Every Phase 5 round |
| `docs/AUDIT.md` | Upstream-vs-fork feature matrix and risk register | On each upstream merge |
| `docs/glossary.md` | — not used; this project has no domain terminology layer | n/a |
| `docs/api-contracts.md` | — not used; no network API surface | n/a |
| `docs/tech-stack.md` | — folded into the Tech Stack section below (too thin for its own file) | n/a |
| `docs/style-guide.md` | — folded into the Conventions section below | n/a |

---

## Tech Stack

- **Payload**: Markdown (the Skill itself) + Python 3.10+ stdlib-only scripts
- **Installer**: Bash (`install.sh`) and PowerShell (`install.ps1`)
- **Tests**: Python `unittest` (36 tests) + Bash assertion suite (9 assertions) + PowerShell suite (5 assertions)
- **No third-party runtime or build dependencies.** This is a deliberate constraint — see ADR-005.

Runtime prerequisites for the Skill (not for installing it): `rtk`, `gh`, `git`,
Python 3, optionally Traycer CLI/Host.

---

## Conventions

- Everything in `skills/dev/` refers to siblings as `${CLAUDE_SKILL_DIR}/<relpath>` — never a hardcoded path.
- `scripts/validate_skill.py` is the gatekeeper: a 23-path required manifest, frontmatter keys, a forbidden-token list, and a required-policy token allowlist. Adding prose is safe; removing policy tokens fails the build.
- No CJK characters anywhere in the payload (enforced by the validator).
- No absolute machine paths in the payload (enforced by the validator).
- `bin/` must never exist at repo root — Claude Code plugin auto-discovery would add it to the Bash tool PATH.

---

## Current Status

- **Last updated**: 2026-08-30
- **Current iteration goal**: Ship two new distribution channels — a Claude Code plugin marketplace and (next round) a Homebrew tap — while leaving `install.sh` intact. Driven by open Issue #1, external feedback reporting user drop-off during setup.
- **Open PRs**: none at Phase 2 entry
- **Known tech debt**: see the bottom of `docs/feature-log.md`

---

## Verification Gate

The exact commands worker, QA, and reviewer must all run. Replaces the language
defaults in `${CLAUDE_SKILL_DIR}/phases/phase4.md`.

- **Lint**: `shellcheck install.sh tests/test-install.sh` (add new shell files as they land)
- **Type check**: `n/a` — no typed surface
- **Static analysis**: `bash -n install.sh` and `python3 scripts/validate_skill.py`
- **Dependency scan**: `pip-audit` — currently reports nothing because the project declares no third-party dependencies and ships no manifest. Keep running it; it becomes meaningful when PyPI packaging lands.
- **Tests**: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'` and `bash tests/test-install.sh`
- **Packaging**: `claude plugin validate . --strict` and `claude plugin tag --dry-run .`

A change is not complete until every command above exits clean.

---

## External Review Policy

- **Mode**: auto
- **Trusted reviewers**: coderabbit, kilo, github-copilot
- **Required reviewers**: none
- **Ignored reviewers**: none
- **Additional reviewer identities**: none
- **Default wait minutes**: 10
- **Allow automatic review requests**: false

CodeRabbit reviewed PR #1 in the prior round and is the expected reviewer here.

---

## Execution Routing Policy

Omitted — use the selected backend's lead route for every role.
