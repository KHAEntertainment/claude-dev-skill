from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "dev"
ENTRY = SKILL / "SKILL.md"
VALIDATOR = ROOT / "scripts" / "validate_skill.py"


def frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must begin with YAML frontmatter")
    return text.split("\n---\n", 1)[0]


def when_to_use(block: str) -> str:
    for line in block.splitlines():
        if line.startswith("when_to_use:"):
            return line.partition(":")[2].strip().strip('"').strip("'")
    raise AssertionError("SKILL.md frontmatter has no when_to_use field")


class ModelInvocationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = ENTRY.read_text(encoding="utf-8")
        self.frontmatter = frontmatter(self.text)

    def test_model_invocation_is_explicitly_enabled(self) -> None:
        """`/dev` must stay reachable across the plan-to-implementation handoff."""
        self.assertIn("disable-model-invocation: false", self.frontmatter)
        self.assertNotIn("disable-model-invocation: true", self.text)

    def test_the_setting_is_explicit_rather_than_omitted(self) -> None:
        self.assertIn("disable-model-invocation:", self.frontmatter)

    def test_when_to_use_keeps_the_explicit_intent_trigger(self) -> None:
        guidance = when_to_use(self.frontmatter)
        self.assertIn("explicitly", guidance)
        self.assertIn("after plan approval", guidance)
        self.assertIn("before implementation begins", guidance)

    def test_when_to_use_excludes_generic_coding_activation(self) -> None:
        guidance = when_to_use(self.frontmatter)
        self.assertIn("Do not invoke", guidance)
        for generic in ("coding", "debugging", "refactoring", "review"):
            self.assertIn(generic, guidance)

    def test_description_carries_the_same_narrowing(self) -> None:
        """`description` is the field Claude Code surfaces for Skill selection.

        `when_to_use` documents intent for readers and for the validator, but it
        is not a documented Claude Code frontmatter key. If the constraint lived
        only there it could be inert at selection time.
        """
        description = ""
        for line in self.frontmatter.splitlines():
            if line.startswith("description:"):
                description = line.partition(":")[2].strip()
                break
        self.assertTrue(description, "SKILL.md frontmatter has no description")
        self.assertIn("explicitly", description)
        self.assertIn("after plan approval", description)
        self.assertIn("do not use it for ordinary coding", description)

    def test_body_documents_the_handoff_and_keeps_manual_invocation(self) -> None:
        for phrase in (
            "## Invocation",
            "model-invocable",
            "The user accepts the plan",
            "Manual invocation is unchanged",
            "not** an invocation trigger",
        ):
            self.assertIn(phrase, self.text)


class ValidatorEnforcementTests(unittest.TestCase):
    """The validator, not just the payload, must hold the contract."""

    def validate(self, mutate) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory, "dev")
            shutil.copytree(SKILL, copy)
            entry = copy / "SKILL.md"
            entry.write_text(mutate(entry.read_text(encoding="utf-8")), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), "--skill-dir", str(copy)],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_unmodified_payload_passes(self) -> None:
        completed = self.validate(lambda text: text)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_disabling_model_invocation_again_fails(self) -> None:
        completed = self.validate(
            lambda text: text.replace(
                "disable-model-invocation: false", "disable-model-invocation: true"
            )
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("disable-model-invocation: false", completed.stderr)

    def test_omitting_the_field_fails(self) -> None:
        completed = self.validate(
            lambda text: "\n".join(
                line
                for line in text.splitlines()
                if not line.startswith("disable-model-invocation:")
            )
            + "\n"
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("disable-model-invocation: false", completed.stderr)

    def test_dropping_when_to_use_fails(self) -> None:
        completed = self.validate(
            lambda text: "\n".join(
                line for line in text.splitlines() if not line.startswith("when_to_use:")
            )
            + "\n"
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("when_to_use", completed.stderr)

    def test_widening_when_to_use_to_generic_coding_fails(self) -> None:
        def widen(text: str) -> str:
            original = [
                line for line in text.splitlines() if line.startswith("when_to_use:")
            ][0]
            return text.replace(
                original,
                'when_to_use: "Invoke for any coding, debugging, or implementation request."',
            )

        completed = self.validate(widen)
        self.assertEqual(1, completed.returncode)
        self.assertIn("explicit-intent trigger", completed.stderr)


if __name__ == "__main__":
    unittest.main()
