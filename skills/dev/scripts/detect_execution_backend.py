#!/usr/bin/env python3
"""Detect the /dev execution backend from the Traycer session contract."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

AGENT_KEY = "TRAYCER_AGENT_ID"
EPIC_KEY = "TRAYCER_EPIC_ID"
IDENTITY_KEYS = (AGENT_KEY, EPIC_KEY)
IDENTITY_RELATIVE = Path(".agent") / "traycer.env"
IDENTITY_LABEL = ".agent/traycer.env"
MAX_IDENTITY_BYTES = 4096  # two short assignments; bounds the read

_ASSIGNMENT = re.compile(r"export ([A-Za-z_][A-Za-z0-9_]*)=(.*)")
_VALUE = re.compile(r"[A-Za-z0-9._:-]+")


class IdentityFileError(Exception):
    """The identity file exists but is not the exact two-line format."""


def find_identity_file(start: Path | None = None) -> Path:
    """Locate `.agent/traycer.env` at the worktree root.

    The root is the first directory, walking up from `start` (default: the
    current directory), that holds a `.git` entry. A linked worktree has a
    `.git` file, so `.exists()` is the test. With no `.git` anywhere above,
    the starting directory is used.
    """
    current = (Path.cwd() if start is None else start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate / IDENTITY_RELATIVE
    return current / IDENTITY_RELATIVE


def load_identity_file(path: Path) -> dict[str, str] | None:
    """Return both identifiers from `path`, or None when the file does not exist.

    Never returns a partial read: any defect raises IdentityFileError naming
    the first defect in line order. Values are never echoed.
    """
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_IDENTITY_BYTES + 1)
        raw = data.decode("utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError) as error:
        detail = error.strerror if isinstance(error, OSError) and error.strerror else "not valid UTF-8"
        raise IdentityFileError(f"unreadable ({detail})") from error

    if len(data) > MAX_IDENTITY_BYTES:
        raise IdentityFileError(f"extra content (larger than {MAX_IDENTITY_BYTES} bytes)")
    if raw.endswith("\n"):
        raw = raw[:-1]
    lines = raw.split("\n") if raw else []
    found: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        if number > 2:
            raise IdentityFileError(f"extra line (line {number})")
        match = _ASSIGNMENT.fullmatch(line)
        if not match:
            raise IdentityFileError(f"line {number} is not an `export KEY=value` assignment")
        key, value = match.groups()
        if key not in IDENTITY_KEYS:
            raise IdentityFileError(f"line {number} has wrong key name {key}")
        if key in found:
            raise IdentityFileError(f"duplicate key {key} (line {number})")
        if not value.strip():
            raise IdentityFileError(f"empty value for {key} (line {number})")
        if not _VALUE.fullmatch(value):
            raise IdentityFileError(
                f"value for {key} (line {number}) has characters outside [A-Za-z0-9._:-]"
            )
        found[key] = value
    for key in IDENTITY_KEYS:
        if key not in found:
            raise IdentityFileError(f"missing key {key}")
    return found


def _incomplete(agent_id: str | None, epic_id: str | None, reason: str) -> dict[str, str | None]:
    return {
        "execution_backend": "incomplete",
        "detection_status": "incomplete",
        "traycer_agent_id": agent_id,
        "traycer_epic_id": epic_id,
        "backend_source": None,
        "reason": reason,
    }


def _ready(agent_id: str, epic_id: str, source: str, reason: str) -> dict[str, str | None]:
    return {
        "execution_backend": "traycer",
        "detection_status": "ready",
        "traycer_agent_id": agent_id,
        "traycer_epic_id": epic_id,
        "backend_source": source,
        "reason": reason,
    }


def detect_backend(
    environment: dict[str, str] | None = None,
    identity_file: Path | None = None,
) -> dict[str, str | None]:
    """Return a deterministic backend decision without probing installed binaries.

    `identity_file` is consulted only when neither identifier is in the
    environment; sources are never mixed. Passing None never reads a file.
    """
    env = os.environ if environment is None else environment
    agent_id = env.get(AGENT_KEY, "").strip()
    epic_id = env.get(EPIC_KEY, "").strip()

    if agent_id and epic_id:
        return _ready(agent_id, epic_id, "detected", "both Traycer session identifiers are present")
    if not agent_id and not epic_id:
        if identity_file is not None:
            try:
                supplied = load_identity_file(identity_file)
            except IdentityFileError as error:
                return _incomplete(None, None, f"invalid {IDENTITY_LABEL}: {error}")
            if supplied is not None:
                return _ready(
                    supplied[AGENT_KEY],
                    supplied[EPIC_KEY],
                    "supplied",
                    f"both Traycer session identifiers were supplied by {identity_file}",
                )
        return _incomplete(
            None,
            None,
            "no Traycer session identifiers are present; backend cannot be determined",
        )
    missing = EPIC_KEY if agent_id else AGENT_KEY
    return _incomplete(
        agent_id or None,
        epic_id or None,
        f"partial Traycer session context; {missing} is missing",
    )


def main() -> int:
    decision = detect_backend(identity_file=find_identity_file())
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 2 if decision["detection_status"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
