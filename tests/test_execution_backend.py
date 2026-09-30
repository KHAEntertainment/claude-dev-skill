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
            ({}, "incomplete", "incomplete"),
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
        self.assertEqual("incomplete", result["execution_backend"])

    def test_binary_presence_does_not_select_traycer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "traycer").write_text("present but irrelevant", encoding="utf-8")
            result = MODULE.detect_backend({"PATH": directory})
        self.assertEqual("incomplete", result["execution_backend"])

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

    def test_cli_exits_zero_on_traycer_ready(self) -> None:
        environment = os.environ.copy()
        environment["TRAYCER_AGENT_ID"] = "agent-1"
        environment["TRAYCER_EPIC_ID"] = "epic-1"
        completed = subprocess.run(
            [sys.executable, str(DETECTOR)],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("traycer", payload["execution_backend"])
        self.assertEqual("ready", payload["detection_status"])
        self.assertEqual("detected", payload["backend_source"])


VALID_FILE = "export TRAYCER_AGENT_ID=agent-1\nexport TRAYCER_EPIC_ID=epic-1\n"


class SuppliedIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / ".git").mkdir()
        (self.root / ".agent").mkdir()
        self.identity = self.root / ".agent" / "traycer.env"

    def write(self, content: str) -> None:
        self.identity.write_text(content, encoding="utf-8")

    def test_env_present_reports_detected_and_ignores_file(self) -> None:
        self.write("garbage")
        result = MODULE.detect_backend(
            {"TRAYCER_AGENT_ID": "a", "TRAYCER_EPIC_ID": "e"}, self.identity
        )
        self.assertEqual("traycer", result["execution_backend"])
        self.assertEqual("detected", result["backend_source"])

    def test_neither_in_env_valid_file_is_supplied(self) -> None:
        self.write(VALID_FILE)
        result = MODULE.detect_backend({}, self.identity)
        self.assertEqual("traycer", result["execution_backend"])
        self.assertEqual("ready", result["detection_status"])
        self.assertEqual("supplied", result["backend_source"])
        self.assertEqual("agent-1", result["traycer_agent_id"])
        self.assertEqual("epic-1", result["traycer_epic_id"])

    def test_either_line_order_and_missing_trailing_newline(self) -> None:
        for content in (
            "export TRAYCER_EPIC_ID=epic-1\nexport TRAYCER_AGENT_ID=agent-1\n",
            "export TRAYCER_AGENT_ID=agent-1\nexport TRAYCER_EPIC_ID=epic-1",
        ):
            with self.subTest(content=content):
                self.write(content)
                result = MODULE.detect_backend({}, self.identity)
                self.assertEqual("supplied", result["backend_source"])
                self.assertEqual("agent-1", result["traycer_agent_id"])
                self.assertEqual("epic-1", result["traycer_epic_id"])

    def test_no_file_is_incomplete_with_null_source(self) -> None:
        result = MODULE.detect_backend({}, self.identity)
        self.assertEqual("incomplete", result["execution_backend"])
        self.assertIsNone(result["backend_source"])
        self.assertEqual(
            "no Traycer session identifiers are present; backend cannot be determined",
            result["reason"],
        )

    def test_exactly_one_env_identifier_never_uses_file(self) -> None:
        self.write(VALID_FILE)
        for environment in ({"TRAYCER_AGENT_ID": "a"}, {"TRAYCER_EPIC_ID": "e"}):
            with self.subTest(environment=environment):
                result = MODULE.detect_backend(environment, self.identity)
                self.assertEqual("incomplete", result["execution_backend"])
                self.assertIsNone(result["backend_source"])
                self.assertIn("partial Traycer session context", result["reason"])
                self.assertNotIn("agent-1", json.dumps(result))
                self.assertNotIn("epic-1", json.dumps(result))

    def test_malformed_files_are_incomplete_and_name_the_defect(self) -> None:
        cases = {
            "extra line": (VALID_FILE + "export TRAYCER_AGENT_ID=agent-2\n", "extra line"),
            "blank line": ("export TRAYCER_AGENT_ID=a\n\nexport TRAYCER_EPIC_ID=e\n", "not an `export KEY=value`"),
            "missing key": ("export TRAYCER_AGENT_ID=a\n", "missing key TRAYCER_EPIC_ID"),
            "empty file": ("", "missing key TRAYCER_AGENT_ID"),
            "empty value": ("export TRAYCER_AGENT_ID=\nexport TRAYCER_EPIC_ID=e\n", "empty value for TRAYCER_AGENT_ID"),
            "duplicate key": ("export TRAYCER_AGENT_ID=a\nexport TRAYCER_AGENT_ID=b\n", "duplicate key TRAYCER_AGENT_ID"),
            "wrong key": ("export TRAYCER_AGENT_ID=a\nexport TRAYCER_EPOC_ID=e\n", "wrong key name TRAYCER_EPOC_ID"),
            "no export": ("TRAYCER_AGENT_ID=a\nTRAYCER_EPIC_ID=e\n", "not an `export KEY=value`"),
            "quoted value": ('export TRAYCER_AGENT_ID="a"\nexport TRAYCER_EPIC_ID=e\n', "characters outside"),
            "shell metacharacter": ("export TRAYCER_AGENT_ID=a;id\nexport TRAYCER_EPIC_ID=e\n", "characters outside"),
            "crlf": ("export TRAYCER_AGENT_ID=a\r\nexport TRAYCER_EPIC_ID=e\r\n", "characters outside"),
        }
        for name, (content, defect) in cases.items():
            with self.subTest(name=name):
                self.write(content)
                result = MODULE.detect_backend({}, self.identity)
                self.assertEqual("incomplete", result["execution_backend"])
                self.assertEqual("incomplete", result["detection_status"])
                self.assertIsNone(result["backend_source"])
                self.assertIsNone(result["traycer_agent_id"])
                self.assertIsNone(result["traycer_epic_id"])
                self.assertIn(".agent/traycer.env", result["reason"])
                self.assertIn(defect, result["reason"])
                self.assertNotIn("\n", result["reason"])

    def test_not_utf8_and_unreadable_are_incomplete(self) -> None:
        self.identity.write_bytes(b"\xff\xfe")
        result = MODULE.detect_backend({}, self.identity)
        self.assertEqual("incomplete", result["execution_backend"])
        self.assertIn("unreadable", result["reason"])
        self.identity.unlink()
        self.identity.mkdir()
        result = MODULE.detect_backend({}, self.identity)
        self.assertEqual("incomplete", result["execution_backend"])
        self.assertIn("unreadable", result["reason"])

    def test_oversized_file_is_incomplete(self) -> None:
        self.write(VALID_FILE + "#" * 5000)
        result = MODULE.detect_backend({}, self.identity)
        self.assertEqual("incomplete", result["execution_backend"])
        self.assertIn("larger than", result["reason"])

    def test_no_identity_file_argument_never_reads_a_file(self) -> None:
        self.write(VALID_FILE)
        result = MODULE.detect_backend({})
        self.assertEqual("incomplete", result["execution_backend"])

    def test_lookup_walks_up_to_the_git_root(self) -> None:
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(self.identity, MODULE.find_identity_file(nested))

    def test_lookup_accepts_a_git_file_from_a_linked_worktree(self) -> None:
        (self.root / ".git").rmdir()
        (self.root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        nested = self.root / "sub"
        nested.mkdir()
        self.assertEqual(self.identity, MODULE.find_identity_file(nested))

    def test_lookup_without_git_uses_the_start_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            start = Path(directory).resolve()
            self.assertEqual(start / ".agent" / "traycer.env", MODULE.find_identity_file(start))

    def test_cli_reports_supplied_identity_from_the_worktree_root(self) -> None:
        self.write(VALID_FILE)
        environment = os.environ.copy()
        environment.pop("TRAYCER_AGENT_ID", None)
        environment.pop("TRAYCER_EPIC_ID", None)
        nested = self.root / "deep"
        nested.mkdir()
        completed = subprocess.run(
            [sys.executable, str(DETECTOR)],
            env=environment,
            cwd=nested,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("supplied", payload["backend_source"])
        self.assertEqual("agent-1", payload["traycer_agent_id"])
        self.assertEqual(
            {
                "backend_source",
                "detection_status",
                "execution_backend",
                "reason",
                "traycer_agent_id",
                "traycer_epic_id",
            },
            set(payload),
        )

    def test_cli_exits_two_on_malformed_file(self) -> None:
        self.write("export TRAYCER_AGENT_ID=a\n")
        environment = os.environ.copy()
        environment.pop("TRAYCER_AGENT_ID", None)
        environment.pop("TRAYCER_EPIC_ID", None)
        completed = subprocess.run(
            [sys.executable, str(DETECTOR)],
            env=environment,
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("missing key", json.loads(completed.stdout)["reason"])


if __name__ == "__main__":
    unittest.main()
