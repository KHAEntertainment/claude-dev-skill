#!/usr/bin/env python3
"""Validate the distributable /dev Claude Code Skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED = {
    "SKILL.md",
    "backends/contract.md",
    "backends/claude-native.md",
    "backends/traycer.md",
    "phases/phase1.md",
    "phases/phase1-prototyping.md",
    "phases/phase2.md",
    "phases/phase3.md",
    "phases/phase3.5.md",
    "phases/external-review.md",
    "phases/phase4.md",
    "phases/phase5.md",
    "agents/report-back.md",
    "agents/worker-new.md",
    "agents/worker-fix.md",
    "agents/qa-agent.md",
    "agents/reviewer.md",
    "agents/worker-prototype-frontend.md",
    "agents/worker-prototype-backend.md",
    "templates/PROJECT_CONTEXT_TEMPLATE.md",
    "templates/DEV_STATE_TEMPLATE.md",
    "scripts/detect_execution_backend.py",
    "scripts/inspect_external_reviews.py",
    "scripts/resolve_repository.py",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills" / "dev",
    )
    args = parser.parse_args()
    skill_dir = args.skill_dir.resolve()
    errors: list[str] = []

    for relative in sorted(REQUIRED):
        if not (skill_dir / relative).is_file():
            fail(errors, f"missing required file: {relative}")

    entry = skill_dir / "SKILL.md"
    if entry.is_file():
        text = entry.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            fail(errors, "SKILL.md must begin with YAML frontmatter")
        for field in (
            "name: dev",
            "version:",
            "description:",
            "argument-hint:",
            "when_to_use:",
        ):
            if field not in text:
                fail(errors, f"SKILL.md frontmatter missing: {field}")

        # The Skill must stay model-invocable so an explicit user request made
        # during planning survives into implementation. Require the explicit
        # `false` rather than an omitted field, so a regression is visible in
        # the diff instead of hiding in a default.
        frontmatter = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
        if "disable-model-invocation: false" not in frontmatter:
            fail(
                errors,
                "SKILL.md must set `disable-model-invocation: false` explicitly; "
                "model invocation is required for the plan-to-implementation handoff",
            )
        when_to_use = ""
        for line in frontmatter.splitlines():
            if line.startswith("when_to_use:"):
                when_to_use = line.partition(":")[2].strip().strip('"').strip("'")
                break
        for phrase in ("explicitly", "after plan approval", "Do not invoke"):
            if phrase not in when_to_use:
                fail(
                    errors,
                    f"SKILL.md `when_to_use` must keep the explicit-intent trigger: {phrase}",
                )

    combined_parts: list[str] = []
    for markdown in sorted(skill_dir.rglob("*.md")):
        content = markdown.read_text(encoding="utf-8")
        combined_parts.append(content)
        if re.search(r"[\u3400-\u9fff]", content):
            fail(errors, f"{markdown.relative_to(skill_dir)} contains Chinese text")
        for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([^`\s)'\"]+)", content):
            if not (skill_dir / ref).is_file():
                fail(errors, f"{markdown.relative_to(skill_dir)} references missing file: {ref}")

    combined = "\n".join(combined_parts)
    forbidden = {
        "~/.claude/commands/dev": "legacy command path",
        "TeamCreate": "obsolete Agent Teams setup tool",
        "TeamDelete": "obsolete Agent Teams cleanup tool",
        "/Users/bbrenner": "machine-specific absolute path",
    }
    for token, description in forbidden.items():
        if token in combined:
            fail(errors, f"found {description}: {token}")

    required_policy = (
        "Never write or modify implementation or test code directly",
        ".agent/dev-state.md",
        "pre-created, verified branch/worktree",
        "RTK",
        "coderabbit",
        "kilo",
        "github-copilot",
        "copilot-pull-request-reviewer[bot]",
        "headRefOid",
        "Default wait minutes",
        "Allow automatic review requests",
        "--trusted-reviewer",
        "false_positive",
        "incomplete",
        "TRAYCER_AGENT_ID",
        "TRAYCER_EPIC_ID",
        "claude-native",
        "rtk proxy traycer",
        "--surface gui",
        "--expect-reply",
        "--workspace-entry",
        "--carry-uncommitted",
        "traycer_last_used",
        "schema_version",
        "communication_response_id",
        "head changed",
        "distinct agent ID",
        "lead is the sole ledger writer",
        "scripts/resolve_repository.py",
        "repository.canonical",
        "--repo OWNER/REPO",
        "positional `OWNER/REPO` argument",
        "default_conflicts_with_origin",
        "ambiguous_default",
    )
    for token in required_policy:
        if token not in combined:
            fail(errors, f"missing required custom policy: {token}")

    detector = skill_dir / "scripts" / "detect_execution_backend.py"
    if detector.is_file():
        detector_text = detector.read_text(encoding="utf-8")
        if "shutil.which" in detector_text or "command -v" in detector_text:
            fail(errors, "backend detector must not probe binary presence")

    resolver = skill_dir / "scripts" / "resolve_repository.py"
    if resolver.is_file():
        resolver_text = resolver.read_text(encoding="utf-8")
        for verb in (
            "issue create",
            "issue comment",
            "issue close",
            "pr create",
            "pr comment",
            "pr review",
            "pr merge",
            "push",
        ):
            if verb in resolver_text:
                fail(errors, f"repository resolver must stay read-only: {verb}")

    state_template = skill_dir / "templates" / "DEV_STATE_TEMPLATE.md"
    if state_template.is_file():
        state_text = state_template.read_text(encoding="utf-8")
        if not state_text.startswith("---\n") or "\n---\n" not in state_text[4:]:
            fail(errors, "DEV_STATE_TEMPLATE.md must contain YAML frontmatter")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: validated {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
