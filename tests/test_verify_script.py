"""Exercise the real gate entrypoint with isolated tool stand-ins, never recurse."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify.sh"


class VerifyScriptTests(unittest.TestCase):
    def run_gate(self, *, shellcheck=None, executable=True, pwsh=False, windows=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copy2(SCRIPT, root / "scripts" / "verify.sh")
            binaries = root / "tools"
            binaries.mkdir()
            for name in ("bash", "python3", "claude", "dirname"):
                path = binaries / name
                if name == "dirname":
                    path.symlink_to(shutil.which("dirname"))
                else:
                    path.write_text("#!/bin/bash\nexit 0\n")
                    path.chmod(0o755)
            check = root / "scripts" / "check_plugin_root.sh"
            check.write_text("#!/bin/bash\nexit 0\n")
            check.chmod(0o755)
            if shellcheck is not None:
                tool = binaries / "shellcheck"
                tool.write_text(f"#!/bin/bash\nexit {shellcheck}\n")
                tool.chmod(0o755 if executable else 0o644)
            if pwsh:
                tool = binaries / "pwsh"
                tool.write_text("#!/bin/bash\nexit 0\n")
                tool.chmod(0o755)
            env = {**os.environ, "PATH": str(binaries), "OS": "Windows_NT" if windows else "Linux"}
            return subprocess.run(
                ["/bin/bash", str(root / "scripts" / "verify.sh")],
                cwd="/", env=env, text=True, capture_output=True, check=False,
            )

    def test_all_checks_pass(self):
        result = self.run_gate(shellcheck=0, pwsh=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("10 passed, 0 failed, 0 did-not-run, 0 optional skipped", result.stdout)
        self.assertIn("GATE PASSED", result.stdout)

    def test_missing_check_cannot_pass_when_all_executed_checks_pass(self):
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT RUN (did-not-run): ShellCheck (exit 127)", result.stdout)
        self.assertIn("8 passed, 0 failed, 1 did-not-run", result.stdout)
        self.assertNotIn("GATE PASSED", result.stdout)

    def test_nonexecutable_check_did_not_run(self):
        result = self.run_gate(shellcheck=0, executable=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT RUN (did-not-run): ShellCheck (exit 126)", result.stdout)
        self.assertIn("8 passed, 0 failed, 1 did-not-run", result.stdout)

    def test_real_failure_is_failed_and_later_checks_still_run(self):
        result = self.run_gate(shellcheck=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED: ShellCheck (exit 1)", result.stdout)
        self.assertNotIn("NOT RUN", result.stdout)
        self.assertIn("PASSED: Claude plugin validation (exit 0)", result.stdout)
        self.assertIn("8 passed, 1 failed, 0 did-not-run", result.stdout)

    def test_absent_optional_powershell_skip_is_visible(self):
        result = self.run_gate(shellcheck=0)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIPPED: PowerShell installer tests (pwsh absent; optional off Windows; exit n/a)", result.stdout)
        self.assertIn("1 optional skipped", result.stdout)

    def test_powershell_is_required_on_windows(self):
        result = self.run_gate(shellcheck=0, windows=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT RUN (did-not-run): PowerShell installer tests (exit 127)", result.stdout)
        self.assertNotIn("SKIPPED", result.stdout)
