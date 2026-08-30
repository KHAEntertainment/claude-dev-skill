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
        self.assertIn("rtk git status --short", reviewer)
        self.assertIn("headRefOid", reviewer)
        self.assertIn("correlation/response ID", reviewer)
        self.assertIn("rev-parse", phase3_5)
        self.assertIn("unchanged checkout", phase3_5)
        self.assertIn("unchanged PR head", phase3_5)
        self.assertIn("immutable local `HEAD`", traycer)
        self.assertIn("invalidate QA, internal review, and external-review", phase4)
        self.assertIn("distinct from each other", contract)
        self.assertIn("backend_source", contract)


if __name__ == "__main__":
    unittest.main()
