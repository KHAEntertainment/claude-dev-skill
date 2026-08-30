#!/usr/bin/env python3
"""Detect the /dev execution backend from the Traycer session contract."""

from __future__ import annotations

import json
import os
import sys


def detect_backend(environment: dict[str, str] | None = None) -> dict[str, str | None]:
    """Return a deterministic backend decision without probing installed binaries."""
    env = os.environ if environment is None else environment
    agent_id = env.get("TRAYCER_AGENT_ID", "").strip()
    epic_id = env.get("TRAYCER_EPIC_ID", "").strip()

    if agent_id and epic_id:
        return {
            "execution_backend": "traycer",
            "detection_status": "ready",
            "traycer_agent_id": agent_id,
            "traycer_epic_id": epic_id,
            "reason": "both Traycer session identifiers are present",
        }
    if not agent_id and not epic_id:
        return {
            "execution_backend": "claude-native",
            "detection_status": "ready",
            "traycer_agent_id": None,
            "traycer_epic_id": None,
            "reason": "no Traycer session identifiers are present",
        }
    missing = "TRAYCER_EPIC_ID" if agent_id else "TRAYCER_AGENT_ID"
    return {
        "execution_backend": "incomplete",
        "detection_status": "incomplete",
        "traycer_agent_id": agent_id or None,
        "traycer_epic_id": epic_id or None,
        "reason": f"partial Traycer session context; {missing} is missing",
    }


def main() -> int:
    decision = detect_backend()
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 2 if decision["detection_status"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
