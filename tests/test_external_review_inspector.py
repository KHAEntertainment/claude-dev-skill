#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import errno
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


def comments_selection_block(query: str) -> str:
    """Extract the `comments(first:100){...}` selection set from the
    `fetch_threads` GraphQL query, brace-matching so nested selections
    (`author{login}`, `commit{oid}`, ...) do not truncate it early.
    """
    marker = "comments(first:100){"
    start = query.index(marker) + len(marker) - 1
    depth = 0
    for index in range(start, len(query)):
        if query[index] == "{":
            depth += 1
        elif query[index] == "}":
            depth -= 1
            if depth == 0:
                return query[start : index + 1]
    raise AssertionError("unbalanced braces in comments selection")


class ExternalReviewInspectorTests(unittest.TestCase):
    def test_submitted_head_thread_comment_completes(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = []
        threads = [{"id": "submitted", "comments": {"nodes": [{"author": {"login": "coderabbitai"}, "state": "SUBMITTED", "commit": {"oid": "current-head"}, "body": "finding"}]}}]
        result = MODULE.inspect(current, threads, recent, policy(), {"submitted": "advisory"})
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["completed_on_head"], ["coderabbit"])
        self.assertEqual(result["stale_reviewers"], [])

    def test_pending_head_thread_comment_does_not_complete(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [{"id": "old", "author": {"login": "coderabbitai"}, "state": "CHANGES_REQUESTED", "commit": {"oid": "old-head"}}]
        threads = [{"id": "draft", "comments": {"nodes": [{"author": {"login": "coderabbitai"}, "state": "PENDING", "commit": {"oid": "current-head"}, "body": "draft"}]}}]
        result = MODULE.inspect(current, threads, recent, policy(), {"draft": "advisory"})
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["completed_on_head"], [])
        self.assertEqual(result["stale_reviewers"], ["coderabbit"])

    def test_inactive_head_thread_comments_do_not_erase_stale_review(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [{"id": "old", "author": {"login": "coderabbitai"}, "state": "CHANGES_REQUESTED", "commit": {"oid": "old-head"}}]
        for resolved, outdated, minimized in ((True, False, False), (False, True, False), (False, False, True)):
            with self.subTest(resolved=resolved, outdated=outdated, minimized=minimized):
                threads = [{"id": "thread", "isResolved": resolved, "isOutdated": outdated,
                            "comments": {"nodes": [{"author": {"login": "coderabbitai"},
                            "commit": {"oid": "current-head"}, "isMinimized": minimized}]}}]
                result = MODULE.inspect(current, threads, recent, policy(), {})
                self.assertEqual(result["state"], "pending")
                self.assertEqual(result["stale_reviewers"], ["coderabbit"])

    def test_thread_comment_order_cannot_hide_active_finding(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        for nodes in (
            [{"author": {"login": "coderabbitai"}, "state": "SUBMITTED", "commit": {"oid": "current-head"}, "body": "visible"},
             {"author": {"login": "coderabbitai"}, "state": "SUBMITTED", "commit": {"oid": "current-head"}, "isMinimized": True, "body": "hidden"}],
            [{"author": {"login": "coderabbitai"}, "state": "SUBMITTED", "commit": {"oid": "current-head"}, "isMinimized": True, "body": "hidden"},
             {"author": {"login": "coderabbitai"}, "state": "SUBMITTED", "commit": {"oid": "current-head"}, "body": "visible"}],
        ):
            result = MODULE.inspect(current, [{"id": "thread", "comments": {"nodes": nodes}}], recent, policy(), {})
            self.assertEqual(result["state"], "pending")
            self.assertEqual(len(result["untriaged_findings"]), 1)

    def test_full_nested_comment_page_is_incomplete(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        comments = [{"author": {"login": "coderabbitai"}, "commit": {"oid": "current-head"}}] * 100
        result = MODULE.inspect(current, [{"id": "full", "comments": {"nodes": comments}}], recent, policy(), {})
        self.assertEqual(result["state"], "incomplete")
        self.assertIn("page limit", result["errors"][0])

    def test_older_unsubmitted_reviews_remain_pending_without_stale_claim(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        for with_check in (True, False):
            if not with_check:
                current["statusCheckRollup"] = []
            for state in ("PENDING", "DISMISSED", None, "UNKNOWN", "CHANGES_REQUESTED"):
                with self.subTest(state=state, with_check=with_check):
                    current["reviews"] = [{
                        "id": "older", "author": {"login": "coderabbitai"},
                        "state": state, "commit": {"oid": "older-head"},
                    }]
                    result = MODULE.inspect(current, threads, recent, policy(), {})
                    self.assertEqual(result["state"], "pending")
                    self.assertEqual(result["pending_reviewers"], ["coderabbit"])
                    self.assertEqual(result["completed_on_head"], [])
                    submitted = state == "CHANGES_REQUESTED"
                    self.assertEqual(result["stale_reviewers"], ["coderabbit"] if submitted else [])
                    reasons = result["pending_reasons"]["coderabbit"]
                    if submitted:
                        self.assertIn("submitted review at an earlier head requested changes", reasons)
                    else:
                        # Stricter than matching one literal: no stale reason of
                        # any wording may appear for an unsubmitted state.
                        self.assertFalse(any("earlier head" in reason for reason in reasons))
                        self.assertTrue(any("no " in reason for reason in reasons))

    def test_unsubmitted_head_review_does_not_erase_old_objection(self):
        result = inspect_fixture("unsubmitted-review-at-head.json")
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["completed_on_head"], [])
        self.assertEqual(result["stale_reviewers"], ["coderabbit"])

    def test_only_explicit_submitted_states_count(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "unsubmitted-review-at-head.json")
        review = current["reviews"][-1]
        for state in (None, "", "UNKNOWN", "PENDING", "DISMISSED"):
            with self.subTest(state=state):
                review["state"] = state
                result = MODULE.inspect(current, threads, recent, policy(), {})
                self.assertEqual(result["state"], "pending")
                self.assertEqual(result["stale_reviewers"], ["coderabbit"])
        del review["state"]
        self.assertEqual(MODULE.inspect(current, threads, recent, policy(), {})["state"], "pending")
        for state in ("COMMENTED", "APPROVED", "CHANGES_REQUESTED"):
            with self.subTest(state=state):
                review["state"] = state
                review["submittedAt"] = "2026-09-08T20:00:00Z"
                result = MODULE.inspect(current, threads, recent, policy(), {})
                self.assertEqual(result["completed_on_head"], ["coderabbit"])
                self.assertEqual(result["stale_reviewers"], [])

    def test_failed_snapshot_write_leaves_no_partial_and_retry_succeeds(self):
        raw = ' { "number": 21, "headRefOid": "head" }\n'
        original = MODULE.tempfile.NamedTemporaryFile
        def disk_full_file(*args, **kwargs):
            output = original(*args, **kwargs)
            real_write = output.write
            def partial_write(value):
                real_write(value[:12])
                output.flush()
                raise OSError(errno.ENOSPC, "disk full")
            output.write = partial_write
            return output
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "payload.json"
            with mock.patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, "")):
                with mock.patch.object(MODULE.tempfile, "NamedTemporaryFile", side_effect=disk_full_file):
                    with self.assertRaisesRegex(MODULE.InspectionError, "disk full"):
                        MODULE.fetch_pr("owner/repo", 21, snapshot)
                self.assertFalse(snapshot.exists())
                self.assertEqual(list(Path(directory).iterdir()), [])
                MODULE.fetch_pr("owner/repo", 21, snapshot)
                self.assertEqual(snapshot.read_text(), raw)
                self.assertEqual(list(Path(directory).iterdir()), [snapshot])

    def test_green_check_preserves_stale_review(self):
        result = inspect_fixture("green-check-stale-review.json")
        self.assertEqual(result["state"], "pending", result)
        self.assertEqual(result["stale_reviewers"], ["coderabbit"])
        self.assertEqual(result["completed_on_head"], [])

    def test_green_check_without_review_is_pending(self):
        result = inspect_fixture("green-check-no-review.json")
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["completed_on_head"], [])
        self.assertEqual(result["check_only_reviewers"], ["coderabbit"])
        self.assertIn("no submitted review or review thread", result["pending_reasons"]["coderabbit"][0])
        self.assertEqual(result["parked_comments"], [{
            "reviewer": "coderabbit",
            "url": "https://github.com/example/project/pull/21#issuecomment-1",
        }])

    def test_check_only_comment_detection_is_body_independent(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        for body in (None, "", "rate limit", "Review complete", "unrelated"):
            with self.subTest(body=body):
                current["comments"][0]["body"] = body
                result = MODULE.inspect(current, threads, recent, policy(), {})
                self.assertEqual(result["state"], "pending")
                self.assertEqual(len(result["parked_comments"]), 1)
        current["comments"] = None
        result = MODULE.inspect(current, threads, recent, policy(), {})
        self.assertEqual(result["parked_comments"], [])
        self.assertEqual(result["state"], "pending")

    def test_green_check_with_real_head_review_clears(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-stale-review.json")
        current["reviews"].append({"id": "new-review", "author": {"login": "coderabbitai"},
                                   "state": "COMMENTED", "submittedAt": "2026-09-08T12:00:00Z",
                                   "commit": {"oid": "current-head"}})
        result = MODULE.inspect(current, threads, recent, policy(), {})
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["check_only_reviewers"], [])
        self.assertEqual(result["stale_reviewers"], [])

    def test_green_check_with_head_thread_counts_as_evidence(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        threads = [{"id": "thread", "comments": [{"author": {"login": "coderabbitai"},
                    "state": "SUBMITTED", "commit": {"oid": "current-head"}, "body": "Finding"}]}]
        result = MODULE.inspect(current, threads, recent, policy(), {"thread": "advisory"})
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["completed_on_head"], ["coderabbit"])

    def test_failed_or_pending_status_is_not_completion(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-stale-review.json")
        for status, state in (("PENDING", "pending"), ("FAILURE", "incomplete")):
            with self.subTest(status=status):
                current["statusCheckRollup"][0]["state"] = status
                result = MODULE.inspect(current, threads, recent, policy(), {})
                self.assertEqual(result["state"], state)
                self.assertEqual(result["completed_on_head"], [])
                self.assertEqual(result["stale_reviewers"], ["coderabbit"])

    def test_payload_snapshot_preserves_exact_response_and_cannot_overwrite(self):
        raw = ' { "headRefOid": "head", "comments": [] }\n'
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "payload.json"
            with mock.patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, "")):
                value = MODULE.fetch_pr("owner/repo", 1, snapshot)
                self.assertEqual(value, json.loads(raw))
                self.assertEqual(snapshot.read_text(), raw)
                with self.assertRaises(MODULE.InspectionError):
                    MODULE.fetch_pr("owner/repo", 1, snapshot)
                self.assertEqual(snapshot.read_text(), raw)

    def test_dependency_failure_is_not_empty_success(self):
        with mock.patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "permission denied")):
            with self.assertRaisesRegex(MODULE.InspectionError, "permission denied"):
                MODULE.fetch_pr("owner/repo", 1)

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
                "submittedAt": "2026-09-08T12:00:00Z",
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
            {"id": "old", "state": "COMMENTED", "author": {"login": "kilocode-bot"}, "submittedAt": "2026-09-08T11:00:00Z", "commit": {"oid": "old-head"}},
            {"id": "new", "state": "COMMENTED", "author": {"login": "kilocode-bot"}, "submittedAt": "2026-09-08T12:00:00Z", "commit": {"oid": "head-10"}},
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


class VerdictRegressionTests(unittest.TestCase):
    def make(self, states):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [{"author":{"login":"coderabbitai"},"state":s,"commit":{"oid":"current-head"},"submittedAt":t} for s,t in states]
        return MODULE.inspect(current, threads, recent, policy(), {})
    def test_changes_requested_blocks(self): self.assertEqual(self.make([("CHANGES_REQUESTED","2026-09-08T20:00:00Z")])["state"], "blocking")
    def test_approved_clears(self): self.assertEqual(self.make([("APPROVED","2026-09-08T20:00:00Z")])["state"], "clear")
    def test_commented_clears(self): self.assertEqual(self.make([("COMMENTED","2026-09-08T20:00:00Z")])["state"], "clear")
    def test_dismissed_pending(self): self.assertEqual(self.make([("DISMISSED","2026-09-08T20:00:00Z")])["state"], "pending")
    def test_approval_after_rejection_clears(self): self.assertEqual(self.make([("CHANGES_REQUESTED","2026-09-08T19:00:00Z"),("APPROVED","2026-09-08T20:00:00Z")])["state"], "clear")
    def test_rejection_after_approval_blocks(self): self.assertEqual(self.make([("APPROVED","2026-09-08T19:00:00Z"),("CHANGES_REQUESTED","2026-09-08T20:00:00Z")])["state"], "blocking")
    def test_rejection_with_green_check_blocks(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["reviews"] = [{"author":{"login":"coderabbitai"},"state":"CHANGES_REQUESTED","commit":{"oid":"current-head"},"submittedAt":"2026-09-08T20:00:00Z"}]
        self.assertEqual(MODULE.inspect(current, [], recent, policy(), {})["state"], "blocking")
    def test_rejection_with_failing_check_stays_blocking_with_errors(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["reviews"] = [{"author":{"login":"coderabbitai"},"state":"CHANGES_REQUESTED","commit":{"oid":"current-head"},"submittedAt":"2026-09-08T20:00:00Z"}]
        current["statusCheckRollup"] = [{"name":"CodeRabbit","status":"failure","conclusion":"failure"}]
        result = MODULE.inspect(current, [], recent, policy(), {})
        self.assertEqual(result["state"], "blocking")
        self.assertTrue(result["errors"])

    def test_errors_without_rejection_stay_incomplete(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = [{"name":"CodeRabbit","status":"failure","conclusion":"failure"}]
        result = MODULE.inspect(current, [], recent, policy(), {})
        self.assertEqual(result["state"], "incomplete")

    def head_review(self, state, submitted_at="__omit__"):
        """One submitted review at head, with submittedAt controllable per case."""
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        review = {
            "author": {"login": "coderabbitai"},
            "state": state,
            "commit": {"oid": "current-head"},
        }
        if submitted_at != "__omit__":
            review["submittedAt"] = submitted_at
        current["reviews"] = [review]
        return MODULE.inspect(current, [], recent, policy(), {})

    def assert_unorderable(self, result):
        """A review with no usable timestamp never establishes completion."""
        self.assertNotEqual(result["state"], "clear")
        self.assertNotIn("coderabbit", result["completed_on_head"])
        self.assertIn(
            "submittedAt",
            " ".join(result["pending_reasons"].get("coderabbit", [])),
        )

    def test_approval_at_head_with_valid_timestamp_still_clears(self):
        result = self.head_review("APPROVED", "2026-09-08T20:00:00Z")
        self.assertEqual(result["state"], "clear")
        self.assertEqual(result["completed_on_head"], ["coderabbit"])

    def test_approval_at_head_with_missing_timestamp_is_not_completion(self):
        self.assert_unorderable(self.head_review("APPROVED"))

    def test_approval_at_head_with_null_timestamp_is_not_completion(self):
        self.assert_unorderable(self.head_review("APPROVED", None))

    def test_approval_at_head_with_empty_timestamp_is_not_completion(self):
        self.assert_unorderable(self.head_review("APPROVED", ""))

    def test_approval_at_head_with_blank_timestamp_is_not_completion(self):
        self.assert_unorderable(self.head_review("APPROVED", "   "))

    def test_comment_at_head_with_missing_timestamp_is_not_completion(self):
        self.assert_unorderable(self.head_review("COMMENTED"))

    def test_rejection_at_head_with_missing_timestamp_still_blocks(self):
        # Fail closed both ways: an unorderable verdict cannot clear the gate,
        # and it cannot soften a rejection we already read either.
        result = self.head_review("CHANGES_REQUESTED")
        self.assertEqual(result["state"], "blocking")
        self.assertEqual(result["blocking_reviewers"], ["coderabbit"])

    def test_untimestamped_approval_cannot_override_earlier_rejection(self):
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [
            {"author":{"login":"coderabbitai"},"state":"CHANGES_REQUESTED","commit":{"oid":"current-head"},"submittedAt":"2026-09-08T19:00:00Z"},
            {"author":{"login":"coderabbitai"},"state":"APPROVED","commit":{"oid":"current-head"}},
        ]
        result = MODULE.inspect(current, [], recent, policy(), {})
        self.assertEqual(result["state"], "blocking")
        self.assertEqual(result["blocking_reviewers"], ["coderabbit"])

    def stale_review(self, state):
        """One submitted review at an earlier head."""
        current, _, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [{
            "author": {"login": "coderabbitai"},
            "state": state,
            "submittedAt": "2026-09-08T12:00:00Z",
            "commit": {"oid": "old-head"},
        }]
        result = MODULE.inspect(current, [], recent, policy(), {})
        return result, " ".join(result["pending_reasons"]["coderabbit"])

    def test_stale_rejection_reason_names_the_rejection(self):
        result, reasons = self.stale_review("CHANGES_REQUESTED")
        self.assertEqual(result["state"], "pending")
        self.assertIn("submitted review at an earlier head requested changes", reasons)

    def test_stale_approval_reason_names_the_approval(self):
        result, reasons = self.stale_review("APPROVED")
        self.assertEqual(result["state"], "pending")
        self.assertIn("submitted review at an earlier head approved", reasons)

    def test_stale_rejection_and_approval_read_differently(self):
        # Issue #29: these were byte-identical, so a lead recording a bypass
        # could not say which kind of stale review they were waiving.
        _, rejection = self.stale_review("CHANGES_REQUESTED")
        _, approval = self.stale_review("APPROVED")
        self.assertNotEqual(rejection, approval)

    def test_stale_verdicts_do_not_change_merge_behaviour(self):
        # Reporting only: both stay pending, exactly as before.
        rejection, _ = self.stale_review("CHANGES_REQUESTED")
        approval, _ = self.stale_review("APPROVED")
        self.assertEqual(rejection["state"], "pending")
        self.assertEqual(approval["state"], "pending")
        self.assertEqual(rejection["stale_reviewers"], ["coderabbit"])
        self.assertEqual(approval["stale_reviewers"], ["coderabbit"])

    def test_stale_comment_reason_names_the_comment(self):
        _, reasons = self.stale_review("COMMENTED")
        self.assertIn("submitted review at an earlier head commented", reasons)

    def test_older_rejection_is_pending(self):
        current, threads, recent = MODULE.load_fixture(FIXTURES / "green-check-no-review.json")
        current["statusCheckRollup"] = []
        current["reviews"] = [{"author":{"login":"coderabbitai"},"state":"CHANGES_REQUESTED","commit":{"oid":"old-head"}}]
        self.assertEqual(MODULE.inspect(current, threads, recent, policy(), {})["state"], "pending")


class LiveFetchThreadsTests(unittest.TestCase):
    """fetch_threads() is the one path a fully green suite never touched
    (Issue #25): every test above reaches inspect() through load_fixture()
    and never calls fetch_threads at all, so replacing it with `return []`
    left every test green. These exercise it directly against a stubbed
    run_json -- no network access -- so the #23 guards (nested pagination,
    the comment `state` field) cannot be silently removed again unnoticed.
    """

    def query_from(self, command):
        for index, token in enumerate(command):
            if token == "-f" and index + 1 < len(command) and command[index + 1].startswith("query="):
                return command[index + 1][len("query="):]
        raise AssertionError(f"no query= argument found in {command}")

    def test_fetch_threads_paginates_across_outer_thread_pages(self):
        # Two outer pages of review threads. Replacing fetch_threads with
        # `return []`, or dropping the outer pageInfo.hasNextPage loop,
        # would return zero or one thread instead of two.
        page_one = {
            "data": {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": [{"id": "thread-1", "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
            }}}}
        }
        page_two = {
            "data": {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": [{"id": "thread-2", "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}}}],
                "pageInfo": {"hasNextPage": False, "endCursor": ""},
            }}}}
        }
        responses = [page_one, page_two]
        calls = []

        def fake_run_json(command, **kwargs):
            calls.append(command)
            return responses.pop(0)

        with mock.patch.object(MODULE, "run_json", side_effect=fake_run_json):
            threads = MODULE.fetch_threads("owner/repo", 7)

        self.assertEqual([thread["id"] for thread in threads], ["thread-1", "thread-2"])
        self.assertEqual(len(calls), 2)
        self.assertIn("cursor=cursor-1", calls[1])

    def test_fetch_threads_query_selects_state_and_nested_page_guard_fields(self):
        response = {
            "data": {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": ""},
            }}}}
        }
        captured = {}

        def fake_run_json(command, **kwargs):
            captured["command"] = command
            return response

        with mock.patch.object(MODULE, "run_json", side_effect=fake_run_json):
            MODULE.fetch_threads("owner/repo", 7)

        query = self.query_from(captured["command"])
        block = comments_selection_block(query)
        tokens = block.split()
        self.assertIn("state", tokens, block)
        self.assertIn("pageInfo{hasNextPage}", tokens, block)

    def test_fetch_threads_raises_when_nested_comment_page_is_full(self):
        response = {
            "data": {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": [{
                    "id": "thread-full",
                    "comments": {
                        "nodes": [{"id": f"c{i}"} for i in range(100)],
                        "pageInfo": {"hasNextPage": True},
                    },
                }],
                "pageInfo": {"hasNextPage": False, "endCursor": ""},
            }}}}
        }
        with mock.patch.object(MODULE, "run_json", return_value=response):
            with self.assertRaisesRegex(MODULE.InspectionError, "exceed the fetched page"):
                MODULE.fetch_threads("owner/repo", 7)

    def test_fetch_threads_comment_state_reaches_submitted_state_gate(self):
        def comment(state):
            return {
                "id": "c1", "body": "finding", "url": "https://example/pr/7#c1",
                "state": state, "author": {"login": "coderabbitai"},
                "commit": {"oid": "head-sha"},
            }

        def response_for(state):
            return {
                "data": {"repository": {"pullRequest": {"reviewThreads": {
                    "nodes": [{
                        "id": "thread-1", "isResolved": False, "isOutdated": False,
                        "comments": {"nodes": [comment(state)], "pageInfo": {"hasNextPage": False}},
                    }],
                    "pageInfo": {"hasNextPage": False, "endCursor": ""},
                }}}}
            }

        current = {
            "number": 7, "headRefOid": "head-sha", "reviews": [], "comments": [],
            "reviewRequests": [], "statusCheckRollup": [],
        }

        with mock.patch.object(MODULE, "run_json", return_value=response_for("SUBMITTED")):
            submitted_threads = MODULE.fetch_threads("owner/repo", 7)
        submitted_result = MODULE.inspect(current, submitted_threads, [], policy(), {"thread-1": "advisory"})
        self.assertEqual(submitted_result["completed_on_head"], ["coderabbit"])
        self.assertEqual(submitted_result["state"], "clear")

        with mock.patch.object(MODULE, "run_json", return_value=response_for("PENDING")):
            pending_threads = MODULE.fetch_threads("owner/repo", 7)
        pending_result = MODULE.inspect(current, pending_threads, [], policy(), {"thread-1": "advisory"})
        self.assertEqual(pending_result["completed_on_head"], [])
        self.assertEqual(pending_result["state"], "pending")


if __name__ == "__main__":
    unittest.main()
