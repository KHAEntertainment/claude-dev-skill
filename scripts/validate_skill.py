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
        "review evidence alone never establishes satisfaction",
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
        "A trusted reviewer's status check alone never satisfies this gate.",
        # Reuse-first ladder and its safety carve-out. The carve-out is pinned
        # as a full sentence: a ladder that survives without it reads as
        # licence to delete guards in the name of minimality.
        "Reuse-first ladder",
        "lowest rung",
        "Minimizing scope must never mean removing a guard.",
        "speculative abstraction",
        # Completion-evidence discipline. `qa-agent.md` holds the canonical
        # definition of "verified"; `report-back.md` cross-references it.
        "Tool Capability Boundary",
        "executed command's actual output",
        "re-run the full Verification Gate",
        # QA scoring: absence of signal must not read as a positive result.
        # Each token pins one path by which a lane that measured nothing could
        # otherwise return a passing number.
        "qa_error: no acceptance criteria",
        "qa_error: no verification executed",
        "No test framework detected",
        "not verified by test execution",
        "Limitations are load-bearing",
        # The coverage term swings 10 points per criterion, so the predicate
        # deciding it must stay decidable. Without these two the term degrades
        # into a self-assessed judgment and two lanes scoring the same PR can
        # legitimately reach different numbers.
        "Test-executable is a decidable predicate",
        "without new infrastructure",
        # A failed criterion already lowers the ratio; deducting coverage on
        # top of it counts the same fact twice and fails legitimate work for
        # arithmetic reasons. Found by the formula's first real use.
        "The coverage term applies only to criteria that passed.",
    )
    for token in required_policy:
        if token not in combined:
            fail(errors, f"missing required custom policy: {token}")

    detector = skill_dir / "scripts" / "detect_execution_backend.py"
    if detector.is_file():
        detector_text = detector.read_text(encoding="utf-8")
        if "shutil.which" in detector_text or "command -v" in detector_text:
            fail(errors, "backend detector must not probe binary presence")

    # `required_policy` above is matched against the Skill's own markdown, so it
    # structurally cannot pin a sentence in the repo-root `PROJECT_CONTEXT.md`.
    # Routing policy lives there and outranks the agent selection guide in the
    # adapter's resolution order, so a silent revert re-overrides newer policy
    # with a stale route. Anchor on this script's own location rather than on
    # `--skill-dir`: every call site stages the Skill elsewhere but always runs
    # this validator from the project or archive root, where the file ships.
    # Absence fails closed — an unreadable policy is not a satisfied one.
    project_context = Path(__file__).resolve().parents[1] / "PROJECT_CONTEXT.md"
    if not project_context.is_file():
        fail(errors, "missing required file: PROJECT_CONTEXT.md")
    else:
        project_text = project_context.read_text(encoding="utf-8")
        for token in (
            "The agent selection guide governs role routing.",
            "outranks the guide in the adapter's resolution order",
            "the lead runs on the `claude` harness",
            "provider-neutral",
        ):
            if token not in project_text:
                fail(errors, f"PROJECT_CONTEXT.md missing routing policy: {token}")

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
