# Feature Log

## Completed

- Traycer execution backend v1 (PR #1, merged 2026-08-30)
- External review oversight gate (commit `6ad111b`)
- Validated atomic Skill distribution installer (commit `ad6101a`)

## Known Tech Debt

- Phase-level role prompts are not covered by the reviewer/QA distinctness
  regression test. `test_qa_and_reviewer_are_distinct_clean_current_head_lanes`
  asserts the wording in the agent docs and loads the phase docs, but does not
  assert against them — so future propagation drift would go undetected.
  (source: PR #1 re-review, recorded 2026-08-30)
- `README.zh.md` is stale and contradicts the current installer: it still
  documents the upstream bilingual *command* install and advertises
  `install.sh --lang zh`, which `install.sh:60` now rejects. Its prerequisites
  table also omits RTK and Python. (recorded 2026-08-30)
- `install.sh` has no uninstall path. Recovery from a bad install is a manual
  restore out of `~/.claude/backups/dev/<timestamp>/`. (recorded 2026-08-30)
- `install.ps1` is under-tested relative to `install.sh`: 5 assertions versus 9.
  It lacks the symlink-refusal, broken-distribution, and idempotent-rerun cases.
  (recorded 2026-08-30)
- `--migrate-legacy` and `--keep-legacy` are accepted by `install.sh` but absent
  from its `usage()` output. (recorded 2026-08-30)
