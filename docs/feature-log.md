# Feature Log

## Completed

- CI Verification Gate: 6 jobs across ubuntu/macos/windows, archive validation,
  and packaging guards (PR #11, merged 2026-08-31)
- Plugin-root and version-sync guard scripts (PR #10, merged 2026-08-31)
- v2.0.1 release: HTTPS marketplace source, no SSH key required (PR #8/#9, merged 2026-08-31)
- Claude Code plugin distribution and v2.0.0 version scheme (PR #7, merged 2026-08-30)
- Traycer execution backend v1 (PR #1, merged 2026-08-30)
- External review oversight gate (commit `6ad111b`)
- Validated atomic Skill distribution installer (commit `ad6101a`)

## Retro — claude-dev-skill / v2.0.x Distribution

### Completed

- Claude Code plugin distribution. `skills/dev/` ships as a plugin from the
  repository root; installable in two commands and verified working end to end
  on a machine with no GitHub SSH key.
- `v2.0.0` release line adopted, resolving a collision with upstream's `v1.x`
  tags that live in this fork's history. `v2.0.1` is current.
- Two stdlib-only packaging guards, both with proven failure modes.
- The repository's first CI: 6 jobs across ubuntu/macos/windows, validating the
  extracted release archive as well as the working tree.
- A documented release procedure, which did not previously exist.
- A latent dispatch defect fixed: dispatched agents do not inherit
  `${CLAUDE_SKILL_DIR}`, which plugin packaging would have made unguessable.

### Known Issues

- `README.zh.md` carries an outdated banner but its body is still wrong.
- The plugin-root component list is defined by Claude Code, not by this repo, and
  can grow without notice.
- `install.ps1` remains under-tested relative to `install.sh` (5 assertions vs 9).

### Deferred

- Homebrew tap (ADR-007). Now unblocked: it needs a tagged tarball, and `v2.0.1`
  exists.
- PyPI packaging. Note the exec-bit hazard — wheels do not preserve file modes,
  and `detect_execution_backend.py` must stay 755.
- Issue #3, adapter-level report-back enforcement. Its stated precondition was
  the contract surviving real lanes; six lanes this iteration all produced clean
  reports, so that precondition is now met.

### Recommended Next Priorities

1. Homebrew tap — smallest remaining distribution gap, and now unblocked.
2. Issue #3 — the lead hand-rolled reply correlation six times this iteration and
   got it wrong three times. Mechanical enforcement at `observe` would remove
   that whole class of error.
3. `README.zh.md` — retranslate or delete; a banner is a stopgap.

## Known Tech Debt

- Phase-level role prompts are not covered by the reviewer/QA distinctness
  regression test. `test_qa_and_reviewer_are_distinct_clean_current_head_lanes`
  asserts the wording in the agent docs and loads the phase docs, but does not
  assert against them — so future propagation drift would go undetected.
  (source: PR #1 re-review, recorded 2026-08-30)
- `README.zh.md` is stale and contradicts the current installer: it still
  documents the upstream bilingual *command* install and advertises
  `install.sh --lang zh`, which `install.sh:60` now rejects. Its prerequisites
  table also omits RTK and Python. **Mitigated** as of PR #7 with a bilingual
  outdated/unsupported banner directing readers to the English README; the body
  itself is still wrong and either needs retranslation or deletion.
  (recorded 2026-08-30, mitigated 2026-08-31)
- `install.sh` has no uninstall path. Recovery from a bad install is a manual
  restore out of `~/.claude/backups/dev/<timestamp>/`. (recorded 2026-08-30)
- `install.ps1` is under-tested relative to `install.sh`: 5 assertions versus 9.
  It lacks the symlink-refusal, broken-distribution, and idempotent-rerun cases.
  (recorded 2026-08-30)
- `--migrate-legacy` and `--keep-legacy` are accepted by `install.sh` but absent
  from its `usage()` output. (recorded 2026-08-30)
- ~~The advertised plugin install path has not been verified end to end.~~
  **Resolved 2026-08-31**: verified against the live `v2.0.0` tag in an isolated
  `CLAUDE_CONFIG_DIR`. Installs cleanly with no SSH key present; payload is 23
  files, version `2.0.0+upstream.3e87db0`, exec bits preserved (755 detector /
  644 inspector, matching git modes), and the detector executes from the
  installed copy.
- `README.zh.md` carries an outdated banner but its body is still wrong.
  Retranslate or delete. (recorded 2026-08-31)
- The plugin-root guard checks the 11 documented auto-discovered components as of
  2026-08-31. That list is defined by Claude Code, not by this repo, so it can
  grow without notice. Re-check it against
  https://code.claude.com/docs/en/plugins-reference on each upstream sync.
  (recorded 2026-08-31)
- CI installs a pinned `@anthropic-ai/claude-code@2.1.251` to run strict manifest
  validation. The pin needs periodic review: too old and it stops matching the
  format the runtime actually enforces. (recorded 2026-08-31)
