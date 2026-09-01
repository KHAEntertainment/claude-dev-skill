#!/usr/bin/env python3
"""Resolve the canonical GitHub repository before any /dev GitHub operation.

Read-only by construction. This helper asks git for the effective push remote,
enumerates that remote's real fetch and push URLs, and verifies they all resolve
to one canonical `OWNER/REPO`. It never creates, comments on, reviews, merges, or
otherwise mutates a repository. When it cannot establish one unambiguous identity
it exits 2 so the caller pauses before the write instead of letting `gh` or `git`
pick a base repository for it.
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


def _decide_repository(
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
        "effective_push_remote": remote_name,
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
    origin_urls = push_urls + fetch_urls

    if not origin_urls:
        result["reason_code"] = "missing_origin"
        result["reason"] = (
            f"effective push remote `{remote_name}` has no configured fetch or push URLs; "
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

    # Record other GitHub remotes that disagree, but do not fail closed unless
    # the disagreement is with the effective push remote or the gh default. The
    # push destination is already the one we validated in `origin_urls`; an
    # unrelated `upstream` on a fork is for the ledger, not a hard stop.
    if conflicts:
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
                f"the configured gh default repository is {default} but the "
                f"effective push remote `{remote_name}` is {candidate}; refusing "
                "to run any GitHub operation until they agree"
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
                f"the effective push remote `{remote_name}` is {candidate} but "
                f"GitHub resolves it to {verified_name}; update the remote before continuing"
            )
            return result

    if expected is not None and not same_repository(expected, candidate):
        result["repository"] = None
        result["reason_code"] = "expected_mismatch"
        result["reason"] = (
            f"the assignment names {expected} but this checkout's "
            f"effective push remote `{remote_name}` is {candidate}"
        )
        return result

    result["status"] = "ready"
    conflict_note = ""
    if conflicts:
        conflict_note = (
            "; non-target GitHub remotes disagree ("
            f"{', '.join(sorted(conflicts))}) but the effective push target is {candidate}"
        )
    if gh_default is not None:
        result["reason_code"] = "origin_matches_default"
        result["reason"] = (
            f"effective push remote `{remote_name}` and the gh default repository "
            f"both resolve to {candidate}{conflict_note}"
        )
    else:
        result["reason_code"] = "origin_is_only_github_remote"
        result["reason"] = (
            f"effective push remote `{remote_name}` resolves to {candidate}"
            f"{conflict_note}"
        )
    return result


def resolve_repository(**kwargs: object) -> dict[str, object]:
    """Decide the canonical repository and enforce the do-not-act invariant.

    `_decide_repository` has nine failure returns. Rather than remember to clear
    the actionable field at each one -- the enumerate-the-cases habit that this
    guard has lost to repeatedly -- the invariant is enforced once, here, on the
    way out: a verdict whose status is not `ready` carries no push target.
    A consumer that ignores the status still cannot harvest a usable remote.
    """
    result = _decide_repository(**kwargs)  # type: ignore[arg-type]
    if result.get("status") != "ready":
        # Null every field that names a remote a caller could substitute into a
        # command. `remote` is an identical twin of `effective_push_remote` --
        # nulling only one would leave the same exploit one field sideways. The
        # rejected remote is still named inside `reason`, which is prose for a
        # human, not a value a script interpolates.
        for actionable in ("effective_push_remote", "remote"):
            result[actionable] = None
    return result


def read_command(
    command: list[str], *, cwd: Path, merge_stderr: bool = True
) -> tuple[int, str]:
    """Run one read-only command and return its exit status and stdout.

    Most probes merge stderr into stdout so error banners are visible in the
    compact JSON. The `gh repo set-default --view` probe is special: a missing
    default is reported on stderr with exit 0, so we must keep stdout clean.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
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
    status, output = read_command(["git", "remote"], cwd=repo_dir)
    if status == -1:
        raise RepositoryError("git_cli_missing", "git CLI is not installed or not in PATH")
    if status != 0:
        raise RepositoryError("missing_origin", "`git remote` failed in this checkout")

    names = [line.strip() for line in output.splitlines() if line.strip()]
    fetch: dict[str, list[str]] = {}
    push: dict[str, list[str]] = {}
    for name in names:
        fetch_status, fetch_output = read_command(["git", "remote", "get-url", "--all", name], cwd=repo_dir)
        if fetch_status == 0:
            fetch[name] = [line.strip() for line in fetch_output.splitlines() if line.strip()]
        else:
            fetch[name] = []

        push_status, push_output = read_command(["git", "remote", "get-url", "--push", "--all", name], cwd=repo_dir)
        if push_status == 0:
            push[name] = [line.strip() for line in push_output.splitlines() if line.strip()]
        else:
            push[name] = []
    return fetch, push


def get_effective_push_remote(repo_dir: Path, *, fallback: str = "origin") -> str:
    """Resolve the git remote that will receive a push for the current branch."""
    status, output = read_command(["git", "branch", "--show-current"], cwd=repo_dir)
    if status == -1:
        raise RepositoryError("git_cli_missing", "git CLI is not installed or not in PATH")
    current_branch = output.splitlines()[0].strip() if status == 0 and output else ""

    for key in (
        f"branch.{current_branch}.pushRemote",
        "remote.pushDefault",
        f"branch.{current_branch}.remote",
    ):
        if not current_branch and key.startswith("branch."):
            continue
        status, output = read_command(["git", "config", key], cwd=repo_dir)
        if status == 0 and output:
            return output.splitlines()[0].strip()
    return fallback


def collect_gh_default(repo_dir: Path) -> str | None:
    """`gh repo set-default --view` takes no repository argument.

    gh reports a missing default on stderr with exit 0, so stdout must not be
    merged with stderr. A non-OWNER/REPO banner is also treated as unreadable.
    """
    status, output = read_command(
        ["gh", "repo", "set-default", "--view"],
        cwd=repo_dir,
        merge_stderr=False,
    )
    if status == -1:
        raise RepositoryError("gh_cli_missing", "gh CLI is not installed or not in PATH")
    if status == 0 and output:
        first = output.splitlines()[0].strip()
        try:
            parse_owner_repo(first, label="gh default repository")
        except RepositoryError as exc:
            raise RepositoryError("gh_default_unreadable", str(exc))
        return first
    if status == 0:
        return None
    if status != 0 and output and ("no default" in output.lower() or "no default repository" in output.lower()):
        return None
    if status != 0:
        raise RepositoryError("gh_default_unreadable", f"could not read gh default: {output[:200]}")
    return None


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
        "--print-push-remote",
        action="store_true",
        help=(
            "print only the validated push remote name, and only when the verdict "
            "is `ready`; otherwise print nothing on stdout and exit 2"
        ),
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
            remote_name = str(fixture.get("effective_push_remote", args.remote))
        else:
            repo_dir = args.repo_dir.resolve()
            remotes, push_remotes = collect_remotes(repo_dir)
            remote_name = get_effective_push_remote(repo_dir)
            gh_default = collect_gh_default(repo_dir)
            access_verified = not args.no_verify_access
            verified_name = None
            if access_verified:
                try:
                    canonical = _first_canonical(remotes, push_remotes, remote_name)
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
            remote_name=remote_name,
        )
    except RepositoryError as exc:
        decision = {
            "status": "incomplete",
            "repository": None,
            "effective_push_remote": None,
            "remote": args.remote,
            "remote_url": None,
            "push_url": None,
            "gh_default": None,
            "conflicting_remotes": [],
            "reason_code": exc.code,
            "reason": str(exc),
        }

    ready = decision["status"] == "ready"

    if args.print_push_remote:
        # Capability-shaped output: on `ready` stdout is the remote name and
        # nothing else, so `$(...)` yields a usable value. On any other verdict
        # stdout is empty and the reason goes to stderr, so a caller that pipes
        # this command -- and thereby loses its exit status -- still gets an
        # empty target and fails loudly instead of pushing somewhere rejected.
        if ready:
            print(decision["effective_push_remote"])
        else:
            print(decision["reason"], file=sys.stderr)
        return 0 if ready else 2

    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
