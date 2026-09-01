from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_skill.py"
SPEC = importlib.util.spec_from_file_location("validate_skill", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


READ_ONLY_RESOLVER = '''
from __future__ import annotations
import subprocess
from pathlib import Path


def read_command(command, *, cwd):
    return subprocess.run(command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)


def collect_branch(repo_dir):
    return read_command(["git", "branch", "--show-current"], cwd=repo_dir)


def collect_config(repo_dir, key):
    return read_command(["git", "config", key], cwd=repo_dir)


def collect_remote_names(repo_dir):
    return read_command(["git", "remote"], cwd=repo_dir)


def collect_fetch_urls(repo_dir, name):
    return read_command(["git", "remote", "get-url", "--all", name], cwd=repo_dir)


def collect_push_urls(repo_dir, name):
    return read_command(["git", "remote", "get-url", "--push", "--all", name], cwd=repo_dir)


def collect_gh_default(repo_dir):
    return read_command(["gh", "repo", "set-default", "--view"], cwd=repo_dir)


def collect_verified_name(repo_dir, repository):
    return read_command(["gh", "repo", "view", repository, "--json", "nameWithOwner"], cwd=repo_dir)
'''


class ValidateResolverGuardTests(unittest.TestCase):
    def validate(self, source: str) -> list[str]:
        errors: list[str] = []
        MODULE.validate_resolver(source, errors)
        return errors

    def test_allows_unmodified_resolver(self) -> None:
        self.assertEqual([], self.validate(READ_ONLY_RESOLVER))

    def test_rejects_injected_read_command_git_push(self) -> None:
        source = READ_ONLY_RESOLVER.replace(
            '["git", "branch", "--show-current"]',
            '["git", "push"]',
        )
        errors = self.validate(source)
        self.assertTrue(any("disallowed prefix" in e for e in errors))

    def test_rejects_injected_gh_issue_create(self) -> None:
        source = READ_ONLY_RESOLVER.replace(
            '["gh", "repo", "set-default", "--view"]',
            '["gh", "issue", "create"]',
        )
        errors = self.validate(source)
        self.assertTrue(any("disallowed prefix" in e for e in errors))

    def test_rejects_subprocess_run_at_module_scope(self) -> None:
        source = READ_ONLY_RESOLVER + '\nsubprocess.run(["gh", "pr", "merge", "15"])\n'
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_subprocess_run_in_nested_function(self) -> None:
        source = READ_ONLY_RESOLVER + '''
def outer():
    def inner():
        subprocess.run(["gh", "pr", "merge", "15"])
'''
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_subprocess_run_in_class_method(self) -> None:
        source = READ_ONLY_RESOLVER + '''
class Helper:
    def merge(self):
        subprocess.run(["gh", "pr", "merge", "15"])
'''
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_subprocess_run_in_lambda(self) -> None:
        source = READ_ONLY_RESOLVER + '''
merge = lambda: subprocess.run(["gh", "pr", "merge", "15"])
'''
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_subprocess_run_in_comprehension(self) -> None:
        source = READ_ONLY_RESOLVER + '''
[subprocess.run(["gh", "pr", "merge", str(n)]) for n in range(1)]
'''
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_subprocess_run_in_try_block(self) -> None:
        source = READ_ONLY_RESOLVER + '''
def maybe_merge():
    try:
        subprocess.run(["gh", "pr", "merge", "15"])
    except Exception:
        pass
'''
        errors = self.validate(source)
        self.assertTrue(any("subprocess.run" in e for e in errors))

    def test_rejects_os_system_at_module_scope(self) -> None:
        source = READ_ONLY_RESOLVER + '\nimport os\nos.system("gh pr merge 15")\n'
        errors = self.validate(source)
        self.assertTrue(any("must not import" in e or "must not call" in e for e in errors))

    def test_rejects_os_popen_in_try_block(self) -> None:
        source = READ_ONLY_RESOLVER + '''
import os

def preview():
    try:
        os.popen("gh pr merge 15")
    except Exception:
        pass
'''
        errors = self.validate(source)
        self.assertTrue(any("must not call" in e for e in errors))

    def test_rejects_import_subprocess_aliased(self) -> None:
        source = READ_ONLY_RESOLVER.replace("import subprocess", "import subprocess as _sp\n_sp.run([\"gh\",\"pr\",\"merge\"])")
        errors = self.validate(source)
        self.assertTrue(any("must not alias" in e for e in errors))

    def test_rejects_from_subprocess_import_run_aliased(self) -> None:
        source = READ_ONLY_RESOLVER.replace("import subprocess", "from subprocess import run as _go\n_go([\"gh\",\"pr\",\"merge\"])")
        errors = self.validate(source)
        self.assertTrue(any("must not import" in e for e in errors))

    def test_rejects_getattr_subprocess(self) -> None:
        source = READ_ONLY_RESOLVER + '\ngetattr(subprocess, "run")(["gh", "pr", "merge"])\n'
        errors = self.validate(source)
        self.assertTrue(any("getattr" in e for e in errors))

    def test_rejects_dunder_import(self) -> None:
        source = READ_ONLY_RESOLVER + '\n__import__("subprocess").run(["gh", "pr", "merge"])\n'
        errors = self.validate(source)
        self.assertTrue(any("__import__" in e for e in errors))

    def test_rejects_exec_string(self) -> None:
        source = READ_ONLY_RESOLVER + '\nexec("import subprocess; subprocess.run([\\\"gh\\\", \\\"pr\\\", \\\"merge\\\"])")\n'
        errors = self.validate(source)
        self.assertTrue(any("exec" in e for e in errors))

    def test_rejects_read_command_alias(self) -> None:
        source = READ_ONLY_RESOLVER + '''
rc = read_command
rc(["git", "push"])
'''
        errors = self.validate(source)
        self.assertTrue(any("must not alias" in e for e in errors))

    def test_rejects_functools_partial(self) -> None:
        source = READ_ONLY_RESOLVER + '''
import functools
p = functools.partial(read_command, ["git", "push"])
p()
'''
        errors = self.validate(source)
        self.assertTrue(any("must not call" in e or "partial" in e for e in errors))

    def test_rejects_string_forms(self) -> None:
        source = READ_ONLY_RESOLVER + '\n"gh issue create"\n"git push"\n'
        errors = self.validate(source)
        self.assertTrue(any("issue create" in e for e in errors))
        self.assertTrue(any("git push" in e for e in errors))

    def test_allows_legitimate_push_url_terminology(self) -> None:
        """`push_url` and `remote_url_mismatch` are not mutations."""
        source = READ_ONLY_RESOLVER + "\npush_url = 1\nremote_url_mismatch = 2\n"
        errors = self.validate(source)
        self.assertEqual([], errors)


class ValidateSkillIntegrationTests(unittest.TestCase):
    def test_real_skill_passes(self) -> None:
        skill_dir = ROOT / "skills" / "dev"
        errors = MODULE.validate_skill(skill_dir)
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
