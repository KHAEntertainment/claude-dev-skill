from __future__ import annotations

import importlib.util
import json
import os
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

# Verbs that would mutate a repository. The resolver must never emit one.
MUTATING_TOKENS = (
    "create",
    "comment",
    "review",
    "merge",
    "close",
    "reopen",
    "edit",
    "push",
    "delete",
    "POST",
    "PATCH",
    "PUT",
    "--method",
)

# Every command the resolver is allowed to run, as an exact argv prefix.
READ_ONLY_PREFIXES = (
    ("git", "remote", "-v"),
    ("gh", "repo", "set-default", "--view"),
    ("gh", "repo", "view"),
)

STUB = """#!{python}
import os
import sys

with open(os.environ["REPO_IDENTITY_LOG"], "a", encoding="utf-8") as handle:
    handle.write("\\t".join(sys.argv) + "\\n")

name = os.path.basename(sys.argv[0])
args = sys.argv[1:]

if name == "git" and args[:2] == ["remote", "-v"]:
    print("origin\\t{origin} (fetch)")
    print("origin\\t{origin} (push)")
    print("upstream\\t{upstream} (fetch)")
    print("upstream\\t{upstream} (push)")
    raise SystemExit(0)

if name == "gh" and args[:3] == ["repo", "set-default", "--view"]:
    sys.stderr.write("no default repository has been set\\n")
    raise SystemExit(1)

if name == "gh" and args[:2] == ["repo", "view"]:
    print("{canonical}")
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

    def test_repository_comparison_is_case_insensitive(self) -> None:
        self.assertTrue(MODULE.same_repository(CANONICAL, CANONICAL.lower()))
        self.assertFalse(MODULE.same_repository(CANONICAL, PARENT))


class ResolutionMatrixTests(unittest.TestCase):
    def resolve(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "remotes": {"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
            "gh_default": CANONICAL,
        }
        arguments.update(overrides)
        return MODULE.resolve_repository(**arguments)  # type: ignore[arg-type]

    def test_fork_with_missing_default_stops_and_names_the_mismatch(self) -> None:
        result = self.resolve(gh_default=None)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("ambiguous_default", result["reason_code"])
        self.assertIsNone(result["repository"])
        self.assertIn(CANONICAL, str(result["reason"]))
        self.assertIn(PARENT, str(result["reason"]))
        self.assertEqual([f"upstream={PARENT}"], result["conflicting_remotes"])

    def test_fork_with_upstream_default_stops_and_names_the_mismatch(self) -> None:
        result = self.resolve(gh_default=PARENT)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("default_conflicts_with_origin", result["reason_code"])
        self.assertIsNone(result["repository"])
        self.assertIn(CANONICAL, str(result["reason"]))
        self.assertIn(PARENT, str(result["reason"]))

    def test_fork_with_matching_default_is_ready(self) -> None:
        result = self.resolve()
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])
        self.assertEqual("origin_matches_default", result["reason_code"])

    def test_ssh_origin_matches_an_https_default(self) -> None:
        result = self.resolve(
            remotes={"origin": "git@github.com:KHAEntertainment/claude-dev-skill.git"},
            gh_default=CANONICAL,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual(CANONICAL, result["repository"])

    def test_single_remote_without_a_default_stays_ready(self) -> None:
        result = self.resolve(remotes={"origin": ORIGIN_HTTPS}, gh_default=None)
        self.assertEqual("ready", result["status"])
        self.assertEqual("origin_is_only_github_remote", result["reason_code"])

    def test_mirror_remote_of_the_same_repository_is_not_a_conflict(self) -> None:
        result = self.resolve(
            remotes={
                "origin": ORIGIN_HTTPS,
                "mirror": "git@github.com:khaentertainment/claude-dev-skill.git",
            },
            gh_default=None,
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual([], result["conflicting_remotes"])

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

    def test_multiple_fetch_urls_with_hostile_is_incomplete(self) -> None:
        result = self.resolve(
            remotes={"origin": [ORIGIN_HTTPS, UPSTREAM_HTTPS]},
            gh_default=None,
        )
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("remote_url_mismatch", result["reason_code"])
        self.assertIsNone(result["repository"])

    def test_missing_origin_fails_closed(self) -> None:
        result = self.resolve(remotes={"upstream": UPSTREAM_HTTPS}, gh_default=None)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("missing_origin", result["reason_code"])

    def test_non_github_origin_fails_closed(self) -> None:
        result = self.resolve(
            remotes={"origin": "https://gitlab.com/KHAEntertainment/claude-dev-skill.git"},
            gh_default=None,
        )
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("non_github_origin", result["reason_code"])

    def test_inaccessible_repository_fails_closed(self) -> None:
        result = self.resolve(access_verified=True, verified_name=None)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("inaccessible_repository", result["reason_code"])

    def test_redirected_origin_fails_closed(self) -> None:
        result = self.resolve(access_verified=True, verified_name=PARENT)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("origin_redirects", result["reason_code"])

    def test_assignment_expectation_mismatch_fails_closed(self) -> None:
        result = self.resolve(expected=PARENT)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual("expected_mismatch", result["reason_code"])

    def test_assignment_expectation_match_is_ready(self) -> None:
        result = self.resolve(expected=CANONICAL.lower())
        self.assertEqual("ready", result["status"])


class ResolverCommandLineTests(unittest.TestCase):
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

    def test_fork_shape_exits_two_with_compact_json(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("ambiguous_default", payload["reason_code"])
        self.assertIsNone(payload["repository"])

    def test_matching_default_exits_zero(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                "gh_default": CANONICAL,
            }
        )
        self.assertEqual(0, status)
        self.assertEqual(CANONICAL, payload["repository"])

    @unittest.skipIf(os.name == "nt", "POSIX shebang stubs are not executable on Windows")
    def test_wrong_default_resolution_performs_no_write(self) -> None:
        """Recreate the dogfooding failure shape and prove nothing was written."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub_dir = root / "bin"
            stub_dir.mkdir()
            log = root / "commands.log"
            source = STUB.format(
                python=sys.executable,
                origin=ORIGIN_HTTPS,
                upstream=UPSTREAM_HTTPS,
                canonical=CANONICAL,
            )
            for name in ("git", "gh"):
                stub = stub_dir / name
                stub.write_text(source, encoding="utf-8")
                stub.chmod(0o755)

            environment = os.environ.copy()
            environment["REPO_IDENTITY_LOG"] = str(log)
            environment["PATH"] = f"{stub_dir}{os.pathsep}{environment['PATH']}"
            completed = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-dir", str(root)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(2, completed.returncode)
            self.assertEqual("ambiguous_default", payload["reason_code"])
            self.assertIsNone(payload["repository"])

            recorded = [
                tuple(line.split("\t"))
                for line in log.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertTrue(recorded, "the resolver ran no command at all")
            for argv in recorded:
                invocation = (Path(argv[0]).name,) + tuple(argv[1:])
                with self.subTest(command=invocation):
                    self.assertTrue(
                        any(
                            invocation[: len(prefix)] == prefix
                            for prefix in READ_ONLY_PREFIXES
                        ),
                        f"resolver ran a command outside the read-only set: {invocation}",
                    )
                    joined = " ".join(invocation)
                    for token in MUTATING_TOKENS:
                        self.assertNotIn(token, joined)
                    self.assertNotIn("hnaymyh123-henry", joined)


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
                "push_remotes": {"origin": UPSTREAM_HTTPS},
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])
        self.assertIsNone(payload["repository"])
        self.assertEqual(ORIGIN_HTTPS, payload["remote_url"])
        self.assertEqual(UPSTREAM_HTTPS, payload["push_url"])

    def test_hostile_multiple_push_url_first(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [UPSTREAM_HTTPS, ORIGIN_HTTPS]},
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])
        self.assertIsNone(payload["repository"])
        self.assertEqual(UPSTREAM_HTTPS, payload["push_url"])

    def test_hostile_multiple_push_url_last(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [ORIGIN_HTTPS, UPSTREAM_HTTPS]},
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])
        self.assertIsNone(payload["repository"])
        self.assertEqual(UPSTREAM_HTTPS, payload["push_url"])

    def test_multiple_push_urls_mixed(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [UPSTREAM_HTTPS, ORIGIN_HTTPS, UPSTREAM_HTTPS]},
                "gh_default": None,
            }
        )
        self.assertEqual(2, status)
        self.assertEqual("remote_url_mismatch", payload["reason_code"])
        self.assertIsNone(payload["repository"])

    def test_multiple_push_urls_all_matching_is_ready(self) -> None:
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": ORIGIN_HTTPS},
                "push_remotes": {"origin": [ORIGIN_HTTPS, "https://github.com/KHAEntertainment/claude-dev-skill"]},
                "gh_default": None,
            }
        )
        self.assertEqual(0, status)
        self.assertEqual(CANONICAL, payload["repository"])

    def test_credentials_are_redacted_in_output(self) -> None:
        secret = "https://user:s3cr3t-token@github.com/KHAEntertainment/claude-dev-skill.git"
        status, payload = self.run_fixture(
            {
                "remotes": {"origin": secret},
                "gh_default": None,
            }
        )
        self.assertEqual(0, status)
        self.assertEqual(CANONICAL, payload["repository"])
        self.assertNotIn("s3cr3t-token", json.dumps(payload))
        self.assertNotIn("user:", json.dumps(payload))
        self.assertEqual("https://github.com/KHAEntertainment/claude-dev-skill.git", payload["remote_url"])

    @unittest.skipIf(os.name == "nt", "POSIX shebang stubs are not executable on Windows")
    def test_missing_gh_cli_returns_incomplete_not_traceback(self) -> None:
        """gh is absent but git is present; the resolver returns compact incomplete JSON."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub_dir = root / "bin"
            stub_dir.mkdir()
            log = root / "commands.log"
            git_stub = stub_dir / "git"
            git_stub.write_text(
                f"#!{sys.executable}\n"
                f"import os, sys\n"
                f"with open(os.environ['REPO_IDENTITY_LOG'], 'a', encoding='utf-8') as h:\n"
                f"    h.write('\\t'.join(sys.argv) + '\\n')\n"
                f"print('origin\\t{ORIGIN_HTTPS} (fetch)')\n"
                f"print('origin\\t{UPSTREAM_HTTPS} (push)')\n"
                f"raise SystemExit(0)\n",
                encoding="utf-8",
            )
            git_stub.chmod(0o755)

            python_dir = str(Path(sys.executable).parent)
            environment = os.environ.copy()
            environment["REPO_IDENTITY_LOG"] = str(log)
            environment["PATH"] = f"{stub_dir}{os.pathsep}{python_dir}"
            completed = subprocess.run(
                [sys.executable, str(RESOLVER), "--repo-dir", str(root)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(2, completed.returncode)
            self.assertEqual("gh_cli_missing", payload["reason_code"])
            self.assertIsNone(payload["repository"])
            recorded = [
                tuple(line.split("\t"))
                for line in log.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertTrue(recorded, "the resolver ran no command at all")
            for argv in recorded:
                self.assertEqual("git", Path(argv[0]).name)


if __name__ == "__main__":
    unittest.main()
