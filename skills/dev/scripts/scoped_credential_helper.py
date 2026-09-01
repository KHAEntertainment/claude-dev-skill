#!/usr/bin/env python3
"""Hand the real git credential only to the canonical repository.

A git credential helper. Git speaks a line protocol on stdin/stdout: a block of
`key=value` lines terminated by a blank line. For the `get` action a helper
answers with `username=` / `password=` lines, or says nothing to decline.

Why this exists
---------------
Every prior attempt to keep `/dev` from writing to the wrong repository was a
*verification*: inspect git config, decide, then trust the workflow to obey the
decision. Nine review rounds found nine ways for a write to reach a
non-canonical repository anyway -- the last of them because a rejected verdict
still carried a usable remote name and the consumer read it through a pipe that
discarded the exit status.

This is not a verification. It removes the authority. A push aimed anywhere
other than the canonical repository is answered with a syntactically valid but
dead credential, so it fails at GitHub with an authentication error instead of
succeeding against a stranger's repository. The failure is loud, server-side,
and cannot be argued away by anything running locally.

Requirements
------------
`credential.useHttpPath=true` must be set for the run. Without it git asks by
host alone -- the `path` key is absent -- and repository-level discrimination is
impossible. A missing `path` is therefore treated as a misconfiguration and gets
the canary, not the real secret.

This helper is only load-bearing when it is the **only** credential helper for
the run. Git consults helpers in order and uses the first that answers, so an
inherited `osxkeychain`, `store`, or `manager` entry will hand over the ambient
account-wide credential before this helper is ever consulted. Reset the list
first -- an empty `credential.helper` value clears everything inherited:

    git config --add credential.helper ""
    git config --add credential.helper "!... scoped_credential_helper.py"

On macOS this reset is mandatory rather than tidy-up: Apple's git ships
`credential.helper=osxkeychain` in a config inside Xcode
(`/Applications/Xcode.app/.../git-core/gitconfig`) which `GIT_CONFIG_SYSTEM`
does not override, so the ambient keychain helper answers first on essentially
every stock macOS checkout unless the list is explicitly reset.

`--check-config` refuses to report `enforced` unless that reset is in place.
This was found by integration testing: the unit tests passed while a real
`git credential fill` still returned the ambient keychain token.

Scope
-----
This covers HTTPS remotes. SSH remotes (`git@github.com:owner/repo.git`) never
consult a credential helper at all, and SSH keys are account-wide rather than
repository-scoped. A run that needs this guarantee must either rewrite SSH
remotes to HTTPS or refuse them; see `--check-config`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# A well-formed token that GitHub will reject. Shape matters: a blank or obviously
# broken value can make git prompt interactively or fall through to another
# helper, either of which would reintroduce the real credential.
CANARY_TOKEN = "ghp_000000000000000000000000000000000000"
CANARY_USERNAME = "dev-skill-canary"

CANONICAL_ENV = "DEV_CANONICAL_REPO"
TRIPWIRE_ENV = "DEV_CREDENTIAL_TRIPWIRE"
REAL_TOKEN_ENV = "DEV_CANONICAL_TOKEN"


def parse_credential_block(stream: object) -> dict[str, str]:
    """Read git's `key=value` block, stopping at a blank line or EOF."""
    fields: dict[str, str] = {}
    for raw in stream:  # type: ignore[attr-defined]
        line = raw.rstrip("\n")
        if line == "":
            break
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value
    return fields


def normalize_repo_path(path: str | None) -> str | None:
    """Turn git's `path` value into a bare `owner/repo`, or None if unusable."""
    if path is None:
        return None
    candidate = path.strip().strip("/")
    if candidate.endswith(".git"):
        candidate = candidate[: -len(".git")]
    parts = [segment for segment in candidate.split("/") if segment]
    if len(parts) != 2:
        return None
    return "/".join(parts)


def same_repository(left: str, right: str) -> bool:
    return left.casefold() == right.casefold()


def record_tripwire(attempted: str | None, canonical: str, fields: dict[str, str]) -> None:
    """Append a durable record of a credential request for a non-canonical repo.

    A misroute that is merely refused teaches nobody anything. The next variant
    is found by reading these records, not by waiting for someone to notice a
    pull request in a stranger's repository.
    """
    target = os.environ.get(TRIPWIRE_ENV)
    if not target:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = fields.get("host", "<no host>")
    entry = (
        f"{stamp}\tattempted={attempted or '<unparseable>'}"
        f"\tcanonical={canonical}\thost={host}\n"
    )
    try:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError:
        # A tripwire that cannot be written must never break the push path; the
        # canary already did the load-bearing work.
        pass


def real_credential(fields: dict[str, str]) -> tuple[str, str] | None:
    """Obtain the genuine credential for the canonical repository.

    Prefers an explicitly provided token. Falls back to `gh auth token` so the
    helper is useful before anyone has set up a scoped token -- the canary
    guarantee does not depend on that upgrade.
    """
    token = os.environ.get(REAL_TOKEN_ENV)
    if token:
        return fields.get("username") or "x-access-token", token
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        return None
    return fields.get("username") or "x-access-token", value


def handle_get(fields: dict[str, str], canonical: str) -> tuple[str, str]:
    """Return the (username, password) git should use, and never raise."""
    requested = normalize_repo_path(fields.get("path"))

    if requested is None or not same_repository(requested, canonical):
        # Covers three cases that must all fail closed: a different repository,
        # a path git could not supply because `useHttpPath` is unset, and a path
        # shaped in a way this helper does not understand.
        record_tripwire(requested, canonical, fields)
        return CANARY_USERNAME, CANARY_TOKEN

    credential = real_credential(fields)
    if credential is None:
        # No real secret available. Declining would let git fall through to
        # another helper or an interactive prompt, so answer with the canary and
        # let the push fail with an authentication error instead.
        return CANARY_USERNAME, CANARY_TOKEN
    return credential


def check_config(repo_dir: Path) -> int:
    """Report whether this run is actually able to enforce the guarantee."""
    problems: list[str] = []

    def git(*args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return completed.stdout.strip()

    # Git uses the first helper that answers. If anything is configured after
    # the last empty-string reset besides this helper, that helper answers first
    # and this one never runs -- which is indistinguishable from working, right
    # up until it hands out the ambient credential.
    helpers = git("config", "--get-all", "credential.helper").splitlines()
    effective: list[str] = []
    for entry in helpers:
        if entry.strip() == "":
            effective = []  # an empty value resets the inherited list
        else:
            effective.append(entry)
    foreign = [h for h in effective if "scoped_credential_helper" not in h]
    if foreign:
        problems.append(
            "another credential helper answers first ("
            + ", ".join(foreign)
            + "); reset the list with `git config --add credential.helper \"\"` "
            "before adding the scoped helper, or the ambient credential is used"
        )
    if not effective:
        problems.append("the scoped credential helper is not configured for this run")

    if git("config", "--get", "credential.useHttpPath").lower() != "true":
        problems.append(
            "credential.useHttpPath is not true; git will ask by host only and "
            "this helper cannot tell repositories apart"
        )
    for url in git("remote", "get-url", "--all", "origin").splitlines():
        if url.startswith("git@") or url.startswith("ssh://"):
            problems.append(
                f"origin uses an SSH URL ({url}); SSH never consults a credential "
                "helper, so this guarantee does not apply to it"
            )

    for problem in problems:
        print(f"NOT ENFORCED: {problem}", file=sys.stderr)
    if problems:
        return 2
    print("enforced: credential scoping is live for this checkout")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="get",
        help="git credential action: get, store, or erase",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="verify that credential scoping can actually be enforced here",
    )
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if args.check_config:
        return check_config(args.repo_dir.resolve())

    canonical = normalize_repo_path(os.environ.get(CANONICAL_ENV))
    if canonical is None:
        # Without a canonical repository there is nothing to scope to. Saying
        # nothing lets git continue with its normal credential lookup, which is
        # the correct behaviour for a run that never opted in.
        return 0

    if args.action != "get":
        # `store` and `erase` are deliberately no-ops: this helper owns no
        # storage, and caching a canary would outlive the run.
        return 0

    username, password = handle_get(parse_credential_block(sys.stdin), canonical)
    print(f"username={username}")
    print(f"password={password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
