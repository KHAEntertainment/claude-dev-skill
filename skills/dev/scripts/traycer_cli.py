#!/usr/bin/env python3
"""Run the Traycer CLI with the session identity the backend detector resolves.

Usage: traycer_cli.py <traycer args...>

The Traycer CLI takes its caller and epic from TRAYCER_AGENT_ID and
TRAYCER_EPIC_ID. A lead whose harness does not export them supplies them in
`.agent/traycer.env`; this wrapper applies the same lookup and rules as
detect_execution_backend.py, so the two cannot disagree.

Identity in the environment: `traycer <args>` runs with the environment
untouched. Identity from the file: both identifiers are exported from it. On
success stdout, stderr, and the exit code are traycer's own.

Failure before `traycer` runs writes nothing to stdout and one line of JSON
to stderr, `{"traycer_cli":"error","code":...,"reason":...}`. Exit 78 is
`no_usable_identity`; exit 69 is `traycer_not_found` or `traycer_exec_failed`.
Those two values avoid colliding with the traycer exit codes that pass through,
and the `traycer_cli` key is the definitive discriminator.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import detect_execution_backend as detector  # noqa: E402

EXIT_NO_USABLE_IDENTITY = 78
EXIT_TRAYCER_UNAVAILABLE = 69


def _fail(code: str, reason: str, status: int) -> int:
    print(json.dumps({"traycer_cli": "error", "code": code, "reason": reason}), file=sys.stderr)
    return status


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    env = dict(os.environ)
    decision = detector.detect_backend(env, detector.find_identity_file())
    if decision["detection_status"] != "ready":
        return _fail("no_usable_identity", str(decision["reason"]), EXIT_NO_USABLE_IDENTITY)
    if decision["backend_source"] == "supplied":
        env[detector.AGENT_KEY] = str(decision["traycer_agent_id"])
        env[detector.EPIC_KEY] = str(decision["traycer_epic_id"])

    executable = shutil.which("traycer", path=env.get("PATH"))
    if executable is None:
        return _fail("traycer_not_found", "traycer is not on PATH", EXIT_TRAYCER_UNAVAILABLE)
    try:
        completed = subprocess.run([executable, *args], env=env, check=False)
    except OSError as error:
        return _fail(
            "traycer_exec_failed",
            f"could not run {executable}: {error.strerror or type(error).__name__}",
            EXIT_TRAYCER_UNAVAILABLE,
        )
    return 128 - completed.returncode if completed.returncode < 0 else completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
