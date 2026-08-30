from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETECTOR = ROOT / "skills" / "dev" / "scripts" / "detect_execution_backend.py"
SPEC = importlib.util.spec_from_file_location("detect_execution_backend", DETECTOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BackendDetectionTests(unittest.TestCase):
    def test_environment_matrix(self) -> None:
        cases = (
            ({}, "claude-native", "ready"),
            ({"TRAYCER_AGENT_ID": "agent-1"}, "incomplete", "incomplete"),
            ({"TRAYCER_EPIC_ID": "epic-1"}, "incomplete", "incomplete"),
            (
                {"TRAYCER_AGENT_ID": "agent-1", "TRAYCER_EPIC_ID": "epic-1"},
                "traycer",
                "ready",
            ),
        )
        for environment, backend, status in cases:
            with self.subTest(environment=environment):
                result = MODULE.detect_backend(environment)
                self.assertEqual(backend, result["execution_backend"])
                self.assertEqual(status, result["detection_status"])

    def test_whitespace_is_absent(self) -> None:
        result = MODULE.detect_backend(
            {"TRAYCER_AGENT_ID": "  ", "TRAYCER_EPIC_ID": "\t"}
        )
        self.assertEqual("claude-native", result["execution_backend"])

    def test_binary_presence_does_not_select_traycer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "traycer").write_text("present but irrelevant", encoding="utf-8")
            result = MODULE.detect_backend({"PATH": directory})
        self.assertEqual("claude-native", result["execution_backend"])

    def test_cli_emits_compact_json_and_fails_partial_context(self) -> None:
        environment = os.environ.copy()
        environment.pop("TRAYCER_AGENT_ID", None)
        environment["TRAYCER_EPIC_ID"] = "epic-1"
        completed = subprocess.run(
            [sys.executable, str(DETECTOR)],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("incomplete", payload["execution_backend"])
        self.assertNotIn("\n\n", completed.stdout)


if __name__ == "__main__":
    unittest.main()
