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
    ("git", "branch", "--show-current"),
    ("git", "config"),
    ("git", "remote"),
    ("git", "remote", "get-url", "--all"),
    ("git", "remote", "get-url", "--push", "--all"),
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


class _ResolverVisitor(ast.NodeVisitor):
    """Allowlist of behaviour. Everything that could reach a subprocess is denied
    unless the guard can prove it is the single audited chokepoint.

    `subprocess.run` is only allowed inside `read_command` using the `command`
    parameter. `read_command` calls must use a literal list whose prefix is on
    the read-only allowlist. `os`, `functools`, `importlib`, and dynamic
    dispatch (`exec`, `eval`, `getattr`, `__import__`, `partial`) are never
    allowed. The walk is scope-agnostic: module, function, method, lambda,
    comprehension, try/except, and `if __name__` are all treated the same way.
    """

    _ALLOWED_IMPORTS = frozenset({
        "argparse",
        "ast",
        "json",
        "re",
        "subprocess",
        "sys",
    })
    _DANGEROUS_NAMES = frozenset({
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "system",
        "popen",
        "exec",
        "eval",
        "compile",
        "getattr",
        "__import__",
        "execv",
        "execvp",
        "execve",
        "execl",
        "execlp",
        "execle",
        "spawnl",
        "spawnlp",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "getoutput",
        "getstatusoutput",
        "partial",
    })
    _DANGEROUS_MODULES = frozenset({"os", "functools", "importlib"})

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        self._function_stack: list[str] = []
        self._parent_stack: list[ast.AST] = []
        self._sys_aliases: set[str] = set()
        self._sys_modules_aliases: set[str] = set()

    def _disallow(self, message: str) -> None:
        fail(self.errors, message)

    def _current_function(self) -> str | None:
        return self._function_stack[-1] if self._function_stack else None

    def _parent(self) -> ast.AST | None:
        return self._parent_stack[-1] if self._parent_stack else None

    def _is_sys_modules_expr(self, node: ast.AST) -> bool:
        """Return True if *node* is an expression that resolves to sys.modules."""
        if isinstance(node, ast.Attribute):
            return (
                node.attr == "modules"
                and isinstance(node.value, ast.Name)
                and node.value.id in self._sys_aliases
            )
        if isinstance(node, ast.Name):
            return node.id in self._sys_modules_aliases
        return False

    def _is_dangerous_call(self, node: ast.Call) -> bool:
        """Return True if this call can dynamically obtain a subprocess runner."""
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in self._DANGEROUS_NAMES
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return func.value.id in ("subprocess", "os", "functools", "importlib")
        return False

    def generic_visit(self, node: ast.AST) -> None:
        self._parent_stack.append(node)
        super().generic_visit(node)
        self._parent_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._function_stack.append("<lambda>")
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname is not None:
                self._disallow(f"repository resolver must not alias imports: import {alias.name} as {alias.asname}")
                continue
            if alias.name not in self._ALLOWED_IMPORTS:
                self._disallow(f"repository resolver must not import {alias.name}")
            if alias.name == "sys":
                self._sys_aliases.add("sys")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__" or (node.module == "pathlib" and len(node.names) == 1 and node.names[0].name == "Path" and node.names[0].asname is None):
            return
        module = node.module or ""
        if module in self._DANGEROUS_MODULES or module.startswith("subprocess") or module.startswith("os"):
            self._disallow(f"repository resolver must not import from {module}")
            return
        for alias in node.names:
            if alias.asname is not None:
                self._disallow(f"repository resolver must not alias imports: from {module} import {alias.name} as {alias.asname}")
            elif alias.name in self._DANGEROUS_NAMES or alias.name in self._DANGEROUS_MODULES:
                self._disallow(f"repository resolver must not import {alias.name} from {module}")
        if module == "sys":
            for alias in node.names:
                if alias.name == "modules" and alias.asname is None:
                    self._sys_modules_aliases.add(alias.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if self._is_sys_modules_expr(node.value):
                self._sys_modules_aliases.add(target.id)
                self._disallow(f"repository resolver must not alias sys.modules as {target.id}")
            elif isinstance(node.value, ast.Name) and node.value.id in self._sys_aliases:
                self._sys_aliases.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            isinstance(node.target, ast.Name)
            and self._is_sys_modules_expr(node.value)
        ):
            self._sys_modules_aliases.add(node.target.id)
            self._disallow(f"repository resolver must not alias sys.modules as {node.target.id}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self._is_sys_modules_expr(node.value):
            self._disallow("repository resolver must not use sys.modules[...] for dynamic module access")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self._DANGEROUS_MODULES:
            parent = self._parent()
            if not isinstance(parent, ast.Attribute):
                self._disallow(f"repository resolver must not reference {node.id} outside a module attribute")
            return
        if node.id == "subprocess":
            parent = self._parent()
            if not isinstance(parent, ast.Attribute):
                self._disallow("repository resolver must not reference subprocess outside an attribute access")
            return
        if node.id == "read_command":
            parent = self._parent()
            if not (isinstance(parent, ast.Call) and parent.func is node):
                self._disallow("repository resolver must not alias, return, or pass read_command")

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        func = node.func

        if isinstance(func, ast.Call):
            self._disallow("repository resolver must not call a dynamically-obtained callable")
            return

        if isinstance(func, ast.Name):
            if func.id == "read_command":
                first = node.args[0] if node.args else None
                if not isinstance(first, (ast.List, ast.Tuple)):
                    self._disallow("repository resolver read_command calls must use a literal argument list")
                    return
                prefix = _prefix_of_literal_list(first)
                if prefix not in READ_ONLY_PREFIXES:
                    self._disallow(f"repository resolver read_command has disallowed prefix: {prefix!r}")
                return
            if func.id in self._DANGEROUS_NAMES:
                self._disallow(f"repository resolver must not call {func.id}")
                return
            return

        if isinstance(func, ast.Attribute):
            if self._is_sys_modules_expr(func.value):
                self._disallow("repository resolver must not call a method on sys.modules")
                return
            if isinstance(func.value, ast.Name):
                if func.value.id == "subprocess":
                    if func.attr != "run" or self._current_function() != "read_command":
                        self._disallow("repository resolver must only call subprocess.run inside read_command")
                        return
                    first = node.args[0] if node.args else None
                    if not isinstance(first, ast.Name) or first.id != "command":
                        self._disallow("repository resolver subprocess.run must use the read_command `command` parameter")
                    return
                if func.value.id in self._DANGEROUS_MODULES:
                    self._disallow(f"repository resolver must not call {func.value.id}.{func.attr}")
                    return
                return
            if isinstance(func.value, ast.Attribute):
                # Ordinary chained method calls, e.g. text.strip() or completed.stdout.strip().
                return
            if isinstance(func.value, ast.Call) and self._is_dangerous_call(func.value):
                self._disallow("repository resolver must not call a method on a dynamically-obtained subprocess runner")
                return
            # Subscript, Constant, BoolOp, etc. are ordinary expression-based calls.
            return

        self._disallow("repository resolver call target is not a plain name or attribute")


def validate_resolver(resolver_text: str, errors: list[str]) -> None:
    """Ensure the repository resolver only executes read-only commands.

    Two layers: an AST guard over all call/import/name sites, and a coarse
    string-form guard so that prose comments cannot carry disallowed command
    examples either.
    """
    try:
        tree = ast.parse(resolver_text)
    except SyntaxError as exc:
        fail(errors, f"repository resolver is not valid Python: {exc}")
        return

    _ResolverVisitor(errors).visit(tree)

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
