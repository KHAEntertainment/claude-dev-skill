"""The Traycer CLI wrapper, exercised against a fake `traycer` on a scratch PATH.

Every test runs the wrapper in a scratch worktree (an empty `.git` marker
stops the identity-file walk-up there) with `TRAYCER_*` scrubbed from the
inherited environment, so nothing reads a real `.agent/` and nothing runs the
real `traycer` binary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "skills" / "dev" / "scripts" / "traycer_cli.py"
VALID_FILE = "export TRAYCER_AGENT_ID=file-agent\nexport TRAYCER_EPIC_ID=file-epic\n"

FAKE_TRAYCER = f"""#!{sys.executable}
import json, os, sys
with open(os.environ["FAKE_LOG"], "w", encoding="utf-8") as log:
    json.dump(
        {{
            "argv": sys.argv[1:],
            "agent": os.environ.get("TRAYCER_AGENT_ID"),
            "epic": os.environ.get("TRAYCER_EPIC_ID"),
        }},
        log,
    )
sys.stdout.write("fake-stdout")
sys.stderr.write("fake-stderr")
raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))
"""


@unittest.skipIf(os.name == "nt", "the fake traycer is a POSIX shebang script")
class TraycerWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.worktree = self.root / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        (self.worktree / ".agent").mkdir()
        self.identity = self.worktree / ".agent" / "traycer.env"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "fake.log"

    def install_fake(self, content: str = FAKE_TRAYCER) -> None:
        fake = self.bin / "traycer"
        fake.write_text(content, encoding="utf-8")
        fake.chmod(0o755)

    def run_wrapper(
        self, *args: str, extra_env: dict[str, str] | None = None, path: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("TRAYCER_", "FAKE_"))
        }
        environment["PATH"] = str(self.bin) if path is None else path
        environment["FAKE_LOG"] = str(self.log)
        environment.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(WRAPPER), *args],
            env=environment,
            cwd=self.worktree,
            check=False,
            capture_output=True,
            text=True,
        )

    def recorded(self) -> dict[str, object]:
        return json.loads(self.log.read_text(encoding="utf-8"))

    def assert_failed_before_traycer(
        self, completed: subprocess.CompletedProcess[str], status: int, code: str
    ) -> dict[str, str]:
        self.assertEqual(status, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertFalse(self.log.exists(), "traycer must not run")
        lines = completed.stderr.splitlines()
        self.assertEqual(1, len(lines))
        payload = json.loads(lines[0])
        self.assertEqual({"traycer_cli", "code", "reason"}, set(payload))
        self.assertEqual("error", payload["traycer_cli"])
        self.assertEqual(code, payload["code"])
        return payload

    def test_env_identity_runs_traycer_unchanged_and_passes_output_through(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        completed = self.run_wrapper(
            "agent", "list", "--json",
            extra_env={"TRAYCER_AGENT_ID": "env-agent", "TRAYCER_EPIC_ID": "env-epic", "FAKE_EXIT": "7"},
        )
        self.assertEqual(7, completed.returncode)
        self.assertEqual("fake-stdout", completed.stdout)
        self.assertEqual("fake-stderr", completed.stderr)
        self.assertEqual(
            {"argv": ["agent", "list", "--json"], "agent": "env-agent", "epic": "env-epic"},
            self.recorded(),
        )

    def test_supplied_file_exports_both_identifiers(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        completed = self.run_wrapper("whoami", "--json")
        self.assertEqual(0, completed.returncode)
        self.assertEqual("fake-stdout", completed.stdout)
        self.assertEqual(
            {"argv": ["whoami", "--json"], "agent": "file-agent", "epic": "file-epic"},
            self.recorded(),
        )

    def test_arguments_reach_traycer_as_unchanged_argv_elements(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        arguments = ["agent", "send", "--message", "two words; rm -rf $HOME `id` \"q\"", "", "--help"]
        completed = self.run_wrapper(*arguments)
        self.assertEqual(0, completed.returncode)
        self.assertEqual(arguments, self.recorded()["argv"])

    def test_no_arguments_still_run_traycer(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        self.assertEqual(0, self.run_wrapper().returncode)
        self.assertEqual([], self.recorded()["argv"])

    def test_no_identity_fails_with_one_line_reason_and_empty_stdout(self) -> None:
        self.install_fake()
        payload = self.assert_failed_before_traycer(self.run_wrapper("whoami"), 78, "no_usable_identity")
        self.assertIn("no Traycer session identifiers", payload["reason"])

    def test_one_env_identifier_never_borrows_from_the_file(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        completed = self.run_wrapper("whoami", extra_env={"TRAYCER_AGENT_ID": "env-agent"})
        payload = self.assert_failed_before_traycer(completed, 78, "no_usable_identity")
        self.assertIn("TRAYCER_EPIC_ID is missing", payload["reason"])

    def test_malformed_file_fails_naming_the_defect(self) -> None:
        self.install_fake()
        self.identity.write_text("export TRAYCER_AGENT_ID=a\n", encoding="utf-8")
        payload = self.assert_failed_before_traycer(self.run_wrapper("whoami"), 78, "no_usable_identity")
        self.assertIn("missing key TRAYCER_EPIC_ID", payload["reason"])

    def test_traycer_missing_from_path_fails_without_running(self) -> None:
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        self.assert_failed_before_traycer(self.run_wrapper("whoami"), 69, "traycer_not_found")

    def test_identity_failure_is_reported_before_a_missing_binary(self) -> None:
        self.assert_failed_before_traycer(self.run_wrapper("whoami"), 78, "no_usable_identity")

    def test_unlaunchable_traycer_fails_with_exec_failed(self) -> None:
        self.install_fake("#!/nonexistent/interpreter\n")
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        self.assert_failed_before_traycer(self.run_wrapper("whoami"), 69, "traycer_exec_failed")

    def test_identity_is_found_from_a_subdirectory_of_the_worktree(self) -> None:
        self.install_fake()
        self.identity.write_text(VALID_FILE, encoding="utf-8")
        nested = self.worktree / "deep" / "er"
        nested.mkdir(parents=True)
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("TRAYCER_", "FAKE_"))
        }
        environment.update({"PATH": str(self.bin), "FAKE_LOG": str(self.log)})
        completed = subprocess.run(
            [sys.executable, str(WRAPPER), "whoami"],
            env=environment,
            cwd=nested,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode)
        self.assertEqual("file-agent", self.recorded()["agent"])


if __name__ == "__main__":
    unittest.main()
