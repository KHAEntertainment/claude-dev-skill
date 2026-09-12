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


# The cause taxonomy, held once for the same reason as the section names: the
# contract defines these and the ledger has to store exactly them. Two lists
# would let the adapters record a cause the ledger cannot hold.
REPORT_BACK_CAUSES = ("absent", "malformed", "truncated")

# The four bounded-read terminating conditions, under the names the contract,
# both adapters, and the ledger all use. Held once for the same reason: the
# adapters record one of these and the ledger has to store exactly these, and
# the cause uses termination, reply correlation, and section presence.
REPORT_BACK_TERMINATIONS = ("completed", "stalled", "page_cap", "time_bound")

_COMPLETED, *_TRUNCATING = REPORT_BACK_TERMINATIONS
_ABSENT, _MALFORMED, _TRUNCATED = REPORT_BACK_CAUSES

# The derivation itself, as data: which terminating condition (with the section
# check, when the read completed) yields which verdict and cause.
#
# This is the guarantee the whole field rests on. `report_back_cause` is safe
# to keep beside `report_back_termination` only because it is read off a total
# mapping rather than authored independently - so the mapping's CONTENT is
# load-bearing, not just its presence. Asserting that the table contains the
# right words in some order leaves a wrong row silently authoritative, and a
# wrong row sends a lead to re-request the shape of a reply that was truncated:
# the wrong remedy, chosen confidently, off a ledger that looks right.
#
# Built from the tuples above rather than retyped, so a renamed condition or
# cause cannot leave this mapping describing the old vocabulary.
# Correlation is an explicit input, not an implicit one. The earlier version
# recorded `report_back_termination: null` for an absent lane on the reasoning
# that no bounded read had run - which is false. Absence is established BY
# reading: the read runs, terminates, and only then is correlation checked. The
# ledger discarded that condition and then asserted the read never happened,
# contradicting `contract.md`'s own "nothing can be known to be absent without
# looking" at the same head.
#
# `absent` additionally requires a `completed` read. A cut read that found no
# correlated reply has established nothing - the reply may lie past the cut -
# so it is `truncated` and re-read. Calling it `absent` would read a partial
# absence of signal as a positive finding, in the ledger built to prevent that.
REPORT_BACK_DERIVATION = (
    ("not yet read", ("null",), "not examined", "pending", "null"),
    ("not observed", tuple(_TRUNCATING), "not examined", "incomplete", _TRUNCATED),
    ("not observed", (_COMPLETED,), "not examined", "incomplete", _ABSENT),
    ("observed", tuple(_TRUNCATING), "not judged", "incomplete", _TRUNCATED),
    ("observed", (_COMPLETED,), "any missing", "incomplete", _MALFORMED),
    ("observed", (_COMPLETED,), "all seven", "complete", "null"),
)


def _mapping_rows(text: str) -> list[tuple[str, tuple[str, ...], str, str, str]]:
    """Parse the ledger's derivation table into comparable tuples.

    Returns (correlation, terminations, sections, verdict, cause) per row, with
    backticked tokens extracted so a reflow or added emphasis is not a policy
    change while a changed value is.
    """
    rows: list[tuple[str, tuple[str, ...], str, str, str]] = []
    for line in text.splitlines():
        if not line.strip().startswith("|") or line.strip().startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        terminations = tuple(re.findall(r"`([^`]+)`", cells[1]))
        verdict = re.findall(r"`([^`]+)`", cells[3])
        cause = re.findall(r"`([^`]+)`", cells[4])
        if not terminations or not verdict or not cause:
            continue
        # Skip the header row, which names the fields rather than values.
        if terminations[0] == "report_back_termination":
            continue
        rows.append((cells[0], terminations, cells[2], verdict[0], cause[0]))
    return rows


def _assigns(cause: str) -> str:
    """Regex matching a sentence that ASSIGNS `cause`, not one mentioning it.

    The distinction is the whole difference between a guard and a nuisance. A
    sentence that assigns a cause makes a claim about when it applies and must
    name what licenses it; one that refers to the cause — a remedy, a
    cross-reference, a pointer at the contract — makes no such claim, and
    failing on it is a guard crying wolf, which is how guards get disabled.

    Deliberately narrower than "mentions the cause": phrasings that assign
    without one of these constructions will escape. A narrow guard that is
    trusted beats a broad one that is switched off.
    """
    return rf"(?:is|as|in|cause|record(?:s|ed)?|classified|file[ds]?)\s+`{cause}`"


def _sentence_containing(text: str, needle: str) -> str | None:
    """Return the sentence containing `needle`, for cross-document checks."""
    for sentence in re.split(r"(?<=\.)\s+(?=[A-Z`*])", text):
        if needle in sentence:
            return sentence
    return None


def _markdown_section(text: str, heading: str) -> str | None:
    """Return the body under `heading` up to the next same-level heading."""
    match = re.search(
        rf"^{re.escape(heading)}$(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    return match.group(1) if match else None


def _bullet(text: str, starts_with: str) -> str | None:
    """Return the single list bullet beginning with `starts_with`.

    Assertions about one rule have to be scoped to the bullet stating it. A
    file-wide `assertIn` passes on any other occurrence of the same words, so a
    deleted condition can still be "found" in the bullet that consumes it —
    which is a test reporting a guard it is not actually holding.
    """
    match = re.search(
        rf"^- {re.escape(starts_with)}.*?(?=^- |\Z)", text, re.M | re.S
    )
    return match.group(0) if match else None


def _line_starting(text: str, prefix: str) -> str | None:
    """Return the single line beginning with `prefix`.

    Same reason as `_bullet`: an enumeration has to be asserted against the
    line that enumerates it, or a renamed value is still "found" in some other
    field's vocabulary elsewhere in the file.
    """
    return next((line for line in text.splitlines() if line.startswith(prefix)), None)


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

    def mapping_rows(self) -> list[tuple[str, tuple[str, ...], str, str, str]]:
        """Parse the mapping table from the section that governs it.

        Scoped rather than file-wide, for the reason four earlier assertions
        in this module were not: a table parsed from the whole document would
        happily bind to some other table added later, and the check would go on
        passing while the section it exists to guard drifted.
        """
        section = _markdown_section(
            self.read("templates/DEV_STATE_TEMPLATE.md"),
            "## Report-back record schema",
        )
        self.assertIsNotNone(section, "template has no report-back record schema")
        rows = _mapping_rows(section)
        self.assertTrue(rows, "the report-back schema carries no mapping table")
        return rows

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

    def test_ledger_can_hold_the_verdict_the_adapters_record(self) -> None:
        # All three adapters instructed recording `report_back` into
        # `.agent/dev-state.md`, which had no such field - so every lead would
        # have invented a shape and the record would be unusable as an audit
        # trail. Issue #3's criterion is "recorded in .agent/dev-state.md";
        # the ledger is the other half of it.
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        contract = self.read("backends/contract.md")
        self.assertIn("`report_back`", state)
        self.assertIn("`report_back_cause`", state)
        # The field is on the per-lane record, not floating in prose.
        workers = _markdown_section(state, "## Worker record schema")
        self.assertIsNotNone(workers, "template has no worker record schema")
        self.assertIn("`report_back`", workers)
        self.assertIn("`report_back_cause`", workers)
        self.assertIn("`report_back_termination`", workers)
        # The ledger stores exactly the causes the contract defines. Asserted
        # from one list so the two cannot drift into a cause the ledger cannot
        # hold, or a field the adapters never produce.
        # Scoped to the line that enumerates them. File-wide, `incomplete` and
        # `complete` already appear as a `backend_source` result and a worker
        # status, so a renamed cause here could still be "found" against an
        # unrelated field's vocabulary.
        allowed = _line_starting(state, "Allowed `report_back_cause` values:")
        self.assertIsNotNone(allowed, "template does not enumerate the causes")
        for cause in REPORT_BACK_CAUSES:
            with self.subTest(cause=cause):
                self.assertIn(f"`{cause}`", allowed)
                self.assertIn(f"`{cause}`", contract)

    def test_every_document_names_the_same_four_terminating_conditions(self) -> None:
        # External review, Medium: the ledger stored the cause but not the
        # condition it came from, and `truncated` collapses three conditions
        # into one value. The omission was deliberate and argued on remedy -
        # all three share one - and overturned on diagnosis, which the cause
        # cannot serve. One list, so contract, adapters and ledger cannot drift
        # into names that no longer match.
        # Scoped to the construct in each document that has to define the
        # names. File-wide, every name also appears in the prose explaining why
        # the cause is lossy, so a renamed condition in the definition would
        # still be "found" in the explanation of it.
        contract = self.read("backends/contract.md")
        traycer = self.read("backends/traycer.md")
        native = self.read("backends/claude-native.md")
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        scopes = {
            "contract.md paging bullet": _bullet(contract, "**Paging must be bounded"),
            "traycer.md bound bullet": _bullet(traycer, "**Bound that read."),
            "claude-native.md bound step": _line_starting(
                native, "   2. **Bound the read**"
            ),
            "template allowed values": _line_starting(
                state, "Allowed `report_back_termination` values:"
            ),
        }
        for name, scope in scopes.items():
            self.assertIsNotNone(scope, f"{name}: not found")
            for condition in REPORT_BACK_TERMINATIONS:
                with self.subTest(scope=name, condition=condition):
                    self.assertIn(f"`{condition}`", scope)
        # Each adapter must name the ledger field it writes, or the condition
        # is observed and then has nowhere to go - the defect one level up.
        for relative, adapter in (
            ("backends/traycer.md", traycer),
            ("backends/claude-native.md", native),
        ):
            with self.subTest(adapter=relative):
                self.assertIn("`report_back_termination`", adapter)

    def test_the_cause_is_derived_from_the_full_mapping(self) -> None:
        # Completed reads have multiple outcomes; termination alone cannot
        # select the row. Preserve the explicit inputs and total mapping.
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        contract = self.read("backends/contract.md")
        for document in (state, contract, self.read("backends/traycer.md"),
                         self.read("backends/claude-native.md")):
            self.assertIn("termination, reply correlation, and section presence", document)
        self.assertIn(
            "Record the terminating condition, and derive the verdict and cause from the full mapping.",
            contract,
        )
        self.assertIn("The mapping is total", state)
        self.assertIn("any pairing not in this table is an invalid record", state)

    def test_the_mapping_table_states_the_exact_pairings(self) -> None:
        # Content, not shape. The previous version of this check collected the
        # table's lines and asserted every value appeared somewhere in the
        # joined block - which stays true when a row's cause is changed, so a
        # table saying a stalled read is `malformed` passed the whole suite
        # while contradicting `contract.md`. The pairing is the guarantee; a
        # table asserted only for its vocabulary is not asserted at all.
        self.assertEqual(
            self.mapping_rows(),
            list(REPORT_BACK_DERIVATION),
            "the ledger's termination-to-cause mapping does not match the "
            "derivation it is supposed to encode",
        )

    def test_the_ledger_mapping_and_the_contract_prose_cannot_drift(self) -> None:
        # Two documents stating one rule is how they diverge, which is the
        # defect fixed at the contract level in b2632ba reappearing in the
        # artifact that resolves it. The contract's sentences are checked
        # against the cause parsed out of the ledger table, not against a
        # literal - so a wrong row fails here too, from the other side.
        rows = self.mapping_rows()
        truncating = next(
            (r for r in rows if r[0] == "observed" and r[1] == tuple(_TRUNCATING)), None
        )
        completed_missing = next(
            (r for r in rows if r[0] == "observed" and r[2] == "any missing"), None
        )
        uncorrelated = next(
            (r for r in rows if r[0] == "not observed" and r[1] == (_COMPLETED,)), None
        )
        self.assertIsNotNone(truncating, "no row for the truncating conditions")
        self.assertIsNotNone(completed_missing, "no row for a completed read")
        self.assertIsNotNone(uncorrelated, "no row for a completed read with no reply")

        bullet = _bullet(
            self.read("backends/contract.md"),
            "**Termination decides whether section inspection is permitted",
        )
        self.assertIsNotNone(bullet, "contract.md has no cause-decision bullet")
        stall_sentence = _sentence_containing(bullet, "ended by a stall")
        completed_sentence = _sentence_containing(bullet, "ended by the completion")
        self.assertIsNotNone(stall_sentence, "contract states no stall outcome")
        self.assertIsNotNone(completed_sentence, "contract states no completed outcome")

        # The cause the ledger assigns each case must be the cause the contract
        # names for it, and must not be the one it names for the other case.
        self.assertIn(f"`{truncating[4]}`", stall_sentence)
        self.assertNotIn(f"`{truncating[4]}`", completed_sentence)
        self.assertIn(f"`{completed_missing[4]}`", completed_sentence)
        self.assertNotIn(f"`{completed_missing[4]}`", stall_sentence)

        # The absent row, which the previous version of this check did not
        # cover - and which is exactly where the two documents drifted. The
        # contract must agree that absence needs a completed read and that a
        # cut read establishes nothing.
        absent_bullet = _bullet(
            self.read("backends/contract.md"), "**Record the terminating condition"
        )
        self.assertIsNotNone(absent_bullet, "contract.md has no derivation bullet")
        self.assertIn(f"`{uncorrelated[4]}`", absent_bullet)
        self.assertIn(f"is `{_COMPLETED}`", absent_bullet)
        self.assertIn("has not established absence", absent_bullet)
        # And the ledger must not claim the read never happened.
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        self.assertNotIn("no bounded read ran", state)
        self.assertIn("Absence is established by reading, not instead of reading", state)

    def test_no_prose_claims_absence_without_a_completed_read(self) -> None:
        """The drift guard's hole, found twice in one file.

        The cross-document check binds the rows where the two documents agree,
        and both times the drift went to prose no row covers — a bullet three
        sections above the mapping still saying an empty read "was already
        classified `absent` above and never reaches" the four conditions, which
        contradicts the table on two counts at once.

        So this binds the prose to the table instead of to a literal: any
        sentence in the enforcement section that names `absent` as a
        classification must also name the termination the mapping pairs it
        with. A reintroduced sentence claiming absence without a completed read
        has no way to satisfy that, whatever words it uses.
        """
        rows = self.mapping_rows()
        absent_row = next(
            (r for r in rows if r[0] == "not observed" and r[1] == (_COMPLETED,)), None
        )
        cut_row = next(
            (r for r in rows if r[0] == "not observed" and r[1] == tuple(_TRUNCATING)),
            None,
        )
        self.assertIsNotNone(absent_row, "no completed-read absent row")
        self.assertIsNotNone(cut_row, "no cut-read row for an uncorrelated reply")
        absent_cause, cut_cause = absent_row[4], cut_row[4]

        section = _markdown_section(
            self.read("backends/contract.md"), "## Report-back enforcement"
        )
        self.assertIsNotNone(section, "contract.md has no enforcement section")

        # The paging bullet is where the stale sentence lived and where the
        # split has to be stated, in the mapping's own terms.
        paging = _bullet(section, "**Paging must be bounded")
        self.assertIsNotNone(paging, "no bounded-paging bullet")
        self.assertIn(
            f"no correlated reply after `{_COMPLETED}` is `{absent_cause}`", paging
        )
        self.assertIn(f"is `{cut_cause}`", paging)
        for condition in _TRUNCATING:
            with self.subTest(condition=condition):
                self.assertIn(f"`{condition}`", paging)

        # And across the WHOLE enforcement section, no sentence that ASSIGNS
        # the cause may do so without naming the condition that licenses it.
        # Matched on the assignment construction — "cause `absent`", "is
        # `absent`", "classified `absent`" — rather than on any mention, so
        # prose that merely refers to the cause stays exempt: "`absent`
        # questions whether the lane is alive" is a remedy, and "`absent`
        # having already been ruled out" is a cross-reference. Neither assigns.
        #
        # Section-wide rather than bullet-scoped because the first pass of this
        # guard covered only the paging bullet and two other bullets carrying
        # the same stale assumption went through untouched.
        # Split per bullet before splitting sentences: a "sentence" spanning a
        # bullet boundary is a parsing artifact, and treating one as a claim
        # fails the guard on prose that is correct.
        classifying = [
            sentence
            for chunk in re.split(r"\n- ", section)
            for sentence in re.split(r"(?<=\.)\s+(?=[A-Z`*\"])", chunk)
            if re.search(_assigns(absent_cause), sentence)
        ]
        self.assertTrue(classifying, "no sentence assigns the absent cause")
        for sentence in classifying:
            with self.subTest(sentence=sentence[:70]):
                self.assertIn(
                    f"`{_COMPLETED}`",
                    sentence,
                    f"classifies a read as `{absent_cause}` without naming "
                    f"`{_COMPLETED}`, which is the only condition that licenses it",
                )

        # The two bullets the section sweep corrected, pinned directly: the
        # cause gloss must carry the qualification, and the cause-decision
        # bullet must say which replies it governs.
        self.assertIn(f"a `{_COMPLETED}` read carried no reply correlated", section)
        self.assertIn("For a reply that was observed", section)

    def test_adapters_license_every_cause_they_assign(self) -> None:
        """The same rule as the contract's, extended to both adapters.

        Third pass at one class. The contract's section was swept and guarded;
        the identical stale rationale was then found living in both adapters,
        where nothing bound it. Each sweep fixed the sites someone listed and
        the drift was wherever nobody looked — so this binds the adapters by
        the same rule rather than by another list of sites.

        Both directions:

        - a sentence assigning `absent` must name `completed`;
        - inside the classification bullet, a sentence naming `truncated` must
          name a cut condition.

        The second is scoped to that bullet on purpose. Elsewhere `truncated`
        appears in definitional prose that licenses it by negating completion
        rather than by naming a condition, and a blanket rule would fail on
        correct writing.
        """
        rows = self.mapping_rows()
        absent_cause = next(
            r[4] for r in rows if r[0] == "not observed" and r[1] == (_COMPLETED,)
        )
        cut_cause = next(
            r[4] for r in rows if r[0] == "not observed" and r[1] == tuple(_TRUNCATING)
        )
        assigns = _assigns(absent_cause)

        for relative, opener in (
            ("backends/traycer.md", "**Classify `absent` before anything else."),
            ("backends/claude-native.md", "**Classify `absent` before anything else."),
        ):
            adapter = self.read(relative)
            bullet = _bullet(adapter, opener) or _line_starting(
                adapter, f"   1. {opener}"
            )
            self.assertIsNotNone(bullet, f"{relative}: no absent-classification step")

            sentences = re.split(r"(?<=\.)\s+(?=[A-Z`*\"])", bullet)
            assigning = [s for s in sentences if re.search(assigns, s)]
            self.assertTrue(assigning, f"{relative}: nothing assigns `{absent_cause}`")
            for sentence in assigning:
                with self.subTest(adapter=relative, sentence=sentence[:70]):
                    self.assertIn(
                        f"`{_COMPLETED}`",
                        sentence,
                        f"{relative} assigns `{absent_cause}` without naming "
                        f"`{_COMPLETED}`",
                    )

            # Inverse direction. Every one of the three sites in this round
            # named `truncated` while describing an empty read and named no
            # condition that licenses it — which is what made each of them
            # read as a misclassification to avoid rather than the rule.
            for sentence in sentences:
                if not re.search(_assigns(cut_cause), sentence):
                    continue
                with self.subTest(adapter=relative, sentence=sentence[:70]):
                    self.assertTrue(
                        any(f"`{c}`" in sentence for c in _TRUNCATING),
                        f"{relative} names `{cut_cause}` in the classification "
                        "step without naming a condition that licenses it: "
                        f"{sentence[:120]}",
                    )

    def test_absent_is_not_a_terminating_condition(self) -> None:
        # `absent` is a cause, not a fifth terminating condition — but the read
        # that established it still ran and its condition is recorded. `null`
        # is reserved for a lane never read at all, which is `pending`.
        #
        # This comment previously said the opposite: that a lane with no
        # correlated reply never ran a bounded read. It survived the revision
        # that made it false, sitting directly above assertions checking for
        # "still ran a bounded read" — the test body was right the whole time
        # and the comment above it contradicted every line of it.
        contract = self.read("backends/contract.md")
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        self.assertIn("`absent` is not a fourth terminating condition", contract)
        # ...but the read that established it still ran, and its condition is
        # recorded. `null` is reserved for a lane never read at all.
        self.assertIn("still ran a bounded read", contract)
        self.assertIn("Every bounded read records how it ended", state)
        self.assertIn("no bounded read has been performed yet", state)
        for adapter in ("backends/traycer.md", "backends/claude-native.md"):
            with self.subTest(adapter=adapter):
                self.assertIn("the read ran, so it ended somehow", self.read(adapter))

    def test_an_incomplete_verdict_cannot_discard_its_cause(self) -> None:
        # The verdict says the lane is unverified; the cause is the only field
        # that selects the remedy. A verdict with a null cause is the same
        # defect one level down from the one this PR closes - recording that
        # something failed while throwing away what to do about it.
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        self.assertIn(
            "A `report_back: incomplete` with a null cause is an invalid record.",
            state,
        )

    def test_a_clean_lane_is_recorded_not_left_blank(self) -> None:
        # Without a positive record, "reported and verified" and "never looked
        # at" are the same absence in the ledger - which is precisely the
        # failure the report-back contract exists to detect, reappearing in the
        # audit trail of the mechanism that detects it.
        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        allowed = _line_starting(state, "Allowed `report_back` values:")
        self.assertIsNotNone(allowed, "template does not enumerate report_back values")
        for value in ("`pending`", "`complete`", "`incomplete`"):
            with self.subTest(value=value):
                self.assertIn(value, allowed)
        self.assertIn("A lane is never `complete` by never having been looked at.", state)
        self.assertIn(
            "A verified report is recorded too, not only a failed one.",
            self.read("backends/contract.md"),
        )

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

    def test_rate_limited_review_has_bounded_authorized_retries(self) -> None:
        external = self.read("phases/external-review.md")
        retry = external.split("### Rate-limited review retries\n", 1)[1].split(
            "### Deadline choices\n", 1
        )[0]
        schedule = {}
        for line in retry.splitlines():
            if line.startswith("| ") and "minutes |" in line:
                elapsed, action = [cell.strip() for cell in line.strip("|").split("|")]
                schedule[elapsed] = action
        self.assertEqual(schedule, {
            "15 minutes": "First retry",
            "30 minutes": "Second and final retry",
            "45 minutes": "End the response window and surface the explicit deadline choices once",
        })
        normalized = " ".join(retry.split())
        for requirement in (
            "only after an explicit rate-limit response",
            "authorizes re-requesting that specific reviewer",
            "One lead owns retries",
            "submitted reviews, review threads, and substantive PR comments",
            "a PR comment does not itself satisfy the inspector",
            "There is no third automatic retry",
            "Observe an actively progressing review without sending a duplicate request",
            "do not send catch-up requests",
            "If the vendor specifies a later retry time",
            "Polling or an acknowledgement never resets the budget",
            "carry the remaining budget and deadline forward",
            "Only an explicit extension renews an exhausted episode",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, normalized)

    def test_correction_review_keeps_current_evidence_and_full_review_triggers(self) -> None:
        phase4 = self.read("phases/phase4.md")
        correction = phase4.split("## Review after fixes\n", 1)[1].split(
            "## Merge Order\n", 1
        )[0]
        normalized = " ".join(correction.split())
        for requirement in (
            "Both QA and internal review must issue fresh results",
            "Read the full diff",
            "reconcile every known finding",
            "A push alone does not resolve or supersede a finding",
            "If there is no usable prior review/base, perform the full review",
            "focus internal QA and review on changed behavior",
            "Reopen the full review if scope, interfaces, architecture, a safety boundary, or material dependencies changed",
            "or if the affected scope is uncertain",
            "Run the full required Verification Gate at the final head",
            "distinct from implementation and each other",
            "reviewed base, target head, review scope, executed checks and remaining findings",
            "Internal delta review does not satisfy external review",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, normalized)

    def test_correction_review_entry_points_share_the_phase4_procedure(self) -> None:
        for relative in (
            "SKILL.md",
            "phases/phase3.5.md",
            "phases/external-review.md",
            "agents/qa-agent.md",
            "agents/reviewer.md",
            "agents/report-back.md",
            "backends/contract.md",
            "templates/DEV_STATE_TEMPLATE.md",
        ):
            with self.subTest(relative=relative):
                text = " ".join(self.read(relative).split())
                self.assertIn("Review after fixes", text)
                self.assertIn("${CLAUDE_SKILL_DIR}/phases/phase4.md", text)

    def test_fix_batches_do_not_promote_advisory_findings_to_blockers(self) -> None:
        phase4 = " ".join(self.read("phases/phase4.md").split())
        for requirement in (
            "First classify whether a finding blocks delivery",
            "An easy fix is not necessarily blocking",
            "Record advisory findings with a rationale and follow-up location",
            "consolidate findings already available from QA, internal review, and external review",
            "Dispatch confirmed blockers together",
            "Do not wait indefinitely",
            "or delay urgent security/data-loss containment",
            "avoid extra commits solely for advisory cleanup",
            "all blocking DELEGATE-FIX findings assigned to this PR are resolved",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, phase4)
        external = " ".join(self.read("phases/external-review.md").split())
        self.assertIn("a blocked merge does not block unrelated work", external)
        self.assertIn("record the next wake/action and yield", external)
        self.assertIn("A current-head `CHANGES_REQUESTED` remains blocking", external)
        self.assertIn("A timeout bypass cannot clear a known actionable finding", external)

    def test_bypass_is_scoped_to_unavailable_review_and_records_commit_range(self) -> None:
        """Issue #33: bypass must never excuse a self-invalidated review.

        A review the author's own fix commits moved past is not
        "unavailable" — that case obligates a re-request at the new head,
        not a bypass. Where a bypass is still used, the recorded debt must
        name the exact unreviewed commit range, not just the PR.
        """
        external = " ".join(self.read("phases/external-review.md").split())
        for requirement in (
            "A bypass is only for a review that never arrived or is unavailable",
            "never for a review that arrived and was invalidated by the author's own response",
            "obligates a re-request at the new head, not a bypass",
            "never one invalidated by the author's own response",
            "the exact unreviewed commit range",
            # Two forms are required: a review that completed before the fix
            # commits anchors the range at the reviewed head, but a review
            # that never completed at all has no reviewed head to anchor
            # it — that case must fall back to the PR's base head, or the
            # range degenerates to empty while every commit is unreviewed.
            "<reviewed-head>..<merged-head>",
            "<base-head>..<merged-head>",
            "no review ever completed on the PR",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, external)

        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        self.assertIn("the exact unreviewed commit range", state)
        self.assertIn("<reviewed-head>..<merged-head>", state)
        self.assertIn("<base-head>..<merged-head>", state)
        self.assertIn("no review ever completed on the PR", state)
        self.assertIn("the PR number alone is not sufficient", state)

        phase5 = self.read("phases/phase5.md")
        self.assertIn("### External-Review Bypasses", phase5)
        self.assertIn(
            "reported explicitly, including `0`",
            phase5,
        )
        self.assertIn(
            "visible as a pattern across rounds, not only per PR",
            phase5,
        )

    def test_post_merge_verification_is_unconditional_and_pins_the_ac_language(
        self,
    ) -> None:
        """Issue #26: nothing re-examined merged code against the closed
        Issue's acceptance criteria, and auto-closure by a merge keyword was
        read as completion evidence. The unconditional step must exist, must
        not be a merge gate, and must state the hazard explicitly rather than
        leaving it implied.
        """
        phase4 = " ".join(self.read("phases/phase4.md").split())
        for requirement in (
            "Post-Merge Verification (unconditional)",
            "This is not a merge gate",
            "the merge commit's tree hash",
            "the verified PR head's tree hash",
            "run the full recorded Verification Gate",
            "Auto-closure by a merge keyword is never evidence of completion",
            "merge_sha",
            "gate_result",
            "criteria_verdict",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, phase4)

        # Cross-references the bypass debt rule rather than restating its
        # commit-range syntax — duplicating it here is exactly the drift the
        # single-source-of-truth tokens above exist to prevent.
        self.assertIn("external-review.md", phase4)
        self.assertNotIn("<reviewed-head>..<merged-head>", phase4)
        self.assertNotIn("<base-head>..<merged-head>", phase4)

        phase5 = self.read("phases/phase5.md")
        self.assertIn("### Post-Merge Verification", phase5)
        self.assertIn("post-merge verification records", phase5)
        # The retro reads the records phase4.md's step produces; it must not
        # restate the check itself.
        self.assertIn(
            "do not repeat the check itself",
            phase5,
        )

        skill_section = _markdown_section(self.read("SKILL.md"), "## Global Rules")
        self.assertIsNotNone(skill_section, "SKILL.md has no Global Rules section")
        self.assertIn(
            "the lead reconciles the merged tree and re-confirms the closed "
            "Issue's acceptance criteria",
            skill_section,
        )
        self.assertIn("${CLAUDE_SKILL_DIR}/phases/phase4.md", skill_section)

        state = self.read("templates/DEV_STATE_TEMPLATE.md")
        for requirement in (
            "Post-merge verification record schema",
            "merge_sha",
            "gate_result",
            "criteria_verdict",
            "applies_verbatim",
            "Auto-closure by a merge keyword is never evidence of completion",
            "unmet_criteria",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, state)

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
        for cause in REPORT_BACK_CAUSES:
            with self.subTest(cause=cause):
                self.assertIn(f"`{cause}`", contract)

    def test_heading_presence_has_a_non_empty_floor(self) -> None:
        # Presence-only recognition is deliberate - the lead judges content -
        # but without this floor seven empty headings pass the adapter check,
        # which is the silent-lane failure wearing the shape of a report.
        contract = self.read("backends/contract.md")
        self.assertIn("A heading with no content under it is a missing section", contract)
        self.assertIn("case-insensitive", contract.lower())

    def test_the_presence_floor_is_itself_mechanical(self) -> None:
        # "Has content under it" is a judgment unless what counts as content is
        # stated, so the rule closing the empty-headings hole reopened it one
        # level up: a heading followed by a blank line, by the next heading, or
        # by an empty code fence were all arguable. The floor must be decidable
        # by two leads independently, which means naming its edge case rather
        # than leaving it to be reasoned out per reply.
        contract = self.read("backends/contract.md")
        self.assertIn(
            "at least one line containing a non-whitespace character", contract
        )
        self.assertIn("before the next heading of any level", contract)
        self.assertIn("empty code fence", contract)

    def test_paging_is_bounded_so_truncated_is_reachable(self) -> None:
        # `truncated` is defined for the state where the transport never
        # declares completion - which is exactly the state an unbounded "read
        # until it declares completion" loops in forever, never recording the
        # cause that exists for it. The guard has to terminate to be a guard.
        contract = self.read("backends/contract.md")
        self.assertIn("Paging must be bounded", contract)
        self.assertIn("An adapter that names no bound has not implemented", contract)
        # The four terminating conditions, asserted inside the bullet that has
        # to state them. File-wide they would also match the cause bullet
        # downstream, so deleting one here would still "pass" against the other
        # bullet's mention of it.
        bullet = _bullet(contract, "**Paging must be bounded")
        self.assertIsNotNone(bullet, "contract.md has no bounded-paging bullet")
        for condition in (
            "declares the reply complete",
            "does not advance",
            "page cap is reached",
            "time bound elapses",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, bullet)

    def test_each_adapter_states_a_concrete_bound(self) -> None:
        # `contract.md` requires a bound but cannot supply one: a page size and
        # a timeout are properties of a transport it does not know. Asserted
        # structurally so tuning the numbers stays a free change while deleting
        # the bound does not.
        for relative in ("backends/traycer.md", "backends/claude-native.md"):
            adapter = self.read(relative)
            with self.subTest(adapter=relative):
                self.assertRegex(adapter, r"\*\*\d+\s+(?:pages|re-reads)\*\*")
                self.assertRegex(adapter, r"\*\*\d+\s+seconds\*\*")

    def test_absent_is_classified_before_shape_and_paging(self) -> None:
        # The cause taxonomy was correct and ran too late. With shape or paging
        # classified first, a lane that never replied records `malformed`
        # (seven sections missing from nothing) or `truncated` (a cut in a
        # reply that never existed) - each sending the lead to a remedy for a
        # different failure than the one that happened. Found by external
        # review at a real head, in `claude-native.md`, and present in
        # `traycer.md` too: an empty inbox stalls like any non-advancing
        # cursor.
        contract = self.read("backends/contract.md")
        # Half of this sentence used to read "or of its transport", which the
        # termination field falsified: the condition ending an empty read is
        # precisely transport evidence, and is the reason it is now recorded.
        self.assertIn("An empty read is never evidence of a reply's shape.", contract)
        self.assertIn(
            "What an empty read *is* evidence of is its own transport", contract
        )
        self.assertIn("`absent` is classified first", contract)
        # Precedence is stated centrally rather than left to each adapter,
        # because two adapters deriving the same ordering from prose is how
        # they drift - which is exactly how this defect reached review.
        self.assertIn("part of the taxonomy rather than each adapter's discretion", contract)

    def test_the_absent_branch_precedes_the_others_in_every_document(self) -> None:
        # Ordering is the whole finding, and no substring assertion can catch a
        # reordering: every token survives being moved. Positional assertions
        # are the only ones that bind here.
        for relative, absent, shape, paging in (
            (
                "backends/contract.md",
                "`absent` is classified first",
                "Judge shape only after",
                "Paging must be bounded",
            ),
            (
                "backends/traycer.md",
                "Classify `absent` before anything else.",
                "verify it carries all seven required sections",
                "Bound that read.",
            ),
            (
                "backends/claude-native.md",
                "Classify `absent` before anything else",
                "Then verify the reply",
                "Bound the read",
            ),
        ):
            document = self.read(relative)
            with self.subTest(document=relative):
                for token in (absent, shape, paging):
                    self.assertIn(token, document)
                self.assertLess(
                    document.index(absent),
                    document.index(shape),
                    f"{relative}: `absent` must be classified before the shape branch",
                )
                self.assertLess(
                    document.index(absent),
                    document.index(paging),
                    f"{relative}: `absent` must be classified before the paging branch",
                )

    def test_termination_controls_whether_shape_can_be_judged(self) -> None:
        # A cut read cannot pass from its visible headings. Completed reads
        # still require the correlation and section checks in the full mapping.
        contract = self.read("backends/contract.md")
        self.assertIn("Termination decides whether section inspection is permitted", contract)
        self.assertIn("whatever sections it happens to contain", contract)
        # Both adapters have to record the condition, or the lead has nothing
        # to read it from.
        self.assertIn("Record which of the four ended it", self.read("backends/traycer.md"))
        self.assertIn(
            "Record which condition ended it", self.read("backends/claude-native.md")
        )

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

    def test_reply_contract_has_the_six_required_sections(self) -> None:
        """Issue #54: the lead-to-user reply contract's own required shape."""
        contract = self.read("reply-contract.md")
        for heading in (
            "## 1. Scope",
            "## 2. Cap",
            "## 3. Exceptions — never compressed away",
            "## 4. Carve-out — the cap counts prose, not required structured artifacts",
            "## 5. Pull principle",
            "## 6. Composition note",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, contract)

    def test_reply_contract_pins_the_three_approved_sentences(self) -> None:
        # Verbatim per the approved plan (Issue #54) so a paraphrase cannot
        # drift the cap, its scope, or the composition note unnoticed.
        contract = self.read("reply-contract.md")
        for sentence in (
            "aim under 100 words",
            "The cap counts prose, not required structured artifacts.",
            "never claims a task-requirements override",
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, contract)

    def test_reply_contract_names_every_artifact_exemption(self) -> None:
        # Scoped to the Carve-out section, not file-wide: an exemption named
        # anywhere else in the file is not the same guarantee as it being
        # part of the list the cap actually defers to.
        contract = self.read("reply-contract.md")
        carveout = _markdown_section(
            contract,
            "## 4. Carve-out — the cap counts prose, not required structured artifacts",
        )
        self.assertIsNotNone(carveout, "reply-contract.md has no Carve-out section")
        for exemption in (
            "Phase 1's progress breadcrumb and its one-question block",
            "Phase 3's Backend-Neutral Task Board",
            "Phase 4's review rating",
            "Phase 5's retro and technical-debt-sweep templates",
        ):
            with self.subTest(exemption=exemption):
                self.assertIn(exemption, carveout)

    def test_reply_contract_scope_excludes_report_back_and_docs(self) -> None:
        contract = self.read("reply-contract.md")
        scope = _markdown_section(contract, "## 1. Scope")
        self.assertIsNotNone(scope, "reply-contract.md has no Scope section")
        self.assertIn("agents/report-back.md", scope)
        self.assertIn("Issue or PR bodies", scope)

    def test_skill_hooks_reference_the_reply_contract_in_both_locations(self) -> None:
        # Issue #54 requires one hook bullet in each of two named sections;
        # scoped per section so a reference living in only one still fails.
        skill = self.read("SKILL.md")
        anchor = _markdown_section(
            skill, "## ⚓ Session State Anchor (execute on every user message)"
        )
        global_rules = _markdown_section(skill, "## Global Rules")
        self.assertIsNotNone(anchor, "SKILL.md has no Session State Anchor section")
        self.assertIsNotNone(global_rules, "SKILL.md has no Global Rules section")
        self.assertIn("${CLAUDE_SKILL_DIR}/reply-contract.md", anchor)
        self.assertIn("${CLAUDE_SKILL_DIR}/reply-contract.md", global_rules)

    def test_phase1_prototyping_cross_references_the_pull_principle(self) -> None:
        prototyping = self.read("phases/phase1-prototyping.md")
        bullet = _bullet(
            prototyping, "Do not relay the prototype agent's full readout"
        )
        self.assertIsNotNone(bullet, "phase1-prototyping.md has no don't-relay bullet")
        self.assertIn("pull principle", bullet)
        self.assertIn("${CLAUDE_SKILL_DIR}/reply-contract.md", bullet)

    def test_agents_directory_never_references_the_reply_contract(self) -> None:
        """Issue #54: worker/QA/reviewer surfaces are untouched — pinned invariant.

        Negative and unbounded by nature: no token list can enumerate every
        way a reference could sneak in, so this walks every file actually
        shipped under `agents/` rather than a named subset.
        """
        agents_dir = SKILL / "agents"
        offenders = [
            str(path.relative_to(SKILL))
            for path in sorted(agents_dir.glob("*.md"))
            if "reply-contract.md" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            offenders,
            [],
            "reply-contract.md must govern only the lead's own replies to the "
            f"user, never a delegated lane's prompt; found references in: {offenders}",
        )

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
