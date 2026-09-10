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
            "expected": CANONICAL,
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
            expected=PARENT,
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

    def test_conflicting_unrelated_remote_does_not_block(self) -> None:
        """A fork's `upstream` disagreeing with the push target is recorded,
        never blocked -- explicit separate push/PR targets are supported."""
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
        self.assertIn("upstream=hnaymyh123-henry/claude-dev-skill", result["conflicting_remotes"])

    def test_hostile_origin_canonical_effective_push_is_ready(self) -> None:
        """A fork-shaped checkout where `origin` is the parent and the effective
        push remote is the canonical `fork` resolves `ready` and names `fork`
        as the only valid push target."""
        result = self.resolve(
            remotes={
                "origin": UPSTREAM_HTTPS,
                "fork": ORIGIN_HTTPS,
            },
            push_remotes={
                "origin": [UPSTREAM_HTTPS],
                "fork": [ORIGIN_HTTPS],
            },
            gh_default=CANONICAL,
            remote_name="fork",
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])
        self.assertEqual("fork", result["effective_push_remote"])
        self.assertIn("origin=hnaymyh123-henry/claude-dev-skill", result["conflicting_remotes"])

    def test_gh_default_mismatch_does_not_block_an_explicitly_scoped_operation(self) -> None:
        """Corrected behaviour (issue-19-bounded-release-requirement): every
        supported command is explicitly scoped, so the CLI's unrelated
        repository default must not block a correctly configured fork whose
        PR target differs from its push target."""
        result = self.resolve(gh_default=PARENT)
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])
        self.assertTrue(any("gh CLI default" in note for note in result["notes"]))

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

    def test_configured_remote_matching_effective_push_remote_is_ready(self) -> None:
        result = self.resolve(configured_remote="origin")
        self.assertEqual("ready", result["status"])

    def test_configured_remote_mismatch_fails_closed_with_no_fallback(self) -> None:
        """A conflicting Git push-remote default (e.g. a hijacked
        `remote.pushDefault`) stops for clarification; there is no fallback."""
        result = self.resolve(
            remotes={
                "origin": ORIGIN_HTTPS,
                "upstream": UPSTREAM_HTTPS,
            },
            push_remotes={
                "origin": [ORIGIN_HTTPS],
                "upstream": [UPSTREAM_HTTPS],
            },
            remote_name="upstream",
            configured_remote="origin",
            expected=CANONICAL,
        )
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("configured_remote_mismatch", result["reason_code"])
        self.assertIsNone(result["effective_push_remote"])
        self.assertIsNone(result["remote"])
        self.assertIsNone(result["repository"])


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

    def _run_with_fixture(self, fixture: dict[str, object], *extra_args: str) -> tuple[subprocess.CompletedProcess[str], str]:
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
                [sys.executable, str(RESOLVER), "--repo-dir", str(root), *extra_args],
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
        completed, log_text = self._run_with_fixture(fixture, "--expect", CANONICAL)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual(CANONICAL, payload["repository"])
        self._no_write_evidence(log_text)

    def test_fork_with_matching_default_exits_zero(self) -> None:
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
        completed, log_text = self._run_with_fixture(fixture, "--expect", CANONICAL)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(CANONICAL, payload["repository"])
        self.assertIn("upstream=hnaymyh123-henry/claude-dev-skill", payload["conflicting_remotes"])
        self._no_write_evidence(log_text)

    def test_upstream_contributor_pr_target_differs_from_push_and_is_not_blocked(self) -> None:
        """The upstream-contributor preset: pushes stay on the fork, but the PR
        operation's `--expect` names upstream. A gh default matching neither
        must not block either operation."""
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {"fetch": [ORIGIN_HTTPS], "push": [ORIGIN_HTTPS]},
                "upstream": {"fetch": [UPSTREAM_HTTPS], "push": [UPSTREAM_HTTPS]},
            },
            "gh_default": PARENT,
        }
        completed, _ = self._run_with_fixture(fixture, "--expect", CANONICAL, "--configured-remote", "origin")
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(CANONICAL, payload["repository"])

    def test_push_default_routing_to_wrong_remote_is_caught_by_configured_remote(self) -> None:
        """A hijacked `remote.pushDefault` silently routes the push to
        `upstream`. `.dev.json` names `origin` as the intended push remote, so
        the configured-remote check -- not the (now-informational) gh
        default -- must stop it."""
        fixture = {
            "branch": "main",
            "config": {
                "branch.main.pushRemote": "",
                "remote.pushDefault": "upstream",
                "branch.main.remote": "origin",
            },
            "remotes": {
                "origin": {"fetch": [ORIGIN_HTTPS], "push": [ORIGIN_HTTPS]},
                "upstream": {"fetch": [UPSTREAM_HTTPS], "push": [UPSTREAM_HTTPS]},
            },
            "gh_default": CANONICAL,
        }
        completed, log_text = self._run_with_fixture(fixture, "--expect", CANONICAL, "--configured-remote", "origin")
        self.assertEqual(2, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("configured_remote_mismatch", payload["reason_code"])
        self.assertIsNone(payload["effective_push_remote"])
        self.assertIsNone(payload["remote"])
        self.assertIsNone(payload["repository"])
        self._no_write_evidence(log_text)

    def test_fresh_clone_no_gh_default_exits_zero(self) -> None:
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
        completed, log_text = self._run_with_fixture(fixture, "--expect", CANONICAL)
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("ready", payload["status"])
        self.assertEqual(CANONICAL, payload["repository"])
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
        completed, log_text = self._run_with_fixture(fixture, "--expect", CANONICAL)
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
                [sys.executable, str(RESOLVER), "--repo-dir", str(root), "--expect", CANONICAL],
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


class DoNotActInvariantTests(unittest.TestCase):
    """A verdict that says "do not act" must carry no actionable push target."""

    def _run(self, payload: dict[str, object], *extra: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory, "state.json")
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(RESOLVER), "--fixture", str(fixture), *extra],
                check=False,
                capture_output=True,
                text=True,
            )

    NON_READY: tuple[tuple[str, dict[str, object]], ...] = (
        (
            "push_url_disagrees",
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [UPSTREAM_HTTPS]},
                "effective_push_remote": "origin",
                "gh_default": None,
            },
        ),
        (
            "expected_disagrees",
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "effective_push_remote": "origin",
                "gh_default": None,
            },
        ),
        (
            "unparseable_origin",
            {
                "remotes": {"origin": "not a url at all"},
                "effective_push_remote": "origin",
                "gh_default": None,
            },
        ),
        (
            "configured_remote_disagrees",
            {
                "remotes": {"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                "effective_push_remote": "upstream",
                "configured_remote": "origin",
                "gh_default": None,
            },
        ),
    )

    @staticmethod
    def _extra_args_for(label: str) -> tuple[str, ...]:
        if label == "expected_disagrees":
            return ("--expect", "hnaymyh123-henry/claude-dev-skill")
        return ()

    def test_non_ready_verdicts_carry_no_push_remote(self) -> None:
        for label, payload in self.NON_READY:
            with self.subTest(label):
                completed = self._run(payload, *self._extra_args_for(label))
                verdict = json.loads(completed.stdout)
                self.assertNotEqual("ready", verdict["status"])
                self.assertEqual(2, completed.returncode)
                for actionable in ("effective_push_remote", "remote"):
                    self.assertIsNone(
                        verdict[actionable],
                        f"{label}: a do-not-act verdict handed back a usable "
                        f"remote in `{actionable}`",
                    )

    def test_print_push_remote_is_empty_and_fails_when_not_ready(self) -> None:
        for label, payload in self.NON_READY:
            with self.subTest(label):
                completed = self._run(payload, "--print-push-remote", *self._extra_args_for(label))
                self.assertEqual(2, completed.returncode)
                self.assertEqual(
                    "",
                    completed.stdout.strip(),
                    f"{label}: stdout must be empty so `$(...)` yields no push target",
                )
                self.assertNotEqual("", completed.stderr.strip())

    def test_print_push_remote_emits_only_the_name_when_ready(self) -> None:
        completed = self._run(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "effective_push_remote": "origin",
                "gh_default": "KHAEntertainment/claude-dev-skill",
                "access_verified": True,
                "verified_name": "KHAEntertainment/claude-dev-skill",
            },
            "--print-push-remote",
            "--expect", CANONICAL,
        )
        self.assertEqual(0, completed.returncode)
        self.assertEqual("origin", completed.stdout.strip())

    def test_piping_the_json_verdict_cannot_yield_a_usable_remote(self) -> None:
        for label, payload in self.NON_READY:
            with self.subTest(label):
                verdict = json.loads(self._run(payload, *self._extra_args_for(label)).stdout)
                for actionable in ("effective_push_remote", "remote"):
                    harvested = verdict[actionable]
                    self.assertFalse(
                        isinstance(harvested, str) and harvested.strip(),
                        f"{label}: harvested {harvested!r} from `{actionable}` "
                        "on a rejected verdict",
                    )


class TransportAuthOverrideDetectionTests(unittest.TestCase):
    """Bounded transport support: a higher-precedence override yields a named
    `unsupported_transport_auth` result rather than a probe of the wrong
    identity source."""

    def _init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)

    def test_ssh_command_env_override_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            old = os.environ.get("GIT_SSH_COMMAND")
            os.environ["GIT_SSH_COMMAND"] = "ssh -F /custom/config"
            try:
                self.assertEqual("GIT_SSH_COMMAND", MODULE.detect_ssh_overrides(root))
            finally:
                if old is None:
                    os.environ.pop("GIT_SSH_COMMAND", None)
                else:
                    os.environ["GIT_SSH_COMMAND"] = old

    def test_core_ssh_command_config_override_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            subprocess.run(
                ["git", "config", "core.sshCommand", "ssh -F /custom/config"],
                cwd=str(root), check=True,
            )
            self.assertEqual("core.sshCommand", MODULE.detect_ssh_overrides(root))

    def test_no_ssh_override_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            self.assertIsNone(MODULE.detect_ssh_overrides(root))

    def test_https_extra_header_override_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            subprocess.run(
                ["git", "config", "http.extraHeader", "Authorization: Bearer x"],
                cwd=str(root), check=True,
            )
            self.assertEqual("http.extraHeader", MODULE.detect_https_auth_overrides(root, ORIGIN_HTTPS))

    def test_no_https_override_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            self.assertIsNone(MODULE.detect_https_auth_overrides(root, ORIGIN_HTTPS))

    def test_askpass_env_override_is_detected(self) -> None:
        old = os.environ.get("SSH_ASKPASS")
        os.environ["SSH_ASKPASS"] = "/usr/bin/ssh-askpass"
        try:
            self.assertEqual("SSH_ASKPASS", MODULE.detect_askpass_overrides())
        finally:
            if old is None:
                os.environ.pop("SSH_ASKPASS", None)
            else:
                os.environ["SSH_ASKPASS"] = old


class TransportAccountVerificationTests(unittest.TestCase):
    """Mocked identity checks only -- no live credential retrieval or network
    call runs here. `lookup_login`/`prober` are injected stubs standing in for
    GitHub's authenticated-user endpoint and a real SSH probe."""

    def _init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)

    def test_https_matching_account_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            fake_fill = lambda repo_dir, url: {"username": "KHAEntertainment", "password": "x"}
            with _patched(MODULE, "fill_https_credential", fake_fill):
                result = MODULE.verify_https_account(
                    root, ORIGIN_HTTPS, "KHAEntertainment",
                    lookup_login=lambda credential: "KHAEntertainment",
                )
            self.assertEqual("verified", result["status"])

    def test_https_mismatched_account_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            fake_fill = lambda repo_dir, url: {"username": "Clarit-AI", "password": "x"}
            with _patched(MODULE, "fill_https_credential", fake_fill):
                result = MODULE.verify_https_account(
                    root, ORIGIN_HTTPS, "KHAEntertainment",
                    lookup_login=lambda credential: "Clarit-AI",
                )
            self.assertEqual("incomplete", result["status"])
            self.assertEqual("account_mismatch", result["reason_code"])

    def test_https_unavailable_credential_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            with _patched(MODULE, "fill_https_credential", lambda repo_dir, url: None):
                result = MODULE.verify_https_account(
                    root, ORIGIN_HTTPS, "KHAEntertainment", lookup_login=lambda credential: "irrelevant"
                )
            self.assertEqual("incomplete", result["status"])
            self.assertEqual("identity_unavailable", result["reason_code"])

    def test_https_extra_header_override_short_circuits_before_helper_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            subprocess.run(
                ["git", "config", "http.extraHeader", "Authorization: Bearer x"],
                cwd=str(root), check=True,
            )
            called = {"fill": False}

            def fake_fill(repo_dir: Path, url: str) -> dict[str, str] | None:
                called["fill"] = True
                return {"username": "KHAEntertainment", "password": "x"}

            with _patched(MODULE, "fill_https_credential", fake_fill):
                result = MODULE.verify_https_account(
                    root, ORIGIN_HTTPS, "KHAEntertainment", lookup_login=lambda credential: "KHAEntertainment"
                )
            self.assertEqual("unsupported_transport_auth", result["reason_code"])
            self.assertFalse(called["fill"], "helper lookup must not run once a higher-precedence override is found")

    def test_ssh_matching_account_documented_exit_one_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            prober = lambda repo_dir, host: (1, "Hi KHAEntertainment! You've successfully authenticated, but GitHub does not provide shell access.")
            result = MODULE.verify_ssh_account(root, "github.com", "KHAEntertainment", prober=prober)
            self.assertEqual("verified", result["status"])

    def test_ssh_mismatched_account_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            prober = lambda repo_dir, host: (1, "Hi Clarit-AI! You've successfully authenticated, but GitHub does not provide shell access.")
            result = MODULE.verify_ssh_account(root, "github.com", "KHAEntertainment", prober=prober)
            self.assertEqual("incomplete", result["status"])
            self.assertEqual("account_mismatch", result["reason_code"])

    def test_ssh_generic_zero_exit_is_not_mistaken_for_success(self) -> None:
        """GitHub's documented successful test exits 1; a generic zero-exit
        rule would misclassify both directions."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            prober = lambda repo_dir, host: (0, "some other banner")
            result = MODULE.verify_ssh_account(root, "github.com", "KHAEntertainment", prober=prober)
            self.assertEqual("incomplete", result["status"])
            self.assertEqual("identity_unavailable", result["reason_code"])

    def test_ssh_command_override_short_circuits_before_probing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            subprocess.run(
                ["git", "config", "core.sshCommand", "ssh -F /custom/config"],
                cwd=str(root), check=True,
            )
            called = {"probe": False}

            def prober(repo_dir: Path, host: str) -> tuple[int, str]:
                called["probe"] = True
                return (1, "Hi KHAEntertainment! You've successfully authenticated")

            result = MODULE.verify_ssh_account(root, "github.com", "KHAEntertainment", prober=prober)
            self.assertEqual("unsupported_transport_auth", result["reason_code"])
            self.assertFalse(called["probe"], "probe must not run once a higher-precedence override is found")


class _patched:
    """Minimal monkeypatch context manager, kept local to avoid a pytest/mock dependency."""

    def __init__(self, module: object, name: str, value: object) -> None:
        self._module = module
        self._name = name
        self._value = value
        self._original = getattr(module, name)

    def __enter__(self) -> None:
        setattr(self._module, self._name, self._value)

    def __exit__(self, *exc: object) -> None:
        setattr(self._module, self._name, self._original)


if __name__ == "__main__":
    unittest.main()
