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
import subprocess
from pathlib import Path


def read_command(command, *, cwd):
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)


def collect_remotes(repo_dir):
    return read_command(["git", "remote", "-v"], cwd=repo_dir)


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

    def test_allows_read_only_git_remote_v(self) -> None:
        errors = self.validate(READ_ONLY_RESOLVER)
        self.assertEqual([], errors)

    def test_rejects_injected_read_command_git_push(self) -> None:
        source = READ_ONLY_RESOLVER.replace(
            '["git", "remote", "-v"]',
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

    def test_rejects_subprocess_run_git_push(self) -> None:
        source = READ_ONLY_RESOLVER.replace(
            "return subprocess.run(command,",
            'return subprocess.run(["git", "push"],',
        )
        errors = self.validate(source)
        self.assertTrue(
            any("subprocess.run" in e for e in errors) or any("disallowed prefix" in e for e in errors)
        )

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
