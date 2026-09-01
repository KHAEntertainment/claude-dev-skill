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

# Bounded so a hung `gh` / `git` cannot block the lead indefinitely.
COMMAND_TIMEOUT = 30

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


def redact_remote(url: str | None) -> str | None:
    """Return a display-safe copy of *url* with any userinfo removed.

    Credentials in an HTTPS remote are the primary concern. The output is never
    used to connect; it is only recorded in the resolver JSON and in the ledger
    so that a token-bearing origin cannot be persisted in committed state.
    """
    if url is None:
        return None
    text = (url or "").strip()
    if not text:
        return text

    if "://" in text:
        scheme, _, rest = text.partition("://")
        authority, _, path = rest.partition("/")
        # authority may be userinfo@host:port; keep only host:port
        safe_authority = authority.rsplit("@", 1)[-1]
        redacted = f"{scheme}://{safe_authority}"
        if path:
            redacted = f"{redacted}/{path}"
        return redacted

    # SCP-like or bare host:path
    if "@" in text:
        _, _, after = text.partition("@")
        return after
    return text


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


def _as_list(value: object) -> list[str]:
    """Accept a single string or a list of strings for fixture and internal use."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _first_canonical(
    remotes: dict[str, list[str] | str],
    push_remotes: dict[str, list[str] | str] | None,
    remote_name: str,
) -> str | None:
    """Return the first normalisable canonical repo for *remote_name*, or None."""
    push_lookup = push_remotes or {}
    urls = _as_list(remotes.get(remote_name, [])) + _as_list(push_lookup.get(remote_name, []))
    for url in urls:
        try:
            return normalize_remote(url)
        except RepositoryError:
            continue
    return None


def resolve_repository(
    *,
    remotes: dict[str, list[str] | str],
    push_remotes: dict[str, list[str] | str] | None = None,
    gh_default: str | None,
    verified_name: str | None = None,
    access_verified: bool = False,
    expected: str | None = None,
    remote_name: str = "origin",
) -> dict[str, object]:
    """Decide the canonical repository, or fail closed with a named mismatch."""
    push_lookup = push_remotes or {}

    result: dict[str, object] = {
        "status": "incomplete",
        "repository": None,
        "remote": remote_name,
        "remote_url": None,
        "push_url": None,
        "gh_default": gh_default,
        "conflicting_remotes": [],
        "reason_code": "",
        "reason": "",
    }

    fetch_urls = _as_list(remotes.get(remote_name, []))
    push_urls = _as_list(push_lookup.get(remote_name, []))
    origin_urls = fetch_urls + push_urls

    if not origin_urls:
        result["reason_code"] = "missing_origin"
        result["reason"] = (
            f"no `{remote_name}` remote is configured; "
            "repository identity cannot be established"
        )
        return result

    candidate: str | None = None
    first_valid_url: str | None = None
    for url in origin_urls:
        try:
            canon = normalize_remote(url)
        except RepositoryError as exc:
            result["reason_code"] = exc.code
            result["reason"] = f"`{remote_name}` URL `{redact_remote(url)}` is unusable: {exc}"
            return result

        if first_valid_url is None:
            first_valid_url = url
            candidate = canon
            continue

        if not same_repository(canon, candidate):
            result["remote_url"] = redact_remote(first_valid_url)
            result["push_url"] = redact_remote(url)
            result["reason_code"] = "remote_url_mismatch"
            result["reason"] = (
                f"`{remote_name}` has multiple URLs that resolve differently: "
                f"{redact_remote(first_valid_url)} -> {candidate} but "
                f"{redact_remote(url)} -> {canon}"
            )
            return result

    # Defensive: should not happen, because empty origin_urls is handled above.
    assert candidate is not None  # noqa: S101
    assert first_valid_url is not None  # noqa: S101

    result["repository"] = candidate
    result["remote_url"] = redact_remote(first_valid_url)

    all_remote_names = set(remotes) | set(push_lookup)
    conflicts: set[str] = set()
    for name in sorted(all_remote_names):
        if name == remote_name:
            continue
        other_urls = _as_list(remotes.get(name, [])) + _as_list(push_lookup.get(name, []))
        for other_url in other_urls:
            try:
                other = normalize_remote(other_url)
            except RepositoryError:
                continue
            if not same_repository(other, candidate):
                conflicts.add(f"{name}={other}")
    result["conflicting_remotes"] = sorted(conflicts)

    if gh_default is not None:
        try:
            default = parse_owner_repo(gh_default, label="gh default repository")
        except RepositoryError as exc:
            result["repository"] = None
            result["reason_code"] = exc.code
            result["reason"] = str(exc)
            return result
        if not same_repository(default, candidate):
            result["repository"] = None
            result["reason_code"] = "default_conflicts_with_origin"
            result["reason"] = (
                f"the configured gh default repository is {default} but "
                f"`{remote_name}` is {candidate}; refusing to run any GitHub "
                "operation until they agree"
            )
            return result
    elif conflicts:
        result["repository"] = None
        result["reason_code"] = "ambiguous_default"
        result["reason"] = (
            f"no gh default repository is configured and `{remote_name}` is "
            f"{candidate} while other GitHub remotes point elsewhere "
            f"({', '.join(conflicts)}); gh would be free to resolve a "
            "different base repository"
        )
        return result

    if access_verified:
        if verified_name is None:
            result["repository"] = None
            result["reason_code"] = "inaccessible_repository"
            result["reason"] = (
                f"{candidate} could not be read with the current gh credentials"
            )
            return result
        if not same_repository(verified_name, candidate):
            result["repository"] = None
            result["reason_code"] = "origin_redirects"
            result["reason"] = (
                f"`{remote_name}` is {candidate} but GitHub resolves it to "
                f"{verified_name}; update the remote before continuing"
            )
            return result

    if expected is not None and not same_repository(expected, candidate):
        result["repository"] = None
        result["reason_code"] = "expected_mismatch"
        result["reason"] = (
            f"the assignment names {expected} but this checkout's "
            f"`{remote_name}` is {candidate}"
        )
        return result

    result["status"] = "ready"
    if gh_default is not None:
        result["reason_code"] = "origin_matches_default"
        result["reason"] = (
            f"`{remote_name}` and the gh default repository both resolve to {candidate}"
        )
    else:
        result["reason_code"] = "origin_is_only_github_remote"
        result["reason"] = (
            f"`{remote_name}` resolves to {candidate} and no other GitHub remote "
            "or gh default disagrees"
        )
    return result


def read_command(command: list[str], *, cwd: Path) -> tuple[int, str]:
    """Run one read-only command and return its exit status and stdout."""
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT,
        )
    except OSError as exc:
        return (-1, str(exc))
    except subprocess.SubprocessError as exc:
        return (124, str(exc))
    return completed.returncode, completed.stdout.strip()


def collect_remotes(repo_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    status, output = read_command(["git", "remote", "-v"], cwd=repo_dir)
    if status == -1:
        raise RepositoryError("git_cli_missing", "git CLI is not installed or not in PATH")
    if status != 0:
        raise RepositoryError("missing_origin", "`git remote -v` failed in this checkout")
    fetch: dict[str, list[str]] = {}
    push: dict[str, list[str]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, url, kind = parts[0], parts[1], parts[2].strip("()")
        if kind == "fetch":
            fetch.setdefault(name, []).append(url)
        elif kind == "push":
            push.setdefault(name, []).append(url)
    return fetch, push


def collect_gh_default(repo_dir: Path) -> str | None:
    status, output = read_command(["gh", "repo", "set-default", "--view"], cwd=repo_dir)
    if status == -1:
        raise RepositoryError("gh_cli_missing", "gh CLI is not installed or not in PATH")
    if status != 0 or not output or "no default repository" in output.lower():
        return None
    return output.splitlines()[0].strip()


def collect_verified_name(repo_dir: Path, repository: str) -> str | None:
    """`gh repo view` takes a positional repository argument, never `--repo`."""
    status, output = read_command(
        ["gh", "repo", "view", repository, "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=repo_dir,
    )
    if status == -1:
        raise RepositoryError("gh_cli_missing", "gh CLI is not installed or not in PATH")
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
            remotes = {str(k): _as_list(v) for k, v in fixture["remotes"].items()}
            push_raw = fixture.get("push_remotes")
            if isinstance(push_raw, dict):
                push_remotes = {str(k): _as_list(v) for k, v in push_raw.items()}
            else:
                push_remotes = None
            raw_default = fixture.get("gh_default")
            gh_default = None if raw_default is None else str(raw_default)
            access_verified = bool(fixture.get("access_verified", False))
            raw_verified = fixture.get("verified_name")
            verified_name = None if raw_verified is None else str(raw_verified)
        else:
            repo_dir = args.repo_dir.resolve()
            remotes, push_remotes = collect_remotes(repo_dir)
            gh_default = collect_gh_default(repo_dir)
            access_verified = not args.no_verify_access
            verified_name = None
            if access_verified:
                try:
                    canonical = _first_canonical(remotes, push_remotes, args.remote)
                except RepositoryError:
                    access_verified = False
                else:
                    if canonical is not None:
                        verified_name = collect_verified_name(repo_dir, canonical)

        decision = resolve_repository(
            remotes=remotes,
            push_remotes=push_remotes,
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
            "push_url": None,
            "gh_default": None,
            "conflicting_remotes": [],
            "reason_code": exc.code,
            "reason": str(exc),
        }

    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0 if decision["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
