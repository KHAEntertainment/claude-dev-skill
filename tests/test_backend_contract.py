from __future__ import annotations

import ast
import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "dev"

# The `required_policy` tuple as it stood at base 66ecfa3, frozen as data.
#
# The tokens are the mechanism that protects every policy sentence in the
# payload, but nothing protected the tokens themselves: deleting an entry from
# `required_policy` and then deleting the prose it pinned passed green gates at
# both steps. The scheme guarded the prose and not itself.
#
# Frozen here rather than read from git so this works in a tree without `.git`.
# Extracted with `ast` from `git show 66ecfa3:scripts/validate_skill.py`, not
# transcribed.
BASE_REQUIRED_POLICY = (
    "Never write or modify implementation or test code directly",
    ".agent/dev-state.md",
    "pre-created, verified branch/worktree",
    "RTK",
    "coderabbit",
    "kilo",
    "github-copilot",
    "copilot-pull-request-reviewer[bot]",
    "headRefOid",
    "Default wait minutes",
    "Allow automatic review requests",
    "--trusted-reviewer",
    "false_positive",
    "review evidence alone never establishes satisfaction",
    "incomplete",
    "TRAYCER_AGENT_ID",
    "TRAYCER_EPIC_ID",
    "claude-native",
    "rtk proxy traycer",
    "--surface gui",
    "--expect-reply",
    "--workspace-entry",
    "--carry-uncommitted",
    "traycer_last_used",
    "schema_version",
    "communication_response_id",
    "head changed",
    "distinct agent ID",
    "lead is the sole ledger writer",
    "A trusted reviewer's status check alone never satisfies this gate.",
)


# The seven required report-back sections, held once. Every document that has
# to name them is asserted against this tuple, so adding an eighth section is a
# one-line change here that then fails until each document carries it — rather
# than four independent lists that drift apart silently.
REPORT_BACK_SECTIONS = (
    "Outputs",
    "Commands + exit codes",
    "Deviations",
    "Quality-gate self-assessment",
    "Acceptance criteria",
    "Evidence",
    "Scope / ownership",
)


def _markdown_section(text: str, heading: str) -> str | None:
    """Return the body under `heading` up to the next same-level heading."""
    match = re.search(
        rf"^{re.escape(heading)}$(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    return match.group(1) if match else None


def _table_row(text: str, operation: str) -> str | None:
    """Return the operations-table row for `operation`, or None."""
    for line in text.splitlines():
        if line.startswith(f"| `{operation}` |"):
            return line
    return None


def _parse_required_policy(source: str) -> list[str]:
    """Return the `required_policy` tuple's literals, parsed with `ast`.

    Parsed rather than grepped on purpose. A regex over this tuple silently
    matches nothing when the formatting shifts and then reports a clean run,
    which is the same defect class the tokens exist to guard against: an
    instrument that fails looks identical to a check that passed.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "required_policy"
            for target in node.targets
        ):
            return [ast.literal_eval(element) for element in node.value.elts]
    raise AssertionError("required_policy assignment not found in validate_skill.py")


def _validator_module():
    """Load scripts/validate_skill.py so its pinned policy has one home.

    The routing section is pinned in the validator rather than duplicated here
    because `.gitattributes` export-ignores `tests`, so CI's archive validation
    runs the validator without this file. Importing it keeps a single source of
    truth and still fails here when the live document drifts from it.
    """
    path = ROOT / "scripts" / "validate_skill.py"
    spec = importlib.util.spec_from_file_location("validate_skill", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_qa_executes_the_whole_gate_not_only_the_test_suite(self) -> None:
        # Requiring only the test suite let a lane pass with the gate's lint
        # and type checks never executed and nothing recording that they had
        # not run - absence of execution reading as satisfaction, inside the
        # file written to prevent exactly that.
        qa = self.read("agents/qa-agent.md")
        self.assertIn("Execute the full Verification Gate.", qa)
        self.assertIn("Reading the gate is not running it.", qa)
        self.assertIn("record each command with the exit code it returned", qa)
        self.assertIn("Any gate command that fails, or does not run, fails QA.", qa)
        # A project with no recorded gate is a finding, not a silent skip.
        self.assertIn("records no Verification Gate", qa)
        # The report has somewhere to put the evidence.
        self.assertIn("### Verification Gate", qa)

    def test_coverage_term_denies_a_full_score_rather_than_failing_a_lane(self) -> None:
        # The prose claimed an unexecuted criterion should keep a lane from
        # reaching 80, but one deduction leaves a clean lane at 90 and passing.
        # Prose and arithmetic must agree on which was meant.
        qa = self.read("agents/qa-agent.md")
        self.assertIn(
            "The coverage term denies a full score; it does not by itself fail a lane.",
            qa,
        )
        self.assertIn("should not receive a full score", qa)
        self.assertNotIn("should not reach 80", qa)

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
        # Collapse wrapping first: these are prose sentences that wrap, so a
        # raw substring check would fail on a harmless reflow rather than on a
        # policy change.
        policy = " ".join(
            (ROOT / "PROJECT_CONTEXT.md").read_text(encoding="utf-8").split()
        )
        self.assertIn("The agent selection guide governs role routing.", policy)
        self.assertIn("outranks the guide in the adapter's resolution order", policy)
        self.assertIn(
            "the lead runs on the `claude` harness, "
            "because the lead is what invokes `/dev`",
            policy,
        )
        self.assertIn("provider-neutral", policy)
        # The exact stale line this replaced, which routed every role to the
        # backend lead and so overrode the guide's per-role choices.
        self.assertNotIn(
            "use the selected backend's lead route for every role", policy
        )

    def test_routing_section_contains_only_approved_content(self) -> None:
        # Structural, not lexical. A denylist of harness names can only reject
        # the names someone thought of - `traycer`, `cursor`, or a route with
        # no harness name at all walk straight through one. The section is
        # small and fixed, so its whole body is the guard: anything added
        # fails, whatever words it uses.
        validator = _validator_module()
        policy = (ROOT / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        section = validator.routing_section(policy)
        self.assertIsNotNone(section, "Execution Routing Policy section is missing")
        self.assertEqual(
            validator.normalize(section),
            validator.ROUTING_SECTION_BODY,
            "Execution Routing Policy must contain its approved content and "
            "nothing else",
        )
        # Reflowing the section must not be a policy change.
        self.assertEqual(
            validator.normalize("  a\n\n b \n c  "),
            "a b c",
            "normalize must collapse whitespace so a rewrap is not a failure",
        )
        # A leftover denylist beside the structural check invites a future
        # reader to maintain the list, which restarts the failure mode.
        self.assertFalse(
            hasattr(validator, "ROUTING_IDENTIFIERS"),
            "ROUTING_IDENTIFIERS is subsumed by the structural check and must "
            "not be reintroduced",
        )

    def test_report_back_defines_the_seven_sections(self) -> None:
        report_back = self.read("agents/report-back.md")
        for section in REPORT_BACK_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, report_back)

    def test_message_and_observe_rows_carry_the_report_back(self) -> None:
        # The operations table is what an adapter author reads first. If the
        # enforcement lives only in prose further down, an adapter can satisfy
        # the table and never implement it.
        contract = self.read("backends/contract.md")
        message = _table_row(contract, "message")
        observe = _table_row(contract, "observe")
        self.assertIsNotNone(message, "contract.md has no `message` operations row")
        self.assertIsNotNone(observe, "contract.md has no `observe` operations row")
        self.assertIn("report-back contract", message)
        self.assertIn("report-back shape verdict", observe)

    def test_contract_enforcement_section_names_every_section(self) -> None:
        contract = self.read("backends/contract.md")
        section = _markdown_section(contract, "## Report-back enforcement")
        self.assertIsNotNone(section, "contract.md missing Report-back enforcement")
        for name in REPORT_BACK_SECTIONS:
            with self.subTest(section=name):
                self.assertIn(name, section)
        # Both operations are specified in the one place that defines them.
        self.assertIn("`message`", section)
        self.assertIn("`observe`", section)
        self.assertIn(".agent/dev-state.md", section)
        self.assertIn("never infer completion", section)

    def test_silence_and_malformed_reply_share_one_verdict(self) -> None:
        # The round's central defect class in the agent transport: no reply read
        # as no problem. A lane that never replied must not be a lesser case
        # than one that replied badly - both leave the lane unverified. The
        # cause is recorded separately because the remedy differs, but a
        # separate cause must never become a separate verdict.
        contract = self.read("backends/contract.md")
        self.assertIn("Absence of a report is not a report.", contract)
        self.assertIn("the same verdict, not a lesser case", contract)
        self.assertIn("report_back: incomplete", contract)
        for cause in ("`absent`", "`malformed`", "`truncated`"):
            with self.subTest(cause=cause):
                self.assertIn(cause, contract)

    def test_heading_presence_has_a_non_empty_floor(self) -> None:
        # Presence-only recognition is deliberate - the lead judges content -
        # but without this floor seven empty headings pass the adapter check,
        # which is the silent-lane failure wearing the shape of a report.
        contract = self.read("backends/contract.md")
        self.assertIn("A heading with no content under it is a missing section", contract)
        self.assertIn("case-insensitive", contract.lower())

    def test_traycer_observe_checks_the_seven_sections(self) -> None:
        adapter = self.read("backends/traycer.md")
        for section in REPORT_BACK_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, adapter)
        self.assertIn("report_back: incomplete", adapter)
        # Shape is judged only after the paged read completes; otherwise
        # pagination manufactures a lane defect.
        self.assertIn("truncated", adapter)
        self.assertIn("is not a completion signal", adapter)

    def test_traycer_message_embeds_the_contract(self) -> None:
        adapter = self.read("backends/traycer.md")
        self.assertIn("must embed the report-back contract", adapter)
        self.assertIn("agents/report-back.md", adapter)

    def test_claude_native_implements_the_same_enforcement(self) -> None:
        # contract.md is backend-neutral, so parity is the requirement, not a
        # courtesy: an adapter that omits this is the one every silent lane
        # would be dispatched through.
        adapter = self.read("backends/claude-native.md")
        self.assertIn("seven required sections", adapter)
        self.assertIn("agents/report-back.md", adapter)
        self.assertIn("`incomplete`", adapter)
        self.assertIn(".agent/dev-state.md", adapter)

    def test_role_specific_close_outs_never_substitute(self) -> None:
        # The escape hatch with a real precedent: a QA lane posting its PR
        # comment and replying nothing looks like a lane that reported.
        #
        # Whitespace is collapsed first because `report-back.md` hard-wraps its
        # prose, so a rewrap must not read as a policy change here. Note the
        # validator pins this same sentence lexically, which is why it sits on
        # one line there: a reflow that splits it reddens the gate in
        # `validate_skill.py` rather than in this test.
        for relative in ("agents/report-back.md", "backends/contract.md"):
            with self.subTest(document=relative):
                self.assertIn(
                    "never substitute for the seven required sections",
                    " ".join(self.read(relative).split()),
                )
        self.assertIn("seven required sections", self.read("agents/qa-agent.md"))

    def test_no_baseline_policy_token_is_ever_removed(self) -> None:
        """Every token pinned at base 66ecfa3 must still be pinned.

        `required_policy` protects the payload's policy prose, but nothing
        protected `required_policy` itself: removing a token and then removing
        the prose it pinned passed the validator and these tests at both steps.
        Additions are allowed and expected; removals are not.

        Repository-CI guard only. `.gitattributes` export-ignores `tests`, so
        this does NOT ship in the extracted archive and gives no protection
        there - unlike the per-file policy map, which is enforced in the
        validator precisely because the archive carries it. Do not read this
        test as archive coverage.
        """
        current = _parse_required_policy(
            (ROOT / "scripts" / "validate_skill.py").read_text(encoding="utf-8")
        )
        missing = [token for token in BASE_REQUIRED_POLICY if token not in current]
        self.assertEqual(
            missing,
            [],
            "required_policy dropped baseline token(s), unpinning the policy "
            f"prose they protect: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
