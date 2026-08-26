#!/usr/bin/env python3
"""Validate the distributable /dev Claude Code Skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED = {
    "SKILL.md",
    "phases/phase1.md",
    "phases/phase1-prototyping.md",
    "phases/phase2.md",
    "phases/phase3.md",
    "phases/phase3.5.md",
    "phases/phase4.md",
    "phases/phase5.md",
    "agents/worker-new.md",
    "agents/worker-fix.md",
    "agents/qa-agent.md",
    "agents/worker-prototype-frontend.md",
    "agents/worker-prototype-backend.md",
    "templates/PROJECT_CONTEXT_TEMPLATE.md",
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
            "description:",
            "argument-hint:",
            "disable-model-invocation: true",
        ):
            if field not in text:
                fail(errors, f"SKILL.md frontmatter missing: {field}")

    combined_parts: list[str] = []
    for markdown in sorted(skill_dir.rglob("*.md")):
        content = markdown.read_text(encoding="utf-8")
        combined_parts.append(content)
        if re.search(r"[\u3400-\u9fff]", content):
            fail(errors, f"{markdown.relative_to(skill_dir)} contains Chinese text")
        for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([^`\s)]+)", content):
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
    )
    for token in required_policy:
        if token not in combined:
            fail(errors, f"missing required custom policy: {token}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: validated {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
