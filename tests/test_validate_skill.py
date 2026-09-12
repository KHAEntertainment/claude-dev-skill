"""The forbidden-path guard must see the whole shipped repository.

`validate_skill.py` widens its home-path scan beyond the Skill payload
(`skills/dev/`) to `en/`, `zh/`, and root-level markdown, anchored on the
validator's own `__file__` location -- the same anchor the existing
`PROJECT_CONTEXT.md` check uses, and for the same reason: every call site
stages `--skill-dir` elsewhere but always runs this validator from the
project or archive root.

Exercising that anchor means running a *copy* of the validator from a
fabricated project root. Copying only `skills/dev` the way
`test_skill_frontmatter.py` does for its narrower, `--skill-dir`-relative
checks would still resolve `Path(__file__).resolve().parents[1]` to this real
repository, silently scanning the real `en/`/`zh/` trees instead of the
fixture.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "dev"
PROJECT_CONTEXT = ROOT / "PROJECT_CONTEXT.md"
VALIDATOR = ROOT / "scripts" / "validate_skill.py"


class HomePathScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

        shutil.copytree(SKILL, self.root / "skills" / "dev")
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(VALIDATOR, self.root / "scripts" / "validate_skill.py")
        shutil.copy(PROJECT_CONTEXT, self.root / "PROJECT_CONTEXT.md")

        self.validator = self.root / "scripts" / "validate_skill.py"
        self.skill_dir = self.root / "skills" / "dev"

    def run_validator(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.validator), "--skill-dir", str(self.skill_dir)],
            check=False,
            capture_output=True,
            text=True,
        )

    def plant(self, relative: str, content: str) -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def test_clean_fixture_passes(self) -> None:
        """Establish the fixture itself is valid before any test mutates it."""
        completed = self.run_validator()
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_planted_home_path_in_en_fails_and_names_the_file(self) -> None:
        self.plant(
            "en/commands/dev.md",
            "Rollback snapshot: `/Users/alice/Documents/backups`.\n",
        )
        completed = self.run_validator()
        self.assertEqual(1, completed.returncode)
        self.assertIn("en/commands/dev.md", completed.stderr)
        self.assertIn("machine-specific absolute path", completed.stderr)

    def test_removing_the_planted_path_passes(self) -> None:
        planted = self.plant(
            "en/commands/dev.md",
            "Rollback snapshot: `/Users/alice/Documents/backups`.\n",
        )
        failing = self.run_validator()
        self.assertEqual(1, failing.returncode)

        planted.write_text("A rollback snapshot is kept locally.\n", encoding="utf-8")
        passing = self.run_validator()
        self.assertEqual(0, passing.returncode, passing.stderr)

    def test_archive_tree_without_en_or_zh_passes(self) -> None:
        """`en/` and `zh/` are `.gitattributes export-ignore`d; CI's packaging
        job extracts a `git archive` tree that never has them."""
        self.assertFalse((self.root / "en").exists())
        self.assertFalse((self.root / "zh").exists())
        completed = self.run_validator()
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_planted_home_path_in_zh_fails_and_names_the_file(self) -> None:
        self.plant("zh/commands/dev.md", "备份路径：`/home/carol/backups/`\n")
        completed = self.run_validator()
        self.assertEqual(1, completed.returncode)
        self.assertIn("zh/commands/dev.md", completed.stderr)

    def test_planted_home_path_in_root_markdown_fails_and_names_the_file(self) -> None:
        self.plant("NOTES.md", "See `C:\\Users\\dave\\workspace` for details.\n")
        completed = self.run_validator()
        self.assertEqual(1, completed.returncode)
        self.assertIn("NOTES.md", completed.stderr)

    def test_template_placeholders_do_not_false_positive(self) -> None:
        self.plant(
            "en/commands/dev.md",
            "Use `/Users/<name>/project`, `C:\\path\\to\\skills\\dev`, or `$HOME/project`.\n",
        )
        completed = self.run_validator()
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_home_path_inside_skill_payload_still_fails(self) -> None:
        """The pre-existing in-payload guard keeps working under the new regex."""
        target = self.skill_dir / "phases" / "phase1.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\nSee `/home/eve/notes` for background.\n",
            encoding="utf-8",
        )
        completed = self.run_validator()
        self.assertEqual(1, completed.returncode)
        self.assertIn("phase1.md", completed.stderr)


if __name__ == "__main__":
    unittest.main()
