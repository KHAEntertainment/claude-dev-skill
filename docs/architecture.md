# Architecture Decisions

Decision records for how this Skill is packaged and distributed. The standard
web-application checkpoint items (auth scheme, API design, database schema,
migration framework, API contract) are **not applicable** — this project has no
server, no network API, and no persistent datastore. The decisions that matter
here are packaging and release decisions, recorded below.

---

## ADR-001 — Ship as a Claude Code plugin, alongside the existing installer

- **Decision**: Publish `skills/dev/` as a Claude Code plugin via a marketplace manifest in this repository, while keeping `install.sh` / `install.ps1` working and supported.
- **Decision time**: 2026-08-30
- **Background**: Installing today requires cloning the repo, running a six-command validation gauntlet, and executing a Bash script. Open Issue #1 reports user drop-off during exactly this flow.
- **Consequence**: Plugin skills are always namespaced `<plugin>:<skill>`, so the plugin is invoked as `/dev-skill:dev`. Bare `/dev` remains available only through manual installation — `install.sh` on macOS/Linux or `install.ps1` on Windows. Both may be installed at once, which yields two copies that can drift; this is documented rather than prevented.

## ADR-002 — Repo root is the plugin root

- **Decision**: The repository root *is* the plugin. `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` sit at root; `skills/dev/` is already at the exact path plugin auto-discovery expects.
- **Decision time**: 2026-08-30
- **Background**: The alternative — moving the payload under `plugins/dev-skill/` — would break `install.sh` (`SOURCE_DIR`), `scripts/validate_skill.py` (default `--skill-dir`), and all three Python test files, which resolve `ROOT / "skills" / "dev"`. A duplicated or symlinked copy would guarantee drift.
- **Consequence**: `skills/` is the only auto-discoverable component directory at root. A `bin/`, `commands/`, `agents/`, `hooks/`, or `.mcp.json` appearing at root would be silently picked up by the plugin loader, so CI guards against it.

## ADR-003 — Marketplace entries pin an explicit tag

- **Decision**: The marketplace plugin entry uses an explicit `{"source": "github", "repo": ..., "ref": "vX.Y.Z"}` source rather than the simpler `"./"`.
- **Decision time**: 2026-08-30
- **Background**: A `"./"` source resolves inside the marketplace checkout, which tracks whatever ref the user added it at — defaulting to the repository's default branch. That would make every push to `main` an immediate release to anyone with auto-update enabled.
- **Consequence**: Releases become deliberate, and **the plugin does not resolve until the pinned tag exists and is pushed**. Cutting a release means updating all five version sites in agreement — `skills/dev/SKILL.md` (core version, keeping its `+upstream.<sha>` build metadata), `version` in both `.claude-plugin` manifests, `source.ref` in the marketplace entry, and the git tag — then tagging and verifying the install against a scratch config. The full procedure is [docs/RELEASING.md](RELEASING.md).
- **Transport**: the entry uses `source: "url"` with an explicit `https://` URL rather than `source: "github"` with `owner/repo`. The two behave differently on a machine without a GitHub SSH key: `claude plugin marketplace add` detects unconfigured SSH and falls back to HTTPS, but `claude plugin install` resolving a `github` source clones `git@github.com:...` with **no fallback** and fails `Permission denied (publickey)`. An authenticated `gh` does not help — the transports are independent. Both behaviours were reproduced directly against the live `v2.0.0` tag; the `url` form installs cleanly with no SSH key present. Choosing `url` removes an install prerequisite rather than documenting one.
- **Accepted risk**: the entry pins `ref` only, not a commit `sha`, so a moved tag would silently change what existing users receive. A released tag is therefore treated as immutable by process rather than by mechanism. Pinning `sha` was deferred because it requires writing the commit SHA into the manifest after that commit exists; revisit when release automation can compute it (Issue #6).

## ADR-004 — Release line starts at v2.0.0

- **Decision**: Fork releases use plain semver starting at `v2.0.0`. `skills/dev/SKILL.md` records `2.0.0+upstream.<sha>`, using semver build metadata to retain provenance. The `custom-vX.Y.Z-upstream.SHA` tag scheme is retired.
- **Decision time**: 2026-08-30
- **Background**: Upstream tags `v1.0.0`–`v1.3.0` already exist in this repository's history (`v1.3.0` → `3e87db0`, an ancestor of `main`), and `master` continues to mirror upstream, so upstream publishing `v1.4.0` would be fetched straight into a collision. Plain `v1.x` is unusable.
- **Consequence**: One version string flows to the git tag, both plugin manifests, and the Skill frontmatter. `2.x` is also honest about the divergence from upstream.

## ADR-005 — No compiled language, and no third-party dependencies

- **Decision**: The installer stays in shell and Python. A Go rewrite was considered and rejected.
- **Decision time**: 2026-08-30
- **Background**: Two reasons. First, upstream is Python and Markdown — a Go installer would mean translating upstream changes on every merge. Second, embedding the payload in a compiled binary welds the content version to the binary version, so a Markdown typo fix would require a five-platform cross-compile and release.
- **Consequence**: Homebrew uses a pure-shell formula wrapping `install.sh` in `libexec`, which needs no code changes because `install.sh` derives all paths from `SCRIPT_DIR`. Revisit only if native support for non-Traycer harnesses becomes a real requirement.

## ADR-006 — Dispatched agents receive resolved absolute paths

- **Decision**: The lead resolves `${CLAUDE_SKILL_DIR}` to an absolute path and substitutes it into worker, QA, and reviewer prompts before dispatch. The resolved value is recorded as `skill_dir` in `.agent/dev-state.md` and re-resolved each run.
- **Decision time**: 2026-08-30
- **Background**: The harness expands `${CLAUDE_SKILL_DIR}` when it loads `SKILL.md`, but a prompt file read off disk still contains the raw variable, and dispatched agents do not inherit the environment variable. Previously a delegate could guess `~/.claude/skills/dev/...`; under a plugin the path is version-stamped and unguessable.
- **Consequence**: A pre-existing latent defect, made materially worse by plugin packaging, is fixed at the dispatch boundary rather than by rewriting all 39 sibling references.

## ADR-007 — Homebrew ships from a personal tap, built from source

- **Decision**: A future `KHAEntertainment/homebrew-tap` will carry a source formula with `depends_on "rtk"` and `depends_on "python@3.13"`. No cask, no prebuilt binary.
- **Decision time**: 2026-08-30 (deferred to a follow-up round)
- **Background**: RTK is already in homebrew-core, so the dependency resolves automatically and brew users never hit the missing-RTK abort. A cask of an unsigned prebuilt binary would be quarantined by macOS Gatekeeper, requiring either a fragile `xattr` workaround or paid notarization.
- **Consequence**: Homebrew-core submission is out of scope; a personal tap is the right scale. The formula cannot be written until a tag with a known tarball sha256 exists.

## ADR-008 — Repository identity is a capability question, not a verification question

- **Decision**: Guaranteeing that no GitHub write reaches a non-canonical repository is treated as a question about what the run is *able* to do, not a question about whether each write was checked first. The layers that carry the guarantee are, in order: a credential scoped to the canonical repository so a misroute fails at GitHub's API; an enforcement-liveness preflight that positively verifies those layers are installed and active before the workflow proceeds; and a honeypot corpus that proves, behaviourally, that no fixture scenario writes where it should not. Explicit `--repo OWNER/REPO` scoping on every command remains, but as defence in depth rather than as the guarantee.
- **Decision time**: 2026-09-05
- **Implementation status**: this record is the decision, not a description of `main`. None of the three layers are in place as of this commit. `resolve_repository.py` and `scoped_credential_helper.py` exist only on the unmerged branch `fix/repo-safety-model-invocation`; the liveness preflight and honeypot corpus are not written yet. They land across the two Issue #19 implementation PRs later in this round.
- **Background**: Nine consecutive review rounds tried to establish a negative — that no code path anywhere writes to the wrong repository, and that no prose instruction is misread. Each round fixed the case demonstrated and was blind to the case one step sideways: a `gh` default that was never verified, a `setdefault` that collapsed fetch and push into one URL, a `remote.pushDefault` routing elsewhere while `origin` validated clean, a worker pushing to literal `origin` rather than the validated remote. Three independent design branches, run in isolation, converged on the same reframe. A scoped credential proves a *positive* about capability, which is decidable; if the run holds a token good for exactly one repository, every one of the nine historical defects degrades from a wrong-repository write to an HTTP 403 — loud, unambiguous, and not defeatable by a local interpreter trick, because enforcement happens at GitHub rather than in a parser the agent shares an address space with.
- **Consequence**: Per-run credential scoping through a GitHub App installation token is the strongest form of this decision, but fine-grained PATs cannot be minted programmatically and an App is a real setup tax for a plugin distributed to third parties. That upgrade is deferred to its own decision record; this round ships the canary corpus, the liveness preflight, and behavioural fixtures. SSH origins are rewritten to HTTPS in a per-run `GIT_CONFIG_GLOBAL` rather than refused, because an SSH remote never consults a credential helper at all and would silently bypass the credential layer this ADR depends on; if the rewrite cannot be positively verified, the preflight hard-stops the workflow rather than the individual write. Acceptance criteria for identity work are written against the hazard — no write reaches a non-canonical repository, by any path — and never against a mechanism, because every previous round wrote mechanism-shaped criteria and the hazard survived one step sideways.

## ADR-009 — The read-only AST guard is a CI-time authorship lint, not a security control

- **Decision**: The AST guard in `scripts/validate_skill.py` is reclassified as a lint that constrains what this repository's own authors ship. It is not a runtime security boundary, and it is not the control that keeps a misrouted write from landing. Behavioural enforcement — recording stubs that observe actual execution, plus the credential layer in ADR-008 — is the real control. **Planned, not yet in place:** CI will report guard-too-strict and guard-too-loose as separately named checks, so that over-correction in either direction is visible at a glance. Today CI runs the validator as a single `Validate the distributable Skill` step; the split lands with the implementation PR for Issue #17.
- **Decision time**: 2026-09-05
- **Background**: The guard cannot be made provably complete against Python's dynamic dispatch, and one residual bypass is known and documented rather than patched (a `staticmethod` binding on a class attribute passes validation while executing a real `git push`). Five of the nine failed identity rounds were spent chasing interpreter escapes — `getattr`, `__import__`, `exec`, `os.execvp`, `sys.modules`, `functools.partial`, `pty`, `ctypes` — inside a script the maintainers themselves write. Enumeration is the losing side of that game: the attacker picks the spelling. The threat model also does not support treating it as a boundary, because every remaining bypass requires someone deliberately hiding a mutating call in the resolver, which is a code-review threat rather than an accident.
- **Consequence**: Guard work is capped. Effort moves to broadening behavioural coverage, which catches what static analysis structurally cannot and is spelling-agnostic. If the guard is revisited, the preferred direction is restricting the resolver's module surface — asserting it imports nothing outside an allowlist and binds no unexpected module-level names — rather than enumerating call spellings. **Planned, not yet in place:** the reclassification will also be recorded in `skills/dev/backends/contract.md`, where the delegated lanes actually read it — this PR changes no payload file. That placement is deliberate rather than incidental: it exists so a future round does not re-litigate the question and spend another five review cycles on it.
