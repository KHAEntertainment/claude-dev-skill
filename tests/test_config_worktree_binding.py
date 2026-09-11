"""Production config selection stays bound to the assigned worktree."""
import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_prewrite_entrypoint as entrypoint
from test_prewrite_entrypoint import VERIFIED
from test_repository_identity import MODULE, VALID_DOC


class ConfigWorktreeBindingTests(unittest.TestCase):
    setUp = entrypoint.PrewriteEntrypointTests.setUp
    run_cli = entrypoint.PrewriteEntrypointTests.run_cli

    def assert_rejected_before_probes(self, config_path, *extra):
        modes = [[], ["--operation", "pr"], ["--operation", "issue"],
                 ["--mode", "check-gh-account"], ["--mode", "check-https-account"],
                 ["--mode", "check-ssh-account"],
                 ["--mode", "check-gh-account", "--setup-account-check", "--account", "Other"]]
        for mode in modes:
            with self.subTest(mode=mode), contextlib.ExitStack() as stack:
                probes = [stack.enter_context(patch.object(MODULE, name)) for name in
                          ("verify_gh_cli_login", "verify_https_account", "verify_ssh_url_account",
                           "verify_branch_and_dry_run", "collect_remotes")]
                status = stack.enter_context(patch.object(MODULE.dev_config, "resolve_status",
                                                         wraps=MODULE.dev_config.resolve_status))
                args = [] if config_path is None else ["--config", str(config_path)]
                code, result = self.run_cli(*args, *mode, *extra)
                self.assertEqual((2, "config_path_mismatch"), (code, result["reason_code"]))
                status.assert_not_called()
                for probe in probes:
                    probe.assert_not_called()

    def test_external_configs_rejected_for_every_production_mode(self):
        with tempfile.TemporaryDirectory() as other:
            path = Path(other) / ".dev.json"
            path.write_text(json.dumps(VALID_DOC))
            self.assert_rejected_before_probes(path)
            subprocess.run(["git", "init", "-q", other], check=True)
            MODULE.dev_config.ensure_excluded(Path(other))
            self.assert_rejected_before_probes(path)

    def test_missing_canonical_config_does_not_allow_foreign_setup_override(self):
        (self.root / ".dev.json").unlink()
        self.assert_rejected_before_probes(self.root / "elsewhere.json")

    def test_canonical_symlink_escape_rejected_with_or_without_override(self):
        with tempfile.TemporaryDirectory() as other:
            external = Path(other) / ".dev.json"
            external.write_text(json.dumps(VALID_DOC))
            path = self.root / ".dev.json"
            path.unlink()
            path.symlink_to(external)
            self.assert_rejected_before_probes(None)
            self.assert_rejected_before_probes(path)

    def test_explicit_canonical_path_and_subdirectory_pass(self):
        subdir = self.root / "subdir"
        subdir.mkdir()
        with patch.object(MODULE, "verify_gh_cli_login", return_value=VERIFIED) as probe:
            code, result = self.run_cli("--repo-dir", str(subdir), "--config", str(self.root / ".dev.json"),
                                        "--operation", "pr", "--target", VALID_DOC["github"]["pullRequestRepository"])
        self.assertEqual((0, "ready"), (code, result["status"]))
        self.assertEqual(subdir.resolve(), probe.call_args.args[0])

    def test_relative_canonical_path_ignores_ambient_config(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as other:
            os.chdir(other)
            try:
                relative = os.path.relpath(self.root / ".dev.json", other)
                with patch.object(MODULE, "verify_gh_cli_login", return_value=VERIFIED) as probe:
                    code, result = self.run_cli("--config", relative, "--mode", "check-gh-account")
                self.assertEqual((0, "verified"), (code, result["status"]))
                self.assertEqual(self.root.resolve(), probe.call_args.args[0])
            finally:
                os.chdir(previous)

    def test_linked_worktree_uses_its_own_config(self):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "fixture"], check=True)
        with tempfile.TemporaryDirectory() as other:
            worktree = Path(other) / "linked"
            subprocess.run(["git", "-C", str(self.root), "worktree", "add", "-q", "--detach", str(worktree)], check=True)
            MODULE.dev_config.create_config(worktree / ".dev.json", VALID_DOC)
            with patch.object(MODULE, "verify_gh_cli_login", return_value=VERIFIED):
                code, result = self.run_cli("--repo-dir", str(worktree), "--config", str(worktree / ".dev.json"),
                                            "--mode", "check-gh-account")
            self.assertEqual((0, "verified"), (code, result["status"]))
            self.assert_rejected_before_probes(self.root / ".dev.json", "--repo-dir", str(worktree))

    def test_first_use_before_and_after_git_initialization(self):
        for git_project in (False, True):
            with self.subTest(git_project=git_project), tempfile.TemporaryDirectory() as other:
                root = Path(other)
                if git_project:
                    subprocess.run(["git", "init", "-q", other], check=True)
                with patch.object(MODULE, "verify_gh_cli_login", return_value=VERIFIED):
                    code, result = self.run_cli("--repo-dir", other, "--mode", "check-gh-account",
                                                "--setup-account-check", "--account", VALID_DOC["github"]["account"])
                    self.assertEqual((0, "candidate_verified"), (code, result["status"]))
                    self.assertFalse((root / ".dev.json").exists())
                    MODULE.dev_config.create_config(root / ".dev.json", VALID_DOC)
                    if git_project:
                        MODULE.dev_config.ensure_excluded(root)
                    code, result = self.run_cli("--repo-dir", other, "--mode", "check-gh-account")
                    self.assertEqual((0, "verified"), (code, result["status"]))

    def test_root_failure_cannot_be_bypassed_with_explicit_config(self):
        with patch.object(MODULE.dev_config, "find_git_root",
                          side_effect=MODULE.dev_config.ConfigError("git_provenance_unavailable", "unavailable")):
            code, result = self.run_cli("--config", str(self.root / ".dev.json"), "--mode", "check-gh-account")
        self.assertEqual((2, "git_provenance_unavailable"), (code, result["reason_code"]))
