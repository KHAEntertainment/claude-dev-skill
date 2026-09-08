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
| `docs/RELEASING.md` | Version sites, tag scheme, and the release procedure | When the release process changes |
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

- **Last updated**: 2026-09-05 (v2.1.0 round opened)
- **Current iteration goal**: v2.1.0 — close the four open Issues and borrow code-minimalism and completion-evidence discipline into the role prompts. Seven PRs, forced serial: arch docs, Issue #16 (external-review inspector), Issue #20 (role-prompt discipline), Issue #3 (adapter-layer report-back), Issue #19 in two parts (repository identity, then liveness preflight with Issue #17), then the release.
- **Architecture decisions this round**: ADR-008 reframes repository identity as a capability question rather than a verification question. ADR-009 reclassifies the read-only AST guard as a CI-time authorship lint rather than a security control. Both are recorded ahead of the implementation PRs that depend on them.
- **Next iteration**: Homebrew tap (ADR-007) — needs a tagged tarball, which exists at `v2.0.1`. Two follow-ups will be filed by this round's release PR: a GitHub App installation token for true per-run credential scoping, and a loopback fake `gh` host for resolver fixtures.
- **Open PRs**: see `gh pr list`; this round runs one PR at a time.
- **Known tech debt**: see the bottom of `docs/feature-log.md`

---

## Verification Gate

The exact commands worker, QA, and reviewer must all run. Replaces the language
defaults in `${CLAUDE_SKILL_DIR}/phases/phase4.md`.

- **Lint**: `shellcheck install.sh tests/test-install.sh scripts/check_plugin_root.sh`
- **Type check**: `n/a` — no typed surface
- **Static analysis**: `bash -n install.sh` and `python3 scripts/validate_skill.py`
- **Dependency scan**: `n/a` — the project declares no third-party dependencies and ships no dependency manifest, so there is nothing to scan. Reinstate `pip-audit` when PyPI packaging lands and a manifest exists. Recorded as `n/a` deliberately rather than listing a command that exits 127, which would train everyone to ignore a failing gate.
- **Tests**: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`, `bash tests/test-install.sh`, and — on Windows, or any runner with PowerShell — `pwsh tests/test-install.ps1`. The PowerShell suite is the only coverage `install.ps1` has; a gate that omits it can pass green while the Windows installer is broken.
- **Packaging**: `scripts/check_plugin_root.sh` and `python3 scripts/check_version_sync.py`. CI then attempts `claude plugin validate . --strict` and `claude plugin tag --dry-run .`; if the Claude Code CLI cannot be installed, it records that reason and instead fails closed on malformed JSON or missing required `name`, `version`, `owner`, or `plugins` manifest fields. On a developer machine with Claude Code available, run the two Claude commands as well.

A change is not complete until every command above exits clean.

---

## External Review Policy

- **Mode**: auto
- **Trusted reviewers**: coderabbit, kilo, github-copilot
- **Required reviewers**: none
- **Ignored reviewers**: none
- **Additional reviewer identities**: none
- **Default wait minutes**: 10
- **Allow automatic review requests**: `coderabbit` only

Automatic re-request is enabled for `coderabbit` alone, decided 2026-09-08. The
lead may post a re-review request for that reviewer without pausing for approval;
every other reviewer still requires explicit approval per
`phases/external-review.md`. The narrow scope is deliberate — it covers the one
reviewer this repository actually uses, and does not become a general licence to
spend review credits.

CodeRabbit reviewed PR #1 in the prior round and is the expected reviewer here.

---

## Execution Routing Policy

Omitted — use the selected backend's lead route for every role.
