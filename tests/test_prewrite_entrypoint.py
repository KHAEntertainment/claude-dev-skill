"""Regression checks through production argument parsing and pre-write wiring.

Network/credential boundaries are injected; local config and Git provenance
are real. These are not evidence of live HTTPS/SSH authentication.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_repository_identity import MODULE, VALID_DOC, CANONICAL, ORIGIN_HTTPS

VERIFIED = {"status": "verified", "reason_code": "account_matches", "reason": "test account"}
REJECTED = {"status": "incomplete", "reason_code": "account_mismatch", "reason": "test mismatch"}


class PrewriteEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        MODULE.dev_config.create_config(self.root / ".dev.json", VALID_DOC)
        MODULE.dev_config.ensure_excluded(self.root)

    def run_cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["resolver", "--repo-dir", str(self.root), *args]), contextlib.redirect_stdout(output):
            code = MODULE.main()
        return code, json.loads(output.getvalue())

    def test_all_successful_account_modes_exit_zero(self):
        cases = [("check-gh-account", "verify_gh_cli_login", []),
                 ("check-https-account", "verify_https_account", ["--url", ORIGIN_HTTPS]),
                 ("check-ssh-account", "verify_ssh_url_account", ["--url", "git@github.com:A/B.git"])]
        for mode, name, args in cases:
            with self.subTest(mode=mode), patch.object(MODULE, name, return_value=VERIFIED) as probe:
                code, payload = self.run_cli("--mode", mode, "--account", "Expected", *args)
                self.assertEqual(0, code)
                self.assertEqual("verified", payload["status"])
                probe.assert_called_once()

    def push(self, urls, responses):
        with contextlib.ExitStack() as stack:
            for name, value in [("collect_remotes", ({"origin": [ORIGIN_HTTPS]}, {"origin": urls})),
                                ("get_effective_push_remote", "origin"),
                                ("collect_gh_default", None), ("collect_verified_name", CANONICAL)]:
                stack.enter_context(patch.object(MODULE, name, return_value=value))
            probe = stack.enter_context(patch.object(MODULE, "verify_https_account", side_effect=responses))
            dry = stack.enter_context(patch.object(MODULE, "verify_branch_and_dry_run", return_value={
                "status": "ready", "remote": "origin", "refspec": "feature/test:refs/heads/feature/test"}))
            code, payload = self.run_cli("--assigned-branch", "feature/test")
            return code, payload, probe.call_args_list, dry.call_count

    def test_push_verifies_every_url_before_dry_run(self):
        other = ORIGIN_HTTPS.removesuffix(".git")
        code, payload, probes, dry = self.push([ORIGIN_HTTPS, other], [VERIFIED, VERIFIED])
        self.assertEqual(0, code)
        self.assertEqual([ORIGIN_HTTPS, other], [call.args[1] for call in probes])
        self.assertEqual(1, dry)

    def test_second_push_url_account_mismatch_blocks_and_clears_target(self):
        code, payload, probes, dry = self.push([ORIGIN_HTTPS, ORIGIN_HTTPS.removesuffix(".git")], [VERIFIED, REJECTED])
        self.assertEqual(2, code)
        self.assertEqual("account_mismatch", payload["reason_code"])
        self.assertIsNone(payload["effective_push_remote"])
        self.assertEqual(2, len(probes))
        self.assertEqual(0, dry)

    def test_production_cannot_skip_access(self):
        code, payload = self.run_cli("--assigned-branch", "feature/test", "--no-verify-access")
        self.assertEqual(2, code)
        self.assertEqual("verification_required", payload["reason_code"])

    def test_destination_main_rejected_before_dry_run(self):
        with patch.object(MODULE, "get_current_branch", return_value="feature/test"), patch.object(MODULE, "read_command") as runner:
            result = MODULE.verify_branch_and_dry_run(self.root, remote="origin", assigned_branch="feature/test", dest_ref="refs/heads/main")
        self.assertEqual("destination_mismatch", result["reason_code"])
        runner.assert_not_called()

    def test_host_mismatch_rejected_before_api_call(self):
        with patch.dict(os.environ, {"GH_HOST": "enterprise.example"}), patch.object(MODULE, "read_command") as runner:
            result = MODULE.verify_gh_cli_login(self.root, "Expected")
        self.assertEqual("host_mismatch", result["reason_code"])
        runner.assert_not_called()

    def test_gh_user_endpoint_explicitly_pins_host(self):
        with patch.dict(os.environ, {"GH_HOST": "github.com"}), patch.object(MODULE, "read_command", return_value=(0, "Expected")) as runner:
            self.assertEqual("verified", MODULE.verify_gh_cli_login(self.root, "Expected")["status"])
        self.assertEqual(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"], runner.call_args.args[0])

    def test_ssh_exact_user_and_port_flow_to_config_and_probe(self):
        for url, host, port in [("git@corp-github:A/B.git", "corp-github", None),
                                ("ssh://git@github.com:443/A/B.git", "github.com", 443)]:
            with self.subTest(url=url), patch.object(MODULE, "detect_ssh_overrides", return_value=None), \
                    patch.object(MODULE, "resolve_ssh_effective_host", return_value=("github.com", "git", "443")) as config, \
                    patch.object(MODULE, "probe_ssh_account", return_value=(1, "Hi Expected! You've successfully authenticated")) as probe:
                result = MODULE.verify_ssh_url_account(self.root, url, "Expected")
                self.assertEqual("verified", result["status"])
                config.assert_called_once_with(self.root, host, user="git", port=port)
                probe.assert_called_once_with(self.root, host, "git", port=port)

    def test_ssh_config_applies_url_options(self):
        with patch.object(MODULE, "read_command", return_value=(0, "hostname github.com\nuser git\nport 443")) as runner:
            MODULE.resolve_ssh_effective_host(self.root, "corp-github", user="git", port=443)
        self.assertEqual(["ssh", "-G", "-l", "git", "-p", "443", "corp-github"], runner.call_args.args[0])

    def test_ssh_probe_does_not_add_host_keys(self):
        with patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "Hi Expected! You've successfully authenticated")) as runner:
            MODULE.probe_ssh_account(self.root, "corp-github", "git", port=443)
        argv = runner.call_args.args[0]
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("UpdateHostKeys=no", argv)
        self.assertEqual(["-p", "443", "git@corp-github"], argv[-3:])

    def test_ssh_effective_config_really_obeys_url_user_port(self):
        config = self.root / "ssh_config"
        config.write_text("Host corp-github\n HostName github.com\n User other-user\n Port 22\n")
        result = MODULE.resolve_ssh_effective_host(
            self.root, "corp-github", ssh_command=("ssh", "-F", str(config)), user="git", port=443)
        self.assertEqual(("github.com", "git", "443"), result)

    def test_https_credential_bearing_url_stops_before_lookup(self):
        with patch.object(MODULE, "fill_https_credential") as helper:
            result = MODULE.verify_https_account(self.root, "https://test:synthetic@github.com/A/B", "Expected")
        self.assertEqual("unsupported_transport_auth", result["reason_code"])
        self.assertNotIn("synthetic", result["reason"])
        helper.assert_not_called()

    def test_named_mutations_require_fresh_local_check(self):
        root = Path(__file__).resolve().parents[1] / "skills/dev"
        cases = [
            ("agents/worker-new.md", "Immediately before posting, re-run"),
            ("agents/worker-fix.md", "Immediately before posting, re-run"),
            ("agents/qa-agent.md", "Immediately before posting, re-run"),
            ("phases/phase4.md", "Immediately before each review submission, re-run"),
            ("phases/phase4.md", "immediately before each subsequent mutation"),
            ("phases/phase2.md", "Immediately before each close, edit, or comment"),
        ]
        for path, required in cases:
            with self.subTest(path=path, required=required):
                self.assertIn(required, (root / path).read_text())
        phase2 = (root / "phases/phase2.md").read_text()
        self.assertIn("gh pr list --repo github.com/<pullRequestRepository> --state merged", phase2)
        self.assertIn("gh repo create <github.pushRepository>", phase2)
        self.assertNotIn("gh repo create <account>/", phase2)
        self.assertNotIn("more than a few minutes", (root / "phases/phase4.md").read_text())


if __name__ == "__main__":
    unittest.main()
