"""PR36 external-review regressions; credentials and networks stay mocked."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_dev_config import MODULE as CONFIG, VALID_DOC
import test_prewrite_entrypoint as entrypoint
from test_prewrite_entrypoint import VERIFIED
from test_repository_identity import MODULE as RESOLVER


class ConfigRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.path = self.root / ".dev.json"

    def cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["config", *args, "--path", str(self.path)]), contextlib.redirect_stdout(output):
            code = CONFIG.main()
        return code, json.loads(output.getvalue())

    def test_root_failure_never_trusts_config(self):
        CONFIG.create_config(self.path, VALID_DOC)
        for failure in [(124, "timed out"), (128, "fatal: broken config"),
                        (128, "fatal: not a git repository (or any of the parent directories): .git")]:
            with self.subTest(failure=failure), patch.object(CONFIG, "_run", return_value=failure):
                self.assertEqual("incomplete", CONFIG.resolve_status(self.path)["status"])

    def test_create_exclusion_failure_then_recover_without_overwrite(self):
        args = ["create", "--account", "KHAEntertainment", "--push-repository", "KHAEntertainment/claude-dev-skill",
                "--pull-request-repository", "KHAEntertainment/claude-dev-skill"]
        with patch.object(CONFIG, "ensure_excluded", return_value=False):
            code, result = self.cli(*args)
        self.assertEqual(2, code)
        self.assertEqual("incomplete", result["status"])
        original = self.path.read_bytes()
        code, result = self.cli(*args)
        self.assertEqual(2, code)
        self.assertEqual("already_exists", result["reason_code"])
        code, result = self.cli("exclude")
        self.assertEqual(0, code)
        self.assertEqual("valid", result["status"])
        self.assertEqual(original, self.path.read_bytes())

    def test_exclude_refuses_tracked_and_invalid_files(self):
        self.path.write_text("{}")
        code, _ = self.cli("exclude")
        self.assertEqual(2, code)
        self.path.write_text(json.dumps(VALID_DOC))
        subprocess.run(["git", "add", ".dev.json"], cwd=self.root, check=True)
        code, result = self.cli("exclude")
        self.assertEqual(2, code)
        self.assertEqual("tracked_config", result["reason_code"])

    def test_exclusion_failure_remains_incomplete(self):
        CONFIG.create_config(self.path, VALID_DOC)
        with patch.object(CONFIG, "ensure_excluded", return_value=False):
            code, result = self.cli("exclude")
        self.assertEqual((2, "incomplete"), (code, result["status"]))

    def test_provenance_errors_stop_status_and_create(self):
        with patch.object(CONFIG, "_run", return_value=(124, "timed out")):
            code, result = self.cli("status")
            self.assertEqual((2, "git_provenance_unavailable"), (code, result["reason_code"]))
            code, result = self.cli("create", "--account", "KHAEntertainment", "--push-repository", "KHAEntertainment/claude-dev-skill",
                                    "--pull-request-repository", "KHAEntertainment/claude-dev-skill")
            self.assertEqual(2, code)
            self.assertFalse(self.path.exists())


class AccountBindingTests(unittest.TestCase):
    setUp = entrypoint.PrewriteEntrypointTests.setUp
    run_cli = entrypoint.PrewriteEntrypointTests.run_cli

    def test_account_override_and_missing_config_stop_before_probe(self):
        with patch.object(RESOLVER, "verify_gh_cli_login", return_value=VERIFIED) as probe:
            code, result = self.run_cli("--mode", "check-gh-account", "--account", "Other")
            self.assertEqual((2, "account_mismatch"), (code, result["reason_code"]))
            (self.root / ".dev.json").unlink()
            code, result = self.run_cli("--mode", "check-gh-account", "--account", "KHAEntertainment")
            self.assertEqual((2, "missing_config"), (code, result["reason_code"]))
            probe.assert_not_called()

    def test_first_use_candidate_check_is_distinct_and_cannot_override_config(self):
        with patch.object(RESOLVER, "verify_gh_cli_login", return_value=VERIFIED) as probe:
            code, result = self.run_cli("--mode", "check-gh-account", "--setup-account-check", "--account", "Other")
            self.assertEqual(2, code)
            probe.assert_not_called()
            (self.root / ".dev.json").unlink()
            code, result = self.run_cli("--mode", "check-gh-account", "--setup-account-check", "--account", "KHAEntertainment")
            self.assertEqual((0, "candidate_verified"), (code, result["status"]))

    def test_option_like_ssh_host_never_reaches_lookup(self):
        with patch.object(RESOLVER, "resolve_ssh_effective_host") as lookup:
            with self.assertRaises(RESOLVER.RepositoryError):
                RESOLVER.normalize_remote_with_ssh_resolution("git@-F:A/B.git", self.root)
            lookup.assert_not_called()

    def test_all_modes_reject_invalid_and_tracked_config_before_probes(self):
        path = self.root / ".dev.json"
        for status in ("invalid", "tracked"):
            path.write_text("{}" if status == "invalid" else json.dumps(VALID_DOC))
            if status == "tracked":
                subprocess.run(["git", "add", "-f", ".dev.json"], cwd=self.root, check=True)
            for mode, name, args in [("check-gh-account", "verify_gh_cli_login", []),
                                     ("check-https-account", "verify_https_account", ["--url", "https://github.com/A/B"]),
                                     ("check-ssh-account", "verify_ssh_url_account", ["--url", "git@github.com:A/B"])]:
                with self.subTest(status=status, mode=mode), patch.object(RESOLVER, name) as probe:
                    code, result = self.run_cli("--mode", mode, "--account", "KHAEntertainment", *args)
                    self.assertEqual((2, "incomplete"), (code, result["status"]))
                    probe.assert_not_called()

    def test_new_project_setup_then_saved_config_verifies_before_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(RESOLVER, "verify_gh_cli_login", return_value=VERIFIED) as probe:
            self.root = Path(directory)  # genuinely pre-Git, no repository metadata
            code, result = self.run_cli("--mode", "check-gh-account", "--setup-account-check", "--account", "KHAEntertainment")
            self.assertEqual((0, "candidate_verified"), (code, result["status"]))
            RESOLVER.dev_config.create_config(self.root / ".dev.json", VALID_DOC)
            code, result = self.run_cli("--mode", "check-gh-account")
            self.assertEqual((0, "verified"), (code, result["status"]))
            self.assertEqual("KHAEntertainment", probe.call_args.args[1])

    def test_setup_flag_does_not_allow_a_resolve_operation(self):
        (self.root / ".dev.json").unlink()
        code, result = self.run_cli("--setup-account-check", "--operation", "pr", "--target", "KHAEntertainment/claude-dev-skill")
        self.assertEqual((2, "invalid_mode"), (code, result["reason_code"]))


if __name__ == "__main__":
    unittest.main()
