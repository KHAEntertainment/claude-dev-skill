#!/usr/bin/env python3
"""Validate the distributable /dev Claude Code Skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED = {
    "SKILL.md",
    "backends/contract.md",
    "backends/claude-native.md",
    "backends/traycer.md",
    "phases/phase1.md",
    "phases/phase1-prototyping.md",
    "phases/phase2.md",
    "phases/phase3.md",
    "phases/phase3.5.md",
    "phases/external-review.md",
    "phases/phase4.md",
    "phases/phase5.md",
    "phases/repository-context.md",
    "agents/report-back.md",
    "agents/worker-new.md",
    "agents/worker-fix.md",
    "agents/qa-agent.md",
    "agents/reviewer.md",
    "agents/worker-prototype-frontend.md",
    "agents/worker-prototype-backend.md",
    "templates/PROJECT_CONTEXT_TEMPLATE.md",
    "templates/DEV_STATE_TEMPLATE.md",
    "scripts/detect_execution_backend.py",
    "scripts/inspect_external_reviews.py",
    "scripts/dev_config.py",
    "scripts/resolve_repository.py",
}


# The Execution Routing Policy section defers to the agent selection guide and
# exists to stay empty of routes. It is pinned structurally: the section must
# contain its approved content and nothing else, so any added line fails
# whatever words it uses.
#
# It is deliberately NOT a denylist of harness or model names. A denylist can
# only reject the names someone thought of — `traycer`, `cursor`, or a route
# phrased with no harness name at all ("all lanes use the lead route") walk
# straight through one. Enumeration over prose is unbounded, and this section
# is small and fixed, so the whole body is the guard.
#
# Whitespace is normalised before comparing, so reflowing or rewrapping the
# section is not a failure. Editing its wording IS a failure until this constant
# is updated in the same commit — that is the point: the section cannot change
# without the change being deliberate and reviewed.
ROUTING_HEADING = "## Execution Routing Policy"
ROUTING_SECTION_BODY = (
    "The agent selection guide governs role routing. This file records only "
    "project-specific exceptions, and there are none. Do not restate the "
    "guide's model or harness choices here, even to agree with them: a route "
    "recorded in this section outranks the guide in the adapter's resolution "
    "order, so anything written here silently overrides newer policy, and a "
    "copy made today becomes a stale override the moment the guide changes. "
    "That is why this section stays empty. One constraint does belong here, "
    "because it is a property of this project rather than a routing "
    "preference: **the lead runs on the `claude` harness, because the lead is "
    "what invokes `/dev`.** Worker, QA, and reviewer assignments are "
    "provider-neutral and may run on whichever harness and model the "
    "selection guide selects for them."
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def normalize(text: str) -> str:
    """Collapse whitespace, so reflowing prose is not a policy change."""
    return " ".join(text.split())


def routing_section(text: str) -> str | None:
    """Return the Execution Routing Policy section body, or None if absent."""
    match = re.search(
        rf"^{re.escape(ROUTING_HEADING)}$(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills" / "dev",
    )
    args = parser.parse_args()
    skill_dir = args.skill_dir.resolve()
    errors: list[str] = []

    for relative in sorted(REQUIRED):
        if not (skill_dir / relative).is_file():
            fail(errors, f"missing required file: {relative}")

    entry = skill_dir / "SKILL.md"
    if entry.is_file():
        text = entry.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            fail(errors, "SKILL.md must begin with YAML frontmatter")
        for field in (
            "name: dev",
            "version:",
            "description:",
            "argument-hint:",
            "when_to_use:",
        ):
            if field not in text:
                fail(errors, f"SKILL.md frontmatter missing: {field}")

        # The Skill must stay model-invocable so an explicit user request made
        # during planning survives into implementation. Require the explicit
        # `false` rather than an omitted field, so a regression is visible in
        # the diff instead of hiding in a default.
        frontmatter = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
        if "disable-model-invocation: false" not in frontmatter:
            fail(
                errors,
                "SKILL.md must set `disable-model-invocation: false` explicitly; "
                "model invocation is required for the plan-to-implementation handoff",
            )
        when_to_use = ""
        for line in frontmatter.splitlines():
            if line.startswith("when_to_use:"):
                when_to_use = line.partition(":")[2].strip().strip('"').strip("'")
                break
        for phrase in ("explicitly", "after plan approval", "Do not invoke"):
            if phrase not in when_to_use:
                fail(
                    errors,
                    f"SKILL.md `when_to_use` must keep the explicit-intent trigger: {phrase}",
                )

    combined_parts: list[str] = []
    for markdown in sorted(skill_dir.rglob("*.md")):
        content = markdown.read_text(encoding="utf-8")
        combined_parts.append(content)
        if re.search(r"[\u3400-\u9fff]", content):
            fail(errors, f"{markdown.relative_to(skill_dir)} contains Chinese text")
        for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([^`\s)'\"]+)", content):
            if not (skill_dir / ref).is_file():
                fail(errors, f"{markdown.relative_to(skill_dir)} references missing file: {ref}")

    combined = "\n".join(combined_parts)
    forbidden = {
        "~/.claude/commands/dev": "legacy command path",
        "TeamCreate": "obsolete Agent Teams setup tool",
        "TeamDelete": "obsolete Agent Teams cleanup tool",
        "/Users/bbrenner": "machine-specific absolute path",
    }
    for token, description in forbidden.items():
        if token in combined:
            fail(errors, f"found {description}: {token}")

    required_policy = (
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
        # Reuse-first ladder and its safety carve-out. The carve-out is pinned
        # as a full sentence: a ladder that survives without it reads as
        # licence to delete guards in the name of minimality.
        "Reuse-first ladder",
        "lowest rung",
        "Minimizing scope must never mean removing a guard.",
        "speculative abstraction",
        # Completion-evidence discipline. `qa-agent.md` holds the canonical
        # definition of "verified"; `report-back.md` cross-references it.
        "Tool Capability Boundary",
        "executed command's actual output",
        "re-run the full Verification Gate",
        # QA scoring: absence of signal must not read as a positive result.
        # Each token pins one path by which a lane that measured nothing could
        # otherwise return a passing number.
        "qa_error: no acceptance criteria",
        "qa_error: no verification executed",
        "No test framework detected",
        "not verified by test execution",
        "Limitations are load-bearing",
        # The coverage term swings 10 points per criterion, so the predicate
        # deciding it must stay decidable. Without these two the term degrades
        # into a self-assessed judgment and two lanes scoring the same PR can
        # legitimately reach different numbers.
        "Test-executable is a decidable predicate",
        "without new infrastructure",
        # A failed criterion already lowers the ratio; deducting coverage on
        # top of it counts the same fact twice and fails legitimate work for
        # arithmetic reasons. Found by the formula's first real use.
        "The coverage term applies only to criteria that passed.",
        # The prototype lanes' opposing principle. Pinned positively: a guard
        # that only asserts a ladder is absent cannot be told apart from a
        # vacuous one, and no token list can enumerate every paraphrase. With
        # this pinned, adding reuse-first guidance to a prototype prompt means
        # first deleting a sentence that says the opposite.
        "Exploration favors breadth over minimality.",
        # QA must execute the whole gate, not read it. Without this the lane
        # could run the test suite, never run lint or type checks, and pass
        # with nothing recording that they had not run.
        "Execute the full Verification Gate.",
        "Reading the gate is not running it.",
        # A convenience entry point that omits a recorded command reports
        # success over something that never ran - the same defect one layer up.
        "may be used only when it is known to run every recorded command",
        # Report-back enforcement at the adapter layer. The same defect class
        # one transport down: a lane that never replied is not a lane that had
        # nothing to say. Each token pins one way the enforcement could be
        # softened back into prompt-level etiquette.
        "Absence of a report is not a report.",
        "the same verdict, not a lesser case",
        "report_back: incomplete",
        # Without this, seven empty headings satisfy a presence check.
        "A heading with no content under it is a missing section",
        # The role-specific close-outs are the obvious escape hatch: a QA lane
        # posting its PR comment and replying nothing must not read as reported.
        "never substitute for the seven required sections",
        # The empty-heading rule closed one hole and opened a smaller one: what
        # counts as content was itself a judgment, so two leads could reach
        # different verdicts on the same reply. This is the mechanical floor.
        "at least one line containing a non-whitespace character",
        # "Read until the transport declares completion" is unbounded, so the
        # `truncated` cause was unreachable in the exact state it exists for.
        "Paging must be bounded",
        # Termination decides whether section inspection is permitted;
        # completed reads still need correlation and section evidence.
        "Termination decides whether section inspection is permitted",
        # The cause taxonomy was right and ran too late: an empty read reached
        # the shape branch as `malformed`, or stalled as `truncated`, when what
        # happened was that nothing arrived. Precedence is part of the
        # taxonomy - two adapters deriving it independently is how they drift.
        "An empty read is never evidence of a reply's shape.",
        # The other half of that sentence used to say "or of its transport",
        # which the termination field falsified: the condition that ended an
        # empty read is exactly transport evidence, and is why it is recorded.
        "What an empty read *is* evidence of is its own transport",
        # Three adapters instructed recording a verdict and cause into a ledger
        # with no field for either, so every lead would have invented a shape.
        # The cause is the half that selects the remedy; a verdict without one
        # records that something failed and discards what to do about it.
        "A `report_back: incomplete` with a null cause is an invalid record.",
        # And the clean lane records too, or "reported and verified" and "never
        # checked" are the same absence - this contract's own failure mode.
        "A lane is never `complete` by never having been looked at.",
        # The cause is lossy on purpose - three conditions collapse to
        # `truncated` - so the condition itself is kept for diagnosis. The
        # verdict and cause use the full mapping of observed inputs.
        "report_back_termination",
        "derive the verdict and cause from the full mapping",
        # The ledger recorded `report_back_termination: null` for an absent
        # lane on the reasoning that no read had run - while `contract.md` said
        # nothing can be known to be absent without looking. Two documents, one
        # head, contradicting each other on the one row the drift guard did not
        # cover. Absence is a result of reading, and a cut read establishes none.
        "Absence is established by reading, not instead of reading",
        "has not established absence",
    )
    for token in required_policy:
        if token not in combined:
            fail(errors, f"missing required custom policy: {token}")

    # `required_policy` is matched against every Skill markdown file
    # concatenated, so a token surviving in one file satisfies it for all.
    # That is too weak wherever the invariant is "each of these files carries
    # this in its own right": deleting the sentence from one lane still passes
    # while a sibling lane holds it up. The doc-assertion tests check per file,
    # but `.gitattributes` export-ignores `tests`, so CI's archive validation
    # runs this script without them and the validator is the only guard there.
    per_file_policy = {
        "agents/worker-new.md": (
            "Reuse-first ladder",
            "Minimizing scope must never mean removing a guard.",
        ),
        "agents/worker-fix.md": (
            "Reuse-first ladder",
            "Minimizing scope must never mean removing a guard.",
        ),
        "agents/worker-prototype-frontend.md": (
            "Exploration favors breadth over minimality.",
        ),
        "agents/worker-prototype-backend.md": (
            "Exploration favors breadth over minimality.",
        ),
        # Report-back enforcement is per-file by nature: `contract.md` is
        # backend-neutral, so both adapters must carry it in their own right.
        # A combined match would let one adapter hold it up for the other.
        "backends/contract.md": (
            "Absence of a report is not a report.",
            "report_back: incomplete",
            "never substitute for the seven required sections",
            "at least one line containing a non-whitespace character",
            "Paging must be bounded",
            "Termination decides whether section inspection is permitted",
            "An empty read is never evidence of a reply's shape.",
            "no correlated reply after `completed` is `absent`",
            "A verified report is recorded too, not only a failed one.",
            "Record the terminating condition, and derive the verdict and cause from the full mapping.",
            "still ran a bounded read",
        ),
        # The ledger is the other half of Issue #3's "recorded in
        # .agent/dev-state.md": a contract pointing at a field that does not
        # exist is not a recorded verdict.
        "templates/DEV_STATE_TEMPLATE.md": (
            "report_back_cause",
            "A `report_back: incomplete` with a null cause is an invalid record.",
            "A lane is never `complete` by never having been looked at.",
            "report_back_termination",
            "termination, reply correlation, and section presence",
            "Every bounded read records how it ended",
        ),
        # Each adapter must state its own bound; `contract.md` requires one to
        # exist but cannot supply a page size or a timeout for a transport it
        # does not know. An adapter naming no bound has not implemented observe.
        "backends/traycer.md": (
            "report_back: incomplete",
            "Quality-gate self-assessment",
            "Bound that read.",
            "Classify `absent` before anything else.",
        ),
        "backends/claude-native.md": (
            "seven required sections",
            "Bound the read",
            "Classify `absent` before anything else",
        ),
        "agents/report-back.md": ("never substitute for the seven required sections",),
        "agents/qa-agent.md": ("seven required sections",),
    }
    for relative, tokens in sorted(per_file_policy.items()):
        target = skill_dir / relative
        if target.is_file():
            target_text = target.read_text(encoding="utf-8")
            for token in tokens:
                if token not in target_text:
                    fail(errors, f"{relative} missing required policy: {token}")

    detector = skill_dir / "scripts" / "detect_execution_backend.py"
    if detector.is_file():
        detector_text = detector.read_text(encoding="utf-8")
        if "shutil.which" in detector_text or "command -v" in detector_text:
            fail(errors, "backend detector must not probe binary presence")

    # `required_policy` above is matched against the Skill's own markdown, so it
    # structurally cannot pin a sentence in the repo-root `PROJECT_CONTEXT.md`.
    # Routing policy lives there and outranks the agent selection guide in the
    # adapter's resolution order, so a silent revert re-overrides newer policy
    # with a stale route. Anchor on this script's own location rather than on
    # `--skill-dir`: every call site stages the Skill elsewhere but always runs
    # this validator from the project or archive root, where the file ships.
    # Absence fails closed — an unreadable policy is not a satisfied one.
    project_context = Path(__file__).resolve().parents[1] / "PROJECT_CONTEXT.md"
    if not project_context.is_file():
        fail(errors, "missing required file: PROJECT_CONTEXT.md")
    else:
        project_text = project_context.read_text(encoding="utf-8")
        section = routing_section(project_text)
        if section is None:
            fail(errors, f"PROJECT_CONTEXT.md missing section: {ROUTING_HEADING}")
        elif normalize(section) != ROUTING_SECTION_BODY:
            fail(
                errors,
                f"PROJECT_CONTEXT.md `{ROUTING_HEADING}` must contain its approved "
                "content and nothing else; this section exists to specify no "
                "routes, so any added or altered line fails regardless of wording. "
                "If the edit is intentional, update ROUTING_SECTION_BODY in "
                "scripts/validate_skill.py in the same commit.",
            )

    state_template = skill_dir / "templates" / "DEV_STATE_TEMPLATE.md"
    if state_template.is_file():
        state_text = state_template.read_text(encoding="utf-8")
        if not state_text.startswith("---\n") or "\n---\n" not in state_text[4:]:
            fail(errors, "DEV_STATE_TEMPLATE.md must contain YAML frontmatter")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: validated {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
