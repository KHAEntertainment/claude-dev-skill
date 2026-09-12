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
artifact is `skills/dev/` — 22 files of Markdown plus four stdlib-only Python
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
- No absolute home-directory paths anywhere in shipped Markdown — the payload, `en/`, `zh/`, and root-level docs alike (enforced by the validator, which tolerates `en/`/`zh/` being absent from a release archive).
- `bin/` must never exist at repo root — Claude Code plugin auto-discovery would add it to the Bash tool PATH.

---

## Current Status

- **Last updated**: 2026-09-11
- **Current iteration goal**: v2.1.0 content complete: report-back enforcement (#32), bounded review recovery (#35), and configured repository/account verification (#36) are merged. Release preparation is separate; the release PR, tag, and post-tag installation still require their remaining approvals/checks.
- **Architecture decisions this round**: ADR-010 supersedes ADR-008 with verification before supported writes using existing credentials. The GitHub App, canary credential helper, per-run SSH rewrite, and liveness-preflight design are rejected. ADR-009 classifies the AST guard as an authorship lint; #17 and #38 remain deferred.
- **Next iteration**: planned controlled ScadForge issue #48 run in a fresh session after the tag, subject to separate start authorization. Homebrew tap remains debt (#39, ADR-007); live SSH verification is #37 and dogfooding distillation is #40.
- **Open PRs**: see `gh pr list`; release preparation follows the completed content stack.
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

The agent selection guide governs role routing. This file records only
project-specific exceptions, and there are none. Do not restate the guide's
model or harness choices here, even to agree with them: a route recorded in this
section outranks the guide in the adapter's resolution order, so anything
written here silently overrides newer policy, and a copy made today becomes a
stale override the moment the guide changes. That is why this section stays
empty.

One constraint does belong here, because it is a property of this project rather
than a routing preference: **the lead runs on the `claude` harness, because the
lead is what invokes `/dev`.** Worker, QA, and reviewer assignments are
provider-neutral and may run on whichever harness and model the selection guide
selects for them.
