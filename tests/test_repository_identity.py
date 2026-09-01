from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "skills" / "dev" / "scripts" / "resolve_repository.py"
SPEC = importlib.util.spec_from_file_location("resolve_repository", RESOLVER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANONICAL = "KHAEntertainment/claude-dev-skill"
PARENT = "hnaymyh123-henry/claude-dev-skill"
ORIGIN_HTTPS = "https://github.com/KHAEntertainment/claude-dev-skill.git"
UPSTREAM_HTTPS = "https://github.com/hnaymyh123-henry/claude-dev-skill.git"

# HTTP-method tokens are the only ones that appear as argv tokens, not phrases.
MUTATING_TOKENS = (
    "POST",
    "PATCH",
    "PUT",
    "--method",
)

MUTATING_PHRASES = (
    r"\bgit\s+push\b",
    r"\bgh\s+issue\s+create\b",
    r"\bgh\s+issue\s+comment\b",
    r"\bgh\s+pr\s+create\b",
    r"\bgh\s+pr\s+comment\b",
    r"\bgh\s+pr\s+review\b",
    r"\bgh\s+pr\s+merge\b",
)

# Read-only command shapes the resolver may emit. Each entry is
# (leading-constant-tokens, min-extra-args, max-extra-args); max=None means
# the command may have any number of trailing flags.
READ_ONLY_COMMANDS = (
    (("git", "branch", "--show-current"), 0, 0),
    (("git", "config"), 1, 1),
    (("git", "remote"), 0, 0),
    (("git", "remote", "get-url", "--all"), 1, 1),
    (("git", "remote", "get-url", "--push", "--all"), 1, 1),
    (("gh", "repo", "set-default", "--view"), 0, 0),
    (("gh", "repo", "view"), 1, None),
)

# Generic git/gh stub. The test sets FIXTURE (JSON) in the environment.
STUB = """#!{python}
import json
import os
import sys

with open(os.environ["REPO_IDENTITY_LOG"], "a", encoding="utf-8") as handle:
    handle.write("\\t".join([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")

fixture = json.loads(os.environ.get("FIXTURE", "{{}}"))
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]

if name == "git" and args == ["branch", "--show-current"]:
    print(fixture.get("branch", "main"))
    raise SystemExit(0)

if name == "git" and args[0] == "config":
    key = args[1]
    value = fixture.get("config", {{}}).get(key, "")
    if value:
        print(value)
        raise SystemExit(0)
    raise SystemExit(1)

if name == "git" and args == ["remote"]:
    for remote in fixture.get("remotes", {{}}):
        print(remote)
    raise SystemExit(0)

if name == "git" and args[:3] == ["remote", "get-url", "--all"]:
    remote = args[3]
    for url in fixture.get("remotes", {{}}).get(remote, {{}}).get("fetch", []):
        print(url)
    raise SystemExit(0)

if name == "git" and args[:4] == ["remote", "get-url", "--push", "--all"]:
    remote = args[4]
    for url in fixture.get("remotes", {{}}).get(remote, {{}}).get("push", []):
        print(url)
    raise SystemExit(0)

if name == "gh" and args == ["repo", "set-default", "--view"]:
    default = fixture.get("gh_default", "")
    if default and not default.lower().startswith("no default"):
        print(default)
        raise SystemExit(0)
    # Real gh reports a missing default on stderr with exit 0.
    sys.stderr.write((default or "no default repository has been set") + "\\n")
    raise SystemExit(0)

if name == "gh" and args[:2] == ["repo", "view"]:
    print(args[2])
    raise SystemExit(0)

sys.stderr.write("unexpected command\\n")
raise SystemExit(1)
"""


class RemoteNormalizationTests(unittest.TestCase):
    def test_https_and_ssh_forms_normalize_identically(self) -> None:
        equivalent = (
            "https://github.com/KHAEntertainment/claude-dev-skill.git",
            "https://github.com/KHAEntertainment/claude-dev-skill",
            "https://github.com/KHAEntertainment/claude-dev-skill/",
            "http://github.com/KHAEntertainment/claude-dev-skill.git",
            "https://KHAEntertainment@github.com/KHAEntertainment/claude-dev-skill.git",
            "git@github.com:KHAEntertainment/claude-dev-skill.git",
            "git@github.com:KHAEntertainment/claude-dev-skill",
            "ssh://git@github.com/KHAEntertainment/claude-dev-skill.git",
            "ssh://git@github.com:22/KHAEntertainment/claude-dev-skill.git",
            "git://github.com/KHAEntertainment/claude-dev-skill.git",
            "  https://github.com/KHAEntertainment/claude-dev-skill.git  ",
        )
        for url in equivalent:
            with self.subTest(url=url):
                self.assertEqual(CANONICAL, MODULE.normalize_remote(url))

    def test_non_github_and_ambiguous_origins_are_rejected(self) -> None:
        cases = (
            ("https://gitlab.com/KHAEntertainment/claude-dev-skill.git", "non_github_origin"),
            ("git@gitlab.com:KHAEntertainment/claude-dev-skill.git", "non_github_origin"),
            ("https://github.example.com/KHAEntertainment/claude-dev-skill.git", "non_github_origin"),
            ("file:///srv/git/claude-dev-skill.git", "non_github_origin"),
            ("https://github.com/KHAEntertainment", "ambiguous_origin"),
            ("https://github.com/KHAEntertainment/claude-dev-skill/extra", "ambiguous_origin"),
            ("/srv/git/claude-dev-skill.git", "ambiguous_origin"),
            ("", "ambiguous_origin"),
        )
        for url, code in cases:
            with self.subTest(url=url):
                with self.assertRaises(MODULE.RepositoryError) as caught:
                    MODULE.normalize_remote(url)
                self.assertEqual(code, caught.exception.code)

    def test_whitespace_in_local_path_is_rejected(self) -> None:
        cases = (
            "/tmp/exfil dir/stash.git",
            "/tmp/exfil dir/stash",
        )
        for url in cases:
            with self.subTest(url=url):
                with self.assertRaises(MODULE.RepositoryError) as caught:
                    MODULE.normalize_remote(url)
                self.assertEqual("ambiguous_origin", caught.exception.code)

    def test_repository_comparison_is_case_insensitive(self) -> None:
        self.assertTrue(MODULE.same_repository(CANONICAL, CANONICAL.lower()))
        self.assertFalse(MODULE.same_repository(CANONICAL, PARENT))

    def test_credentials_are_redacted(self) -> None:
        redacted = MODULE.redact_remote("https://token@github.com/KHAEntertainment/claude-dev-skill.git")
        self.assertEqual("https://github.com/KHAEntertainment/claude-dev-skill.git", redacted)


class ResolutionMatrixTests(unittest.TestCase):
    def resolve(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "remotes": {"origin": ORIGIN_HTTPS},
            "push_remotes": None,
            "gh_default": CANONICAL,
            "remote_name": "origin",
        }
        arguments.update(overrides)
        return MODULE.resolve_repository(**arguments)

    def test_single_remote_with_matching_default_is_ready(self) -> None:
        result = self.resolve()
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])

    def test_effective_push_remote_can_differ_from_origin(self) -> None:
        result = self.resolve(
            remotes={
                "upstream": UPSTREAM_HTTPS,
            },
            push_remotes={
                "upstream": [UPSTREAM_HTTPS],
            },
            gh_default=PARENT,
            remote_name="upstream",
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(PARENT, result["repository"])
        self.assertEqual("upstream", result["effective_push_remote"])

    def test_multiple_push_urls_all_matching_is_ready(self) -> None:
        result = self.resolve(
            remotes={"origin": ORIGIN_HTTPS},
            push_remotes={"origin": [ORIGIN_HTTPS, "https://github.com/KHAEntertainment/claude-dev-skill"]},
            gh_default=None,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])

    def test_multiple_push_urls_with_hostile_is_incomplete(self) -> None:
        result = self.resolve(
            remotes={"origin": ORIGIN_HTTPS},
            push_remotes={"origin": [ORIGIN_HTTPS, UPSTREAM_HTTPS]},
            gh_default=None,
        )
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("remote_url_mismatch", result["reason_code"])
        self.assertIsNone(result["repository"])

    def test_conflicting_remote_is_ready_when_default_matches_effective_push_target(self) -> None:
        result = self.resolve(
            remotes={
                "origin": ORIGIN_HTTPS,
                "upstream": UPSTREAM_HTTPS,
            },
            push_remotes={
                "origin": [ORIGIN_HTTPS],
                "upstream": [UPSTREAM_HTTPS],
            },
            gh_default=CANONICAL,
            remote_name="origin",
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])
        self.assertEqual("origin_matches_default", result["reason_code"])
        self.assertIn("upstream=hnaymyh123-henry/claude-dev-skill", result["conflicting_remotes"])

    def test_gh_default_mismatch_blocks(self) -> None:
        result = self.resolve(gh_default=PARENT)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("default_conflicts_with_origin", result["reason_code"])

    def test_missing_gh_default_with_conflicts_is_ready(self) -> None:
        result = self.resolve(
            remotes={
                "origin": ORIGIN_HTTPS,
                "upstream": UPSTREAM_HTTPS,
            },
            push_remotes={
                "origin": [ORIGIN_HTTPS],
                "upstream": [UPSTREAM_HTTPS],
            },
            gh_default=None,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])
        self.assertEqual("origin_is_only_github_remote", result["reason_code"])
        self.assertIn("upstream=hnaymyh123-henry/claude-dev-skill", result["conflicting_remotes"])

    def test_assignment_expectation_match_is_ready(self) -> None:
        result = self.resolve(expected=CANONICAL)
        self.assertEqual("ready", result["status"])

    def test_assignment_expectation_mismatch_fails_closed(self) -> None:
        result = self.resolve(expected=PARENT)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("expected_mismatch", result["reason_code"])

    def test_inaccessible_repository_fails_closed(self) -> None:
        result = self.resolve(access_verified=True, verified_name=None)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("inaccessible_repository", result["reason_code"])

    def test_redirected_origin_fails_closed(self) -> None:
        result = self.resolve(access_verified=True, verified_name="Other/Repo")
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("origin_redirects", result["reason_code"])

    def test_missing_origin_fails_closed(self) -> None:
        result = self.resolve(remotes={"upstream": UPSTREAM_HTTPS}, remote_name="origin")
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("missing_origin", result["reason_code"])


class ResolverCommandLineTests(unittest.TestCase):
    def _no_write_evidence(self, log_text: str) -> None:
        for raw in log_text.splitlines():
            joined = " ".join(raw.split("\t"))
            for token in MUTATING_TOKENS:
                self.assertNotIn(token, joined)
            for pattern in MUTATING_PHRASES:
                self.assertIsNone(re.search(pattern, joined), f"mutating phrase in: {joined}")
            tokens = raw.split("\t")
            leading = tuple(tokens)
            total = len(tokens)
            allowed = any(
                leading[: len(prefix)] == prefix
                and total - len(prefix) >= min_extra
                and (max_extra is None or total - len(prefix) <= max_extra)
                for prefix, min_extra, max_extra in READ_ONLY_COMMANDS
            )
            self.assertTrue(allowed, f"resolver ran unexpected command: {joined}")

    def _run_with_fixture(self, fixture: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub_dir = root / "stubs"
            stub_dir.mkdir()
            log = root / "commands.log"
            env = {
                "PATH": f"{stub_dir}:{os.environ['PATH']}",
                "REPO_IDENTITY_LOG": str(log),
                "FIXTURE": json.dumps(fixture),
            }
            (stub_dir / "git").write_text(STUB.format(python=sys.executable), encoding="utf-8")
            (stub_dir / "git").chmod(0o755)
            (stub_dir / "gh").write_text(STUB.format(python=sys.executable), encoding="utf-8")
            (stub_dir / "gh").chmod(0o755)
            completed = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-dir", str(root)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            log_text = log.read_text(encoding="utf-8") if log.exists() else ""
            return completed, log_text

    def test_matching_default_exits_zero(self) -> None:
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {
                    "fetch": [ORIGIN_HTTPS],
                    "push": [ORIGIN_HTTPS],
                },
            },
            "gh_default": CANONICAL,
        }
        completed, log_text = self._run_with_fixture(fixture)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual(CANONICAL, payload["repository"])
        self._no_write_evidence(log_text)

    def test_fork_with_matching_default_exits_zero(self) -> None:
        """A fork checkout with origin+upstream and a matching gh default is ready."""
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {
                    "fetch": [ORIGIN_HTTPS],
                    "push": [ORIGIN_HTTPS],
                },
                "upstream": {
                    "fetch": [UPSTREAM_HTTPS],
                    "push": [UPSTREAM_HTTPS],
                },
            },
            "gh_default": CANONICAL,
        }
        completed, log_text = self._run_with_fixture(fixture)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(CANONICAL, payload["repository"])
        self.assertEqual("origin_matches_default", payload["reason_code"])
        self.assertIn("upstream=hnaymyh123-henry/claude-dev-skill", payload["conflicting_remotes"])
        self._no_write_evidence(log_text)

    def test_push_default_routing_selects_upstream(self) -> None:
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "upstream",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {
                    "fetch": [ORIGIN_HTTPS],
                    "push": [ORIGIN_HTTPS],
                },
                "upstream": {
                    "fetch": [UPSTREAM_HTTPS],
                    "push": [UPSTREAM_HTTPS],
                },
            },
            "gh_default": CANONICAL,
        }
        completed, log_text = self._run_with_fixture(fixture)
        self.assertEqual(2, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("default_conflicts_with_origin", payload["reason_code"])
        self.assertEqual("upstream", payload["effective_push_remote"])
        self.assertIsNone(payload["repository"])
        self.assertIn("origin=KHAEntertainment/claude-dev-skill", payload["conflicting_remotes"])
        self._no_write_evidence(log_text)

    def test_fresh_clone_no_gh_default_exits_zero(self) -> None:
        """A clean single-remote checkout with no gh default configured is ready."""
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {
                    "fetch": [ORIGIN_HTTPS],
                    "push": [ORIGIN_HTTPS],
                },
            },
            "gh_default": "",
        }
        completed, log_text = self._run_with_fixture(fixture)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(CANONICAL, payload["repository"])
        self.assertEqual("origin_is_only_github_remote", payload["reason_code"])
        self.assertEqual([], payload["conflicting_remotes"])
        self._no_write_evidence(log_text)

    def test_whitespace_url_in_push_position_fails_closed(self) -> None:
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {
                    "fetch": [ORIGIN_HTTPS],
                    "push": ["/tmp/exfil dir/stash.git"],
                },
            },
            "gh_default": CANONICAL,
        }
        completed, log_text = self._run_with_fixture(fixture)
        self.assertEqual(2, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("incomplete", payload["status"])
        self._no_write_evidence(log_text)

    def test_missing_gh_cli_returns_incomplete_not_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python_dir = root / "python_stubs"
            python_dir.mkdir()
            log = root / "commands.log"
            git_stub = (f'#!{sys.executable}\n'
                        'import os, sys\n'
                        'with open(os.environ["REPO_IDENTITY_LOG"], "a") as f:\n'
                        '    f.write("\\t".join(sys.argv) + "\\n")\n'
                        'if sys.argv[1:] == ["branch", "--show-current"]:\n'
                        '    print("main"); raise SystemExit(0)\n'
                        'if sys.argv[1:3] == ["config"]:\n'
                        '    raise SystemExit(1)\n'
                        'if sys.argv[1:] == ["remote"]:\n'
                        '    print("origin"); raise SystemExit(0)\n'
                        'if sys.argv[1:4] == ["remote", "get-url", "--all"]:\n'
                        '    print("https://github.com/KHAEntertainment/claude-dev-skill.git"); raise SystemExit(0)\n'
                        'if sys.argv[1:5] == ["remote", "get-url", "--push", "--all"]:\n'
                        '    print("https://github.com/KHAEntertainment/claude-dev-skill.git"); raise SystemExit(0)\n'
                        'raise SystemExit(1)\n')
            (python_dir / "git").write_text(git_stub, encoding="utf-8")
            (python_dir / "git").chmod(0o755)
            env = {
                "PATH": str(python_dir),
                "REPO_IDENTITY_LOG": str(log),
            }
            completed = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-dir", str(root)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(2, completed.returncode)
            payload = json.loads(completed.stdout)
            self.assertEqual("incomplete", payload["status"])
            self.assertEqual("gh_cli_missing", payload["reason_code"])


class SplitRemoteRegressionTests(unittest.TestCase):
    def run_fixture(self, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory, "state.json")
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(RESOLVER), "--fixture", str(fixture)],
                check=False,
                capture_output=True,
                text=True,
            )
        return completed.returncode, json.loads(completed.stdout)

    def test_split_fetch_push_resolves_to_incomplete(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [UPSTREAM_HTTPS]},
                "effective_push_remote": "origin",
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])
        self.assertIsNone(payload["repository"])

    def test_hostile_multiple_push_url_first(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": [ORIGIN_HTTPS]},
                "push_remotes": {"origin": [UPSTREAM_HTTPS, ORIGIN_HTTPS]},
                "effective_push_remote": "origin",
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])

    def test_hostile_multiple_push_url_last(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": [ORIGIN_HTTPS]},
                "push_remotes": {"origin": [ORIGIN_HTTPS, UPSTREAM_HTTPS]},
                "effective_push_remote": "origin",
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])


if __name__ == "__main__":
    unittest.main()
