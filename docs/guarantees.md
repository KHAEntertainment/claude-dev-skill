# Guarantees

The rules every `/dev` run follows, and the boundaries it keeps with each tool it works alongside.

## Standing guarantees

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

See [the full audit](AUDIT.md), [upstream maintenance procedure](../UPSTREAM.md), and [custom changelog](../CHANGELOG.custom.md).

## Integration boundaries

These are the third-party systems `/dev` invokes or composes with at runtime. RTK, Traycer, Graft, and CodeRabbit are wired into the Skill payload (`skills/dev/`) and gated by the verification harness. i-have-adhd is a documented composition only: the payload deliberately names no brevity skill (see [`dogfooding.md`](dogfooding.md#i-have-adhd)).

- **[RTK](https://github.com/rtk-ai/rtk)** — command transport for every shell, Git, GitHub, test, and lint invocation the Skill runs. Hard prerequisite at install time (the `command -v rtk` preflight in [`install.sh`](../install.sh)); ambient thereafter and never version-checked at runtime.
- **[Traycer](https://github.com/traycerai/traycer)** — optional multi-harness execution backend. The lead loads the Traycer adapter at [`skills/dev/backends/traycer.md`](../skills/dev/backends/traycer.md) only when detection returns `traycer`: both `TRAYCER_AGENT_ID` and `TRAYCER_EPIC_ID` in the environment, or, with neither present, a valid supplied `.agent/traycer.env`. Anything else is `incomplete`; `claude-native` is never a fallback, only a lead-resolved choice for a known native Claude Code session (see [Detection and fail-closed behavior](backends.md#detection-and-fail-closed-behavior)). Capability-verified: any gap in a child harness surfaces as `incomplete`, not as a silent fallback.
- **[i-have-adhd](https://github.com/ayghri/i-have-adhd)** — *composes with*, **not depends on**. A session brevity skill that `/dev` aligns with at the end-of-turn reply layer ([`skills/dev/reply-contract.md`](../skills/dev/reply-contract.md) §6): `/dev` never claims a task-requirements override to justify verbosity. Per-session activation is required to enable i-have-adhd; `/dev` does not install, invoke, or require it.
- **[Graft](https://github.com/trailhq/Graft) (`@nanonets/graft@0.18.0`)** — pinned optional code-graph evidence CLI used at gates via `rtk proxy graft`. Never an execution backend; `/dev` never runs `graft init` in a managed project. See [`skills/dev/graft.md`](../skills/dev/graft.md).
- **[CodeRabbit](https://github.com/coderabbitai)** — trusted external reviewer for Phase 4 oversight ([`skills/dev/phases/external-review.md`](../skills/dev/phases/external-review.md)). Substituted after the rate-limit breakpoint (#48) with a family-distinct reviewer from the review fallback chain; the substitute reviewer must post a real verdict — a clear status field is not a review.

## Concepts we learned from

These are systems `/dev` does *not* install. We borrow a discipline, cite the project that taught it to us, and stop there.

- **[Ponytail](https://github.com/dietrichgebert/ponytail)** by Dietrich Gebert — the reuse-first ladder borrowed in PR #30 (Issue #20); a calibration experiment is planned in open Issue #43 (v2.1.2). Also cited in [`architecture.md`](architecture.md) as the source of the config-leak problem that bounds the native non-Claude lead escape hatch. Not installed; `/dev` adapts the ladder only.
- The dogfooding distillation ([`dogfooding.md`](dogfooding.md), Issue #40 / PR #63) is `/dev`'s own codification, not a borrowed system — its first seven lessons came from the v2.1.0 recovery log, and it is the method source for the rate-limit breakpoint (#48).
