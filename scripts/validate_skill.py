#!/usr/bin/env python3
"""Validate the distributable /dev Claude Code Skill."""

from __future__ import annotations

import argparse
import ast
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

# Every command-and-subcommand prefix the repository resolver is permitted to run.
READ_ONLY_PREFIXES = (
    ("git", "remote", "-v"),
    ("gh", "repo", "set-default", "--view"),
    ("gh", "repo", "view"),
)

# Mutating command phrases in prose, used only as a coarse string-form guard.
MUTATING_PROSE = (
    "issue create",
    "issue comment",
    "issue close",
    "pr create",
    "pr comment",
    "pr review",
    "pr merge",
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def _prefix_of_literal_list(node: ast.List | ast.Tuple) -> tuple[str, ...]:
    constants: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            constants.append(element.value)
        else:
            break
    return tuple(constants)


def validate_resolver(resolver_text: str, errors: list[str]) -> None:
    """Ensure the repository resolver only executes read-only commands.

    Two layers: an AST guard over subprocess.run / read_command call sites, and
    a coarse string-form guard so that prose comments cannot carry disallowed
    command examples either.
    """
    try:
        tree = ast.parse(resolver_text)
    except SyntaxError as exc:
        fail(errors, f"repository resolver is not valid Python: {exc}")
        return

    function_stack: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_stack.append(node.name)
            # Every subprocess.run in the file must live inside read_command and
            # use the parameter named `command` (which comes from a literal
            # read_command call site).
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "run"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "subprocess"
                ):
                    first = child.args[0] if child.args else None
                    if node.name != "read_command" or not isinstance(first, ast.Name) or first.id != "command":
                        fail(
                            errors,
                            "repository resolver subprocess.run must live in read_command and use the `command` parameter",
                        )
            function_stack.pop()

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "read_command":
            first = node.args[0] if node.args else None
            if not isinstance(first, (ast.List, ast.Tuple)):
                fail(errors, "repository resolver read_command calls must use a literal argument list")
                continue
            prefix = _prefix_of_literal_list(first)
            if prefix not in READ_ONLY_PREFIXES:
                fail(errors, f"repository resolver read_command has disallowed prefix: {prefix!r}")

    for verb in MUTATING_PROSE:
        if re.search(rf"\b{re.escape(verb)}\b", resolver_text):
            fail(errors, f"repository resolver must stay read-only: {verb}")
    if re.search(r"\bgit\s+push\b", resolver_text):
        fail(errors, "repository resolver must stay read-only: git push")


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []

    for relative in sorted(REQUIRED):
        if not (skill_dir / relative).is_file():
            fail(errors, f"missing required file: {relative}")

    entry = skill_dir / "SKILL.md"
    if entry.is_file():
        text = entry.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            fail(errors, "SKILL.md must begin with YAML frontmatter")

        frontmatter = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
        for field in (
            "name: dev",
            "version:",
            "description:",
            "argument-hint:",
            "when_to_use:",
        ):
            if field not in frontmatter:
                fail(errors, f"SKILL.md frontmatter missing: {field}")

        # The Skill must stay model-invocable so an explicit user request made
        # during planning survives into implementation. Require the explicit
        # `false` rather than an omitted field, so a regression is visible in
        # the diff instead of hiding in a default.
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
        validate_resolver(resolver.read_text(encoding="utf-8"), errors)

    state_template = skill_dir / "templates" / "DEV_STATE_TEMPLATE.md"
    if state_template.is_file():
        state_text = state_template.read_text(encoding="utf-8")
        if not state_text.startswith("---\n") or "\n---\n" not in state_text[4:]:
            fail(errors, "DEV_STATE_TEMPLATE.md must contain YAML frontmatter")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills" / "dev",
    )
    args = parser.parse_args()
    skill_dir = args.skill_dir.resolve()
    errors = validate_skill(skill_dir)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: validated {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
