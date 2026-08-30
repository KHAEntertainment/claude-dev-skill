#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "dev" / "scripts" / "inspect_external_reviews.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "external_reviews"

SPEC = importlib.util.spec_from_file_location("external_reviews", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def policy(*, required: set[str] | None = None, ignored: set[str] | None = None):
    return MODULE.ReviewerPolicy(
        identities={name: set(values) for name, values in MODULE.DEFAULT_IDENTITIES.items()},
        check_markers={name: set(values) for name, values in MODULE.DEFAULT_CHECK_MARKERS.items()},
        required=required or set(),
        ignored=ignored or set(),
    )


def inspect_fixture(name: str, *, dispositions: dict[str, str] | None = None, review_policy=None):
    current, threads, recent = MODULE.load_fixture(FIXTURES / name)
    return MODULE.inspect(current, threads, recent, review_policy or policy(), dispositions or {})


class ExternalReviewInspectorTests(unittest.TestCase):
    def test_no_reviewer_is_not_applicable(self):
        result = inspect_fixture("no-reviewer.json")
        self.assertEqual(result["state"], "not_applicable")
        self.assertEqual(result["expected_reviewers"], [])

    def test_all_default_reviewers_clear_on_current_head(self):
        result = inspect_fixture("trusted-clear.json")
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["expected_reviewers"], ["coderabbit", "github-copilot", "kilo"])
        self.assertEqual(result["pending_reviewers"], [])

    def test_copilot_comment_requires_triage(self):
        result = inspect_fixture("copilot-unresolved.json")
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["untriaged_findings"][0]["id"], "copilot-finding-1")
        self.assertIn("github-copilot", result["pending_reviewers"])

    def test_active_finding_body_is_bounded(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "copilot-unresolved.json")
        result = MODULE.inspect(current, threads, recent, policy(), {}, max_body_chars=20)
        body = result["findings"][0]["body"]
        self.assertEqual(len(body), 20)
        self.assertTrue(body.endswith("…"))

    def test_copilot_author_login_without_bot_suffix_is_trusted(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "no-reviewer.json")
        current["reviews"] = [
            {
                "id": "copilot-review",
                "author": {"login": "copilot-pull-request-reviewer"},
                "state": "COMMENTED",
                "commit": {"oid": "head-10"},
            }
        ]
        result = MODULE.inspect(current, threads, recent, policy(), {})
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["observed_reviewers"], ["github-copilot"])

    def test_advisory_and_blocking_dispositions(self):
        advisory = inspect_fixture(
            "copilot-unresolved.json", dispositions={"copilot-finding-1": "advisory"}
        )
        self.assertEqual(advisory["state"], "clear")
        blocking = inspect_fixture(
            "copilot-unresolved.json", dispositions={"copilot-finding-1": "blocking"}
        )
        self.assertEqual(blocking["state"], "blocking")
        self.assertEqual(blocking["blocking_findings"][0]["reviewer"], "github-copilot")

    def test_false_positive_clears_with_recorded_disposition(self):
        result = inspect_fixture(
            "copilot-unresolved.json", dispositions={"copilot-finding-1": "false_positive"}
        )
        self.assertEqual(result["state"], "clear")

    def test_stale_copilot_review_is_pending(self):
        result = inspect_fixture("copilot-stale.json")
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["stale_reviewers"], ["github-copilot"])

    def test_current_review_supersedes_older_review_from_same_reviewer(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "no-reviewer.json")
        current["reviews"] = [
            {"id": "old", "author": {"login": "kilocode-bot"}, "commit": {"oid": "old-head"}},
            {"id": "new", "author": {"login": "kilocode-bot"}, "commit": {"oid": "head-10"}},
        ]
        result = MODULE.inspect(current, threads, recent, policy(), {})
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["stale_reviewers"], [])

    def test_recent_pr_evidence_marks_reviewer_expected(self):
        result = inspect_fixture("recent-coderabbit.json")
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["recently_observed_reviewers"], ["coderabbit"])

    def test_required_and_ignored_precedence(self):
        required = inspect_fixture(
            "no-reviewer.json", review_policy=policy(required={"github-copilot"})
        )
        self.assertEqual(required["state"], "pending")
        ignored = inspect_fixture(
            "copilot-unresolved.json",
            review_policy=policy(required={"github-copilot"}, ignored={"github-copilot"}),
        )
        self.assertEqual(ignored["state"], "not_applicable")

    def test_failed_check_without_findings_is_incomplete(self):
        result = inspect_fixture("failed-check.json")
        self.assertEqual(result["state"], "incomplete")
        self.assertIn("without readable", result["errors"][0])

    def test_unknown_bot_is_reported_but_not_trusted(self):
        result = inspect_fixture("unknown-bot.json")
        self.assertEqual(result["state"], "not_applicable")
        self.assertEqual(result["unknown_bot_identities"], ["excellent-review-bot[bot]"])

    def test_ordinary_review_named_check_is_not_reported_as_bot(self):
        result = inspect_fixture("ordinary-review-check.json")
        self.assertEqual(result["state"], "not_applicable")
        self.assertEqual(result["unknown_bot_identities"], [])

    def test_fixture_pages_are_flattened(self):
        result = inspect_fixture("paginated-threads.json")
        self.assertEqual(result["state"], "clear")
        self.assertEqual(len(result["findings"]), 2)

    def test_custom_identity_is_detected(self):
        custom_policy = policy()
        custom_policy.identities["acme-review"] = {"acme-reviewer[bot]"}
        current, threads, recent = MODULE.load_fixture(FIXTURES / "no-reviewer.json")
        current["reviewRequests"] = [{"login": "acme-reviewer[bot]"}]
        result = MODULE.inspect(current, threads, recent, custom_policy, {})
        self.assertEqual(result["state"], "pending")
        self.assertIn("acme-review", result["expected_reviewers"])

    def test_kilo_hyphenated_bot_login_is_trusted(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "no-reviewer.json")
        current["reviewRequests"] = [{"login": "kilo-code-bot"}]
        result = MODULE.inspect(current, threads, recent, policy(), {})
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["observed_reviewers"], ["kilo"])
        self.assertEqual(result["unknown_bot_identities"], [])

    def test_zero_recent_pr_limit_makes_no_github_request(self):
        with mock.patch.object(MODULE, "run_json") as run_json:
            self.assertEqual(MODULE.fetch_recent("owner/repo", 1, 0), [])
            run_json.assert_not_called()

    def test_cli_accepts_dispositions(self):
        with tempfile.TemporaryDirectory() as directory:
            dispositions = Path(directory) / "dispositions.json"
            dispositions.write_text(json.dumps({"copilot-finding-1": "advisory"}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--fixture",
                    str(FIXTURES / "copilot-unresolved.json"),
                    "--dispositions",
                    str(dispositions),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["state"], "clear")

    def test_cli_trusted_reviewer_filter_overrides_defaults(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--fixture",
                str(FIXTURES / "trusted-clear.json"),
                "--trusted-reviewer",
                "github-copilot",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["expected_reviewers"], ["github-copilot"])
        self.assertEqual(result["unknown_bot_identities"], [])

    def test_cli_rejects_required_reviewer_that_is_not_trusted(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--fixture",
                str(FIXTURES / "no-reviewer.json"),
                "--trusted-reviewer",
                "coderabbit",
                "--required-reviewer",
                "github-copilot",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "incomplete")

    def test_additional_identity_also_matches_check_context(self):
        identities = {name: set(values) for name, values in MODULE.DEFAULT_IDENTITIES.items()}
        markers = {name: set(values) for name, values in MODULE.DEFAULT_CHECK_MARKERS.items()}
        MODULE.parse_identity("acme=acme-review-app", identities, markers)
        custom_policy = MODULE.ReviewerPolicy(
            identities=identities,
            check_markers=markers,
            required=set(),
            ignored=set(),
        )
        current, threads, recent = MODULE.load_fixture(FIXTURES / "no-reviewer.json")
        current["statusCheckRollup"] = [
            {"context": "acme-review-app", "state": "PENDING"}
        ]
        result = MODULE.inspect(current, threads, recent, custom_policy, {})
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["observed_reviewers"], ["acme"])

    def test_malformed_fixture_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "bad.json"
            fixture.write_text("not-json", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--fixture", str(fixture)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
