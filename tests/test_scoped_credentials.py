"""The credential helper must hand the real secret to exactly one repository.

These drive the helper the way git does -- a `key=value` block on stdin, parsed
output on stdout -- with no network and no real credential anywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "skills" / "dev" / "scripts" / "scoped_credential_helper.py"

CANONICAL = "KHAEntertainment/claude-dev-skill"
REAL_TOKEN = "ghp_realtokenvalue_for_tests_only"
CANARY_USERNAME = "dev-skill-canary"


def run_helper(
    fields: dict[str, str],
    *,
    canonical: str | None = CANONICAL,
    token: str | None = REAL_TOKEN,
    tripwire: Path | None = None,
    action: str = "get",
) -> dict[str, str]:
    block = "".join(f"{key}={value}\n" for key, value in fields.items()) + "\n"
    env = {
        "PATH": os.environ.get("PATH", ""),
        # A PATH without `gh` would make the fallback path indeterminate, so the
        # real token is always supplied explicitly here.
    }
    if canonical is not None:
        env["DEV_CANONICAL_REPO"] = canonical
    if token is not None:
        env["DEV_CANONICAL_TOKEN"] = token
    if tripwire is not None:
        env["DEV_CREDENTIAL_TRIPWIRE"] = str(tripwire)
    completed = subprocess.run(
        [sys.executable, str(HELPER), action],
        input=block,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    parsed: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            parsed[key.strip()] = value
    parsed["_returncode"] = str(completed.returncode)
    return parsed


def isolated_git_env() -> dict[str, str]:
    """A git environment with no inherited global/system config.

    Without this the tests read the developer's real `credential.helper` chain,
    so they pass on a machine with `osxkeychain` and fail on CI without it.
    """
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    # GIT_CONFIG_SYSTEM is not sufficient on Apple Git, which ships a third
    # config inside Xcode (.../git-core/gitconfig) that supplies `osxkeychain`
    # and is not overridden by it. GIT_CONFIG_NOSYSTEM disables all of it.
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_CONFIG_SYSTEM", None)
    return env


def github_fields(path: str, **extra: str) -> dict[str, str]:
    fields = {"protocol": "https", "host": "github.com", "path": path}
    fields.update(extra)
    return fields


class CanonicalRepositoryTests(unittest.TestCase):
    def test_canonical_path_receives_the_real_token(self) -> None:
        result = run_helper(github_fields("KHAEntertainment/claude-dev-skill.git"))
        self.assertEqual(REAL_TOKEN, result["password"])

    def test_canonical_path_without_git_suffix_also_matches(self) -> None:
        result = run_helper(github_fields("KHAEntertainment/claude-dev-skill"))
        self.assertEqual(REAL_TOKEN, result["password"])

    def test_case_differences_do_not_defeat_the_match(self) -> None:
        result = run_helper(github_fields("khaentertainment/CLAUDE-DEV-SKILL.git"))
        self.assertEqual(REAL_TOKEN, result["password"])


class NonCanonicalRepositoryTests(unittest.TestCase):
    """Every one of these must get the canary, never the real secret."""

    HOSTILE = (
        ("fork_parent", "hnaymyh123-henry/claude-dev-skill.git"),
        ("sibling_same_owner", "KHAEntertainment/some-other-repo.git"),
        ("different_owner", "evil-user/claude-dev-skill.git"),
        ("owner_prefix_lookalike", "KHAEntertainment-evil/claude-dev-skill.git"),
        ("nested_path", "KHAEntertainment/claude-dev-skill/extra.git"),
    )

    def test_non_canonical_paths_receive_the_canary(self) -> None:
        for label, path in self.HOSTILE:
            with self.subTest(label):
                result = run_helper(github_fields(path))
                self.assertEqual(CANARY_USERNAME, result["username"], label)
                self.assertNotEqual(REAL_TOKEN, result["password"], label)

    def test_missing_path_is_treated_as_misconfiguration(self) -> None:
        """`credential.useHttpPath` unset means git omits `path` entirely.

        Repository-level discrimination is impossible in that state, so the
        helper must fail closed rather than hand over the real secret.
        """
        result = run_helper({"protocol": "https", "host": "github.com"})
        self.assertEqual(CANARY_USERNAME, result["username"])
        self.assertNotEqual(REAL_TOKEN, result["password"])

    def test_helper_always_answers_so_git_cannot_fall_through(self) -> None:
        """Declining would let git try another helper or prompt a human.

        Either would reintroduce the real credential, so a refusal must take the
        form of an answer git will use and GitHub will reject.
        """
        result = run_helper(github_fields("evil-user/claude-dev-skill.git"))
        self.assertIn("username", result)
        self.assertIn("password", result)
        self.assertTrue(result["password"].strip())


class TripwireTests(unittest.TestCase):
    def test_non_canonical_request_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory, "nested", "tripwire.log")
            run_helper(
                github_fields("hnaymyh123-henry/claude-dev-skill.git"), tripwire=log
            )
            self.assertTrue(log.is_file())
            contents = log.read_text(encoding="utf-8")
            self.assertIn("hnaymyh123-henry/claude-dev-skill", contents)
            self.assertIn(CANONICAL, contents)

    def test_canonical_request_is_not_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory, "tripwire.log")
            run_helper(github_fields("KHAEntertainment/claude-dev-skill.git"), tripwire=log)
            self.assertFalse(log.exists())

    def test_a_secret_never_appears_in_the_tripwire_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory, "tripwire.log")
            run_helper(github_fields("evil-user/x.git"), tripwire=log)
            self.assertNotIn(REAL_TOKEN, log.read_text(encoding="utf-8"))


class OptOutAndActionTests(unittest.TestCase):
    def test_no_canonical_repo_means_the_helper_stays_out_of_the_way(self) -> None:
        """A run that never opted in must not have its credentials altered."""
        result = run_helper(github_fields("anyone/anything.git"), canonical=None)
        self.assertNotIn("password", result)
        self.assertEqual("0", result["_returncode"])

    def test_store_and_erase_are_no_ops(self) -> None:
        for action in ("store", "erase"):
            with self.subTest(action):
                result = run_helper(
                    github_fields("KHAEntertainment/claude-dev-skill.git"), action=action
                )
                self.assertNotIn("password", result)
                self.assertEqual("0", result["_returncode"])


class CheckConfigTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
            env=isolated_git_env(),
        )

    def _check(self, repo: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), "--check-config", "--repo-dir", str(repo)],
            capture_output=True,
            text=True,
            check=False,
            env=isolated_git_env(),
        )

    def test_reports_not_enforced_without_use_http_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-q")
            self._git(repo, "remote", "add", "origin", f"https://github.com/{CANONICAL}.git")
            completed = self._check(repo)
            self.assertEqual(2, completed.returncode)
            self.assertIn("useHttpPath", completed.stderr)

    def test_reports_not_enforced_for_ssh_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-q")
            self._git(repo, "config", "credential.useHttpPath", "true")
            self._git(repo, "config", "credential.helper", f"!python3 {HELPER}")
            self._git(repo, "remote", "add", "origin", f"git@github.com:{CANONICAL}.git")
            completed = self._check(repo)
            self.assertEqual(2, completed.returncode)
            self.assertIn("SSH", completed.stderr)

    def test_reports_enforced_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-q")
            self._git(repo, "config", "credential.useHttpPath", "true")
            self._git(repo, "config", "credential.helper", f"!python3 {HELPER}")
            self._git(repo, "remote", "add", "origin", f"https://github.com/{CANONICAL}.git")
            completed = self._check(repo)
            self.assertEqual(0, completed.returncode)


if __name__ == "__main__":
    unittest.main()


class HelperChainExclusivityTests(unittest.TestCase):
    """Git uses the first helper that answers, so ours must be the only one.

    Found by integration testing, not by unit tests: every unit test above passed
    while a real `git credential fill` still returned the ambient keychain token,
    because an inherited `osxkeychain` helper answered first.
    """

    def _repo(self, directory: str) -> Path:
        repo = Path(directory)
        env = isolated_git_env()
        subprocess.run(
            ["git", "init", "-q"], cwd=repo, check=True, capture_output=True, env=env
        )
        subprocess.run(
            ["git", "config", "credential.useHttpPath", "true"],
            cwd=repo, check=True, capture_output=True, env=env,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", f"https://github.com/{CANONICAL}.git"],
            cwd=repo, check=True, capture_output=True, env=env,
        )
        return repo

    def _add_helper(self, repo: Path, value: str) -> None:
        subprocess.run(
            ["git", "config", "--add", "credential.helper", value],
            cwd=repo, check=True, capture_output=True, env=isolated_git_env(),
        )

    def _check(self, repo: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), "--check-config", "--repo-dir", str(repo)],
            capture_output=True, text=True, check=False, env=isolated_git_env(),
        )

    def test_foreign_helper_before_ours_is_reported_not_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._repo(directory)
            self._add_helper(repo, "osxkeychain")
            self._add_helper(repo, f"!python3 {HELPER}")
            completed = self._check(repo)
            self.assertEqual(2, completed.returncode)
            self.assertIn("answers first", completed.stderr)
            self.assertIn("osxkeychain", completed.stderr)

    def test_empty_reset_before_ours_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._repo(directory)
            self._add_helper(repo, "osxkeychain")
            self._add_helper(repo, "")  # resets the inherited list
            self._add_helper(repo, f"!python3 {HELPER}")
            completed = self._check(repo)
            self.assertEqual(0, completed.returncode, completed.stderr)

    def test_no_helper_at_all_is_reported_not_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._repo(directory)
            completed = self._check(repo)
            self.assertEqual(2, completed.returncode)
            self.assertIn("not configured", completed.stderr)
