#!/usr/bin/env python3
"""Resolve the canonical GitHub repository before any /dev GitHub operation.

Read-only by construction. This helper runs at most three commands — `git remote
-v`, `gh repo set-default --view`, and `gh repo view OWNER/REPO --json
nameWithOwner` — and never creates, comments on, reviews, merges, or otherwise
mutates a repository. When it cannot establish one unambiguous identity it exits
2 so the caller pauses before the write instead of letting `gh` pick a base
repository for it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


GITHUB_HOST = "github.com"
SUPPORTED_SCHEMES = frozenset({"https", "http", "ssh", "git"})
SCP_LIKE = re.compile(r"^(?:(?P<user>[^@/]+)@)?(?P<host>[^:/@]+):(?P<path>.+)$")
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

READY_CODES = frozenset({"origin_matches_default", "origin_is_only_github_remote"})


class RepositoryError(RuntimeError):
    """A remote URL, fixture, or command result that cannot be trusted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_remote(url: str) -> str:
    """Return canonical `OWNER/REPO` for an ordinary HTTPS or SSH GitHub remote."""
    text = (url or "").strip()
    if not text:
        raise RepositoryError("ambiguous_origin", "remote URL is empty")

    if "://" in text:
        scheme, _, rest = text.partition("://")
        if scheme.lower() not in SUPPORTED_SCHEMES:
            raise RepositoryError(
                "non_github_origin", f"unsupported remote scheme: {scheme}"
            )
        authority, _, path = rest.partition("/")
        host = authority.rpartition("@")[2].partition(":")[0]
    else:
        match = SCP_LIKE.match(text)
        if not match:
            raise RepositoryError(
                "ambiguous_origin", f"unrecognized remote URL: {text}"
            )
        host = match.group("host")
        path = match.group("path")

    if host.lower() != GITHUB_HOST:
        raise RepositoryError(
            "non_github_origin",
            f"remote host is not {GITHUB_HOST}: {host or text}",
        )

    trimmed = path.strip().strip("/")
    if trimmed[-4:].lower() == ".git":
        trimmed = trimmed[:-4].strip("/")
    segments = [segment for segment in trimmed.split("/") if segment]
    if len(segments) != 2:
        raise RepositoryError(
            "ambiguous_origin", f"remote path is not OWNER/REPO: {path}"
        )

    owner, repository = segments
    if not OWNER_PATTERN.match(owner) or not REPO_PATTERN.match(repository):
        raise RepositoryError(
            "ambiguous_origin", f"remote path is not OWNER/REPO: {path}"
        )
    return f"{owner}/{repository}"


def parse_owner_repo(value: str, *, label: str) -> str:
    """Validate an already-canonical `OWNER/REPO` string such as the `gh` default."""
    segments = [segment for segment in (value or "").strip().split("/") if segment]
    if len(segments) != 2:
        raise RepositoryError("ambiguous_default", f"{label} is not OWNER/REPO: {value}")
    owner, repository = segments
    if not OWNER_PATTERN.match(owner) or not REPO_PATTERN.match(repository):
        raise RepositoryError("ambiguous_default", f"{label} is not OWNER/REPO: {value}")
    return f"{owner}/{repository}"


def same_repository(left: str, right: str) -> bool:
    """GitHub owner and repository names are case-insensitive."""
    return left.casefold() == right.casefold()


def resolve_repository(
    *,
    remotes: dict[str, str],
    gh_default: str | None,
    verified_name: str | None = None,
    access_verified: bool = False,
    expected: str | None = None,
    remote_name: str = "origin",
) -> dict[str, object]:
    """Decide the canonical repository, or fail closed with a named mismatch."""
    result: dict[str, object] = {
        "status": "incomplete",
        "repository": None,
        "remote": remote_name,
        "remote_url": remotes.get(remote_name),
        "gh_default": gh_default,
        "conflicting_remotes": [],
        "reason_code": "",
        "reason": "",
    }

    if remote_name not in remotes:
        result["reason_code"] = "missing_origin"
        result["reason"] = (
            f"no `{remote_name}` remote is configured; "
            "repository identity cannot be established"
        )
        return result

    try:
        origin = normalize_remote(remotes[remote_name])
    except RepositoryError as exc:
        result["reason_code"] = exc.code
        result["reason"] = f"`{remote_name}` remote is unusable: {exc}"
        return result

    result["repository"] = origin

    others: dict[str, str] = {}
    for name, url in sorted(remotes.items()):
        if name == remote_name:
            continue
        try:
            others[name] = normalize_remote(url)
        except RepositoryError:
            continue

    conflicting = sorted(
        f"{name}={value}"
        for name, value in others.items()
        if not same_repository(value, origin)
    )
    result["conflicting_remotes"] = conflicting

    if gh_default is not None:
        try:
            default = parse_owner_repo(gh_default, label="gh default repository")
        except RepositoryError as exc:
            result["repository"] = None
            result["reason_code"] = exc.code
            result["reason"] = str(exc)
            return result
        if not same_repository(default, origin):
            result["repository"] = None
            result["reason_code"] = "default_conflicts_with_origin"
            result["reason"] = (
                f"the configured gh default repository is {default} but "
                f"`{remote_name}` is {origin}; refusing to run any GitHub "
                "operation until they agree"
            )
            return result
    elif conflicting:
        result["repository"] = None
        result["reason_code"] = "ambiguous_default"
        result["reason"] = (
            f"no gh default repository is configured and `{remote_name}` is "
            f"{origin} while other GitHub remotes point elsewhere "
            f"({', '.join(conflicting)}); gh would be free to resolve a "
            "different base repository"
        )
        return result

    if access_verified:
        if verified_name is None:
            result["repository"] = None
            result["reason_code"] = "inaccessible_repository"
            result["reason"] = (
                f"{origin} could not be read with the current gh credentials"
            )
            return result
        if not same_repository(verified_name, origin):
            result["repository"] = None
            result["reason_code"] = "origin_redirects"
            result["reason"] = (
                f"`{remote_name}` is {origin} but GitHub resolves it to "
                f"{verified_name}; update the remote before continuing"
            )
            return result

    if expected is not None and not same_repository(expected, origin):
        result["repository"] = None
        result["reason_code"] = "expected_mismatch"
        result["reason"] = (
            f"the assignment names {expected} but this checkout's "
            f"`{remote_name}` is {origin}"
        )
        return result

    result["status"] = "ready"
    if gh_default is not None:
        result["reason_code"] = "origin_matches_default"
        result["reason"] = (
            f"`{remote_name}` and the gh default repository both resolve to {origin}"
        )
    else:
        result["reason_code"] = "origin_is_only_github_remote"
        result["reason"] = (
            f"`{remote_name}` resolves to {origin} and no other GitHub remote "
            "or gh default disagrees"
        )
    return result


def read_command(command: list[str], *, cwd: Path) -> tuple[int, str]:
    """Run one read-only command and return its exit status and stdout."""
    completed = subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True, check=False
    )
    return completed.returncode, completed.stdout.strip()


def collect_remotes(repo_dir: Path) -> dict[str, str]:
    status, output = read_command(["git", "remote", "-v"], cwd=repo_dir)
    if status != 0:
        raise RepositoryError("missing_origin", "`git remote -v` failed in this checkout")
    remotes: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        remotes.setdefault(parts[0], parts[1])
    return remotes


def collect_gh_default(repo_dir: Path) -> str | None:
    status, output = read_command(["gh", "repo", "set-default", "--view"], cwd=repo_dir)
    if status != 0 or not output or "no default repository" in output.lower():
        return None
    return output.splitlines()[0].strip()


def collect_verified_name(repo_dir: Path, repository: str) -> str | None:
    """`gh repo view` takes a positional repository argument, never `--repo`."""
    status, output = read_command(
        ["gh", "repo", "view", repository, "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=repo_dir,
    )
    if status != 0 or not output:
        return None
    return output.splitlines()[0].strip()


def load_fixture(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryError("ambiguous_origin", f"cannot read fixture {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("remotes"), dict):
        raise RepositoryError(
            "ambiguous_origin", "fixture must contain a remotes object"
        )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--expect", help="canonical OWNER/REPO recorded in the assignment")
    parser.add_argument(
        "--fixture",
        type=Path,
        help="read deterministic remote/default state instead of running commands",
    )
    parser.add_argument(
        "--no-verify-access",
        action="store_true",
        help="skip the read-only gh accessibility check",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.fixture is not None:
            fixture = load_fixture(args.fixture)
            remotes = {str(k): str(v) for k, v in fixture["remotes"].items()}
            raw_default = fixture.get("gh_default")
            gh_default = None if raw_default is None else str(raw_default)
            access_verified = bool(fixture.get("access_verified", False))
            raw_verified = fixture.get("verified_name")
            verified_name = None if raw_verified is None else str(raw_verified)
        else:
            repo_dir = args.repo_dir.resolve()
            remotes = collect_remotes(repo_dir)
            gh_default = collect_gh_default(repo_dir)
            access_verified = not args.no_verify_access
            verified_name = None
            if access_verified and args.remote in remotes:
                try:
                    origin = normalize_remote(remotes[args.remote])
                except RepositoryError:
                    access_verified = False
                else:
                    verified_name = collect_verified_name(repo_dir, origin)

        decision = resolve_repository(
            remotes=remotes,
            gh_default=gh_default,
            verified_name=verified_name,
            access_verified=access_verified,
            expected=args.expect,
            remote_name=args.remote,
        )
    except RepositoryError as exc:
        decision = {
            "status": "incomplete",
            "repository": None,
            "remote": args.remote,
            "remote_url": None,
            "gh_default": None,
            "conflicting_remotes": [],
            "reason_code": exc.code,
            "reason": str(exc),
        }

    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0 if decision["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
