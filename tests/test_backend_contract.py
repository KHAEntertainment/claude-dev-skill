from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "dev"


class BackendContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (SKILL / relative).read_text(encoding="utf-8")

    def test_contract_has_all_fail_closed_operations(self) -> None:
        contract = self.read("backends/contract.md")
        for operation in (
            "preflight",
            "prepare_worktree",
            "resolve_route",
            "launch",
            "message",
            "observe",
            "shutdown",
            "recover",
        ):
            self.assertIn(f"`{operation}`", contract)
        for topology in ("serial", "parallel"):
            self.assertIn(topology, contract)
        for backend in ("claude-native", "traycer", "incomplete"):
            self.assertIn(backend, contract)

    def test_claude_adapter_preserves_serial_and_agent_teams(self) -> None:
        adapter = self.read("backends/claude-native.md")
        self.assertIn("`serial`", adapter)
        self.assertIn("`parallel`", adapter)
        self.assertIn("Agent Teams", adapter)
        self.assertIn("tmux/iTerm", adapter)
        self.assertIn("Never silently", adapter)

    def test_traycer_command_contract_and_receive_capability(self) -> None:
        adapter = self.read("backends/traycer.md")
        required = (
            "rtk proxy traycer",
            "worktree create",
            "--workspace",
            "--source-branch",
            "--branch",
            "--workspace-entry",
            "--surface gui",
            "agent create",
            "agent send",
            "--expect-reply",
            "agent inbox",
            "agent transcript",
            "agent stop",
            "agent archive",
            "response ID",
            "cursor/page",
            "--carry-uncommitted",
        )
        for token in required:
            self.assertIn(token, adapter)
        self.assertIn("must never use `--carry-uncommitted`", adapter)
        self.assertIn("Codex/OpenCode", adapter)

    def test_route_precedence_validation_and_last_used(self) -> None:
        adapter = self.read("backends/traycer.md")
        project = adapter.index("Explicit `PROJECT_CONTEXT.md`")
        workspace = adapter.index("Workspace `.traycer/agent-selection-guide.md`")
        global_guide = adapter.index("Global `rtk proxy traycer agent selection-guide")
        lead = adapter.index("Lead route from the lead row")
        self.assertLess(project, workspace)
        self.assertLess(workspace, global_guide)
        self.assertLess(global_guide, lead)
        for token in ("list-harnesses", "list-harness-models", "list-profiles"):
            self.assertIn(token, adapter)
        self.assertIn("traycer_last_used", adapter)
        self.assertIn("Do not invent `read_only`", adapter)
        self.assertIn("invalid field", adapter)
        self.assertIn("unavailable model/profile", adapter)
        self.assertIn("do not substitute another route", adapter)

    def test_traycer_supports_both_topologies_without_backend_switching(self) -> None:
        adapter = self.read("phases/phase3.md")
        self.assertIn("Both Traycer topologies", adapter)
        self.assertIn("Topology controls scheduling and ownership", adapter)
        self.assertIn("Do not silently change backend or topology", adapter)

    def test_failures_never_trigger_claude_fallback(self) -> None:
        adapter = self.read("backends/traycer.md")
        for failure in (
            "missing CLI",
            "Host",
            "authentication",
            "permission",
            "A2A capability",
            "malformed JSON or NDJSON",
            "missing page",
        ):
            self.assertIn(failure, adapter)
        self.assertIn("never fall back to Claude-native", adapter)

    def test_state_schema_preserves_review_and_recovery_fields(self) -> None:
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        for token in (
            "schema_version",
            "execution_backend",
            "topology",
            "lead:",
            "reviewer:",
            "agent_id",
            "traycer_agent_id",
            "traycer_epic_id",
            "backend_source",
            "communication_response_id",
            "headRefOid",
            "external_review_state",
            "unresolved_actionable_findings",
            "review_deadline",
            "wait_extensions",
            "approved_review_requests",
            "approved_bypasses",
            "review_debt",
            "The Tech Lead is the sole writer",
        ):
            self.assertIn(token, state)
        for status in (
            "planned",
            "worktree_ready",
            "active",
            "blocked",
            "pr_created",
            "qa",
            "review",
            "complete",
            "stopped",
        ):
            self.assertIn(f"`{status}`", state)

    def test_qa_and_reviewer_are_distinct_clean_current_head_lanes(self) -> None:
        qa = self.read("agents/qa-agent.md")
        reviewer = self.read("agents/reviewer.md")
        phase3_5 = self.read("phases/phase3.5.md")
        traycer = self.read("backends/traycer.md")
        phase4 = self.read("phases/phase4.md")
        contract = self.read("backends/contract.md")
        self.assertIn("stale_head", qa)
        self.assertIn("rtk git status --short", qa)
        self.assertIn("distinct agent ID", reviewer)
        self.assertIn("from the QA agent", reviewer)
        self.assertIn("distinct from the reviewer agent", qa)
        self.assertIn("rtk git status --short", reviewer)
        self.assertIn("headRefOid", reviewer)
        self.assertIn("correlation/response ID", reviewer)
        self.assertIn("rev-parse", phase3_5)
        self.assertIn("unchanged checkout", phase3_5)
        self.assertIn("unchanged PR head", phase3_5)
        self.assertIn("the reviewer agent ID", phase3_5)
        self.assertIn("immutable local `HEAD`", traycer)
        self.assertIn("invalidate QA, internal review, and external-review", phase4)
        self.assertIn("and the QA agent", phase4)
        self.assertIn("distinct from each other", contract)
        self.assertIn("backend_source", contract)

    def test_implementation_lanes_carry_the_reuse_first_ladder(self) -> None:
        for relative in ("agents/worker-new.md", "agents/worker-fix.md"):
            prompt = self.read(relative)
            with self.subTest(prompt=relative):
                self.assertIn("Reuse-first ladder", prompt)
                self.assertIn("already in the codebase", prompt)
                self.assertIn("standard library", prompt)
                self.assertIn("already-installed dependency", prompt)
                self.assertIn("lowest rung", prompt)

    def test_safety_carveout_accompanies_the_ladder_in_both_lanes(self) -> None:
        # The ladder without the carve-out reads as licence to delete guards in
        # the name of minimality, so the two must never drift apart.
        for relative in ("agents/worker-new.md", "agents/worker-fix.md"):
            prompt = self.read(relative)
            with self.subTest(prompt=relative):
                self.assertIn("Safety carve-out", prompt)
                self.assertIn(
                    "Minimizing scope must never mean removing a guard.", prompt
                )
                for guard in (
                    "Validation",
                    "error handling",
                    "security",
                    "accessibility",
                ):
                    self.assertIn(guard, prompt)

    def test_prototype_lanes_state_the_opposing_principle(self) -> None:
        # Inverted guard. A negative assertion over prose is unbounded: it
        # cannot enumerate every paraphrase of a ladder, and a test asserting
        # only that the wrong thing is absent cannot tell a working guard from
        # a vacuous one. Asserting the opposing principle means a future edit
        # adding reuse-first guidance must first delete a sentence saying the
        # opposite - a visible, guarded act rather than an addition that slips
        # past untouched.
        for relative in (
            "agents/worker-prototype-frontend.md",
            "agents/worker-prototype-backend.md",
        ):
            prompt = self.read(relative)
            with self.subTest(prompt=relative):
                self.assertIn("Exploration Stance", prompt)
                self.assertIn("Exploration favors breadth over minimality.", prompt)
                self.assertIn("does not apply in this lane", prompt)
                self.assertIn("This exclusion is deliberate", prompt)
                # Cheap backstop for a literal copy of the ladder. The positive
                # assertions above are the actual guard; these two are not.
                self.assertNotIn("Reuse-first ladder", prompt)
                self.assertNotIn("lowest rung", prompt)

    def test_reviewer_checks_for_over_engineering_as_advisory(self) -> None:
        reviewer = self.read("agents/reviewer.md")
        self.assertIn("over-engineering", reviewer)
        self.assertIn("speculative abstraction", reviewer)
        self.assertIn("reimplemented by hand", reviewer)
        self.assertIn("`advisory` unless", reviewer)

    def test_completion_claims_require_executed_output(self) -> None:
        report_back = self.read("agents/report-back.md")
        qa = self.read("agents/qa-agent.md")
        for prompt in (report_back, qa):
            self.assertIn("executed command's actual output", prompt)
            self.assertIn("re-run the full Verification Gate", prompt)
        # qa-agent.md owns the canonical wording; report-back cross-references
        # it rather than restating it.
        self.assertIn("Tool Capability Boundary", report_back)
        self.assertIn("agents/qa-agent.md", report_back)
        self.assertIn("canonical definition", qa)

    def test_qa_score_cannot_read_absence_of_signal_as_a_pass(self) -> None:
        qa = self.read("agents/qa-agent.md")
        # No denominator, nothing executed, and an undetected framework are all
        # explicit outcomes rather than paths to an implicit 100.
        self.assertIn("qa_error: no acceptance criteria", qa)
        self.assertIn("qa_error: no verification executed", qa)
        self.assertIn("No test framework detected", qa)
        self.assertIn("never a silent skip", qa)
        # The score carries a coverage term, and Limitations feed the result.
        self.assertIn("not verified by test execution", qa)
        self.assertIn("Limitations are load-bearing", qa)
        self.assertIn("blocks the pass", qa)

    def test_coverage_term_predicate_is_decidable(self) -> None:
        # The coverage term is worth 10 points per criterion, so "could this
        # have been test-executed?" must not be self-assessed. This repository
        # pins prose with doc-assertion tests, so "it is only prose" must not
        # read as non-executable and quietly zero the deduction.
        qa = self.read("agents/qa-agent.md")
        self.assertIn("Test-executable is a decidable predicate", qa)
        self.assertIn("without new infrastructure", qa)
        self.assertIn("doc-assertion tests over shipped prose", qa)
        self.assertIn("is not by itself a reason to call it non-executable", qa)
        # A non-executable judgment is free, so it must be recorded and named.
        self.assertIn("naming the infrastructure that is missing", qa)
        self.assertIn("Not test-executable", qa)
        self.assertIn("Test-executable but not executed", qa)

    def test_coverage_term_does_not_double_count_failed_criteria(self) -> None:
        # A failed criterion already reduced the ratio. Deducting coverage on
        # top of it penalises the same fact twice and can push legitimate work
        # under the 80 threshold for arithmetic reasons rather than quality.
        qa = self.read("agents/qa-agent.md")
        self.assertIn("10 per PASSED test-executable acceptance criterion", qa)
        self.assertIn("The coverage term applies only to criteria that passed.", qa)
        self.assertIn(
            "Never apply a coverage deduction to a criterion you marked failed.", qa
        )

    def test_project_context_defers_role_routing_to_the_selection_guide(self) -> None:
        # PROJECT_CONTEXT.md outranks the agent selection guide in the adapter's
        # resolution order, so any route restated here silently overrides newer
        # policy. The section must defer, and record only the one constraint
        # that is a property of this project rather than a routing preference.
        policy = (ROOT / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("The agent selection guide governs role routing.", policy)
        self.assertIn("outranks the guide in the adapter's resolution order", policy)
        self.assertIn("the lead runs on the `claude` harness", policy)
        self.assertIn("provider-neutral", policy)
        # The exact stale line this replaced, which routed every role to the
        # backend lead and so overrode the guide's per-role choices.
        self.assertNotIn(
            "use the selected backend's lead route for every role", policy
        )


if __name__ == "__main__":
    unittest.main()
