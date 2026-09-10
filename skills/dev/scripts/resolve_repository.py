#!/usr/bin/env python3
"""Resolve the canonical GitHub repository and account before a `/dev` write.

Read-only by construction. This helper asks git for the effective push remote,
enumerates that remote's real fetch and push URLs, and verifies they all
resolve to one canonical `OWNER/REPO` that matches the operation's configured
target from `.dev.json` (see `dev_config.py`). It never creates, comments on,
reviews, merges, or otherwise mutates a repository. When it cannot establish
one unambiguous, matching identity it exits 2 so the caller pauses before the
write instead of letting `gh` or `git` pick a target for it.

Two independent things are validated here, and a caller must not conflate them:

- **Repository identity** (`resolve_repository` / `_decide_repository`): does
  the actual push destination match the configured target for *this*
  operation? A push operation's target is `.dev.json`'s `pushRepository`; a PR
  operation's target is `pullRequestRepository`. The caller selects which one
  to pass as `--expect`.
- **Transport account** (`verify_https_account` / `verify_ssh_account`): does
  the credential Git will actually use match `.dev.json`'s `account`? Neither
  commit authorship, a URL username, nor `gh auth status` establishes this.

The GitHub CLI's own repository default (`gh repo set-default`) is recorded
for the ledger but never blocks a resolution: every supported operation is
explicitly scoped (`--repo`, an explicit endpoint, or a positional argument),
so an unrelated CLI default may legitimately disagree with a correctly
configured fork's operation target.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

GITHUB_HOST = "github.com"
SUPPORTED_SCHEMES = frozenset({"https", "http", "ssh", "git"})
SCP_LIKE = re.compile(r"^(?:(?P<user>[^@/]+)@)?(?P<host>[^:/@]+):(?P<path>.+)$")
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

# Bounded so a hung `gh` / `git` / `ssh` cannot block the lead indefinitely.
COMMAND_TIMEOUT = 30

# Never let a probe fall back to an interactive prompt. A prompt-shaped setup
# is `incomplete`, not an invitation to collect credentials through the agent.
NONINTERACTIVE_ENV_OVERRIDES = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "SSH_ASKPASS": "",
}

GITHUB_SSH_GREETING = re.compile(
    r"Hi ([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)!.*successfully authenticated",
    re.IGNORECASE | re.DOTALL,
)


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
    """Return a display-safe copy of *url* with any userinfo removed."""
    if url is None:
        return None
    text = (url or "").strip()
    if not text:
        return text

    if "://" in text:
        scheme, _, rest = text.partition("://")
        authority, _, path = rest.partition("/")
        safe_authority = authority.rsplit("@", 1)[-1]
        redacted = f"{scheme}://{safe_authority}"
        if path:
            redacted = f"{redacted}/{path}"
        return redacted

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
    configured_remote: str | None = None,
) -> dict[str, object]:
    """Decide the canonical repository, or fail closed with a named mismatch.

    `expected` is the operation's configured target from `.dev.json` (its
    `pushRepository` for a push, `pullRequestRepository` for a PR). It is not
    optional in the supported workflow -- a caller that omits it gets whatever
    the checkout happens to resolve to, with no confirmation that it is the
    intended target.

    `configured_remote` is `.dev.json`'s named `pushRemote`. When git's own
    effective push remote (`remote_name`) disagrees, that is a stop: a
    conflicting Git push-remote default (e.g. a hijacked `remote.pushDefault`)
    gets no fallback.

    The GitHub CLI default (`gh_default`) is recorded for the ledger only. It
    never fails the decision: every supported operation is explicitly scoped,
    so an unrelated CLI default may legitimately disagree with a correctly
    configured fork's operation target.
    """
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
        "notes": [],
        "reason_code": "",
        "reason": "",
    }

    if configured_remote is not None and configured_remote != remote_name:
        result["reason_code"] = "configured_remote_mismatch"
        result["reason"] = (
            f".dev.json names `{configured_remote}` as the push remote, but the "
            f"effective push remote for this checkout is `{remote_name}`; refusing "
            "to substitute one for the other"
        )
        return result

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

    # Record other GitHub remotes that disagree, but do not fail closed: the
    # push destination is already the one validated above. An unrelated
    # `upstream` on a fork (or a PR base that differs from the push target) is
    # for the ledger, not a hard stop -- explicit separate push/PR targets are
    # the supported shape, not an error.
    if conflicts:
        result["conflicting_remotes"] = sorted(conflicts)

    # Informational only. Every supported operation is explicitly scoped
    # (`--repo`, an explicit endpoint, or a positional argument), so the CLI's
    # unrelated repository default has no bearing on whether this operation is
    # safe to run, and must not block a correctly configured fork.
    if gh_default is not None:
        try:
            default = parse_owner_repo(gh_default, label="gh default repository")
        except RepositoryError:
            default = None
        if default is not None and not same_repository(default, candidate):
            result["notes"].append(
                f"the gh CLI default repository is {default}, which differs from "
                f"the operation's actual target {candidate}; not blocking, because "
                "this operation is explicitly scoped"
            )

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
    result["reason_code"] = "target_confirmed"
    result["reason"] = (
        f"effective push remote `{remote_name}` resolves to {candidate}{conflict_note}"
    )
    return result


def resolve_repository(**kwargs: object) -> dict[str, object]:
    """Decide the canonical repository and enforce the do-not-act invariant.

    `_decide_repository` has multiple failure returns. Rather than remember to
    clear the actionable field at each one, the invariant is enforced once,
    here, on the way out: a verdict whose status is not `ready` carries no
    push target. A consumer that ignores the status still cannot harvest a
    usable remote.
    """
    result = _decide_repository(**kwargs)  # type: ignore[arg-type]
    if result.get("status") != "ready":
        for actionable in ("effective_push_remote", "remote"):
            result[actionable] = None
    return result


def read_command(
    command: list[str], *, cwd: Path, merge_stderr: bool = True, env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Run one read-only command and return its exit status and stdout."""
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT,
            env=env,
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
        fetch[name] = [line.strip() for line in fetch_output.splitlines() if line.strip()] if fetch_status == 0 else []

        push_status, push_output = read_command(["git", "remote", "get-url", "--push", "--all", name], cwd=repo_dir)
        push[name] = [line.strip() for line in push_output.splitlines() if line.strip()] if push_status == 0 else []
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
        except RepositoryError:
            return None
        return first
    if status == 0:
        return None
    if status != 0 and output and ("no default" in output.lower() or "no default repository" in output.lower()):
        return None
    return None


def collect_verified_name(repo_dir: Path, repository: str) -> str | None:
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


# --- Transport account verification -----------------------------------------
#
# Bounded to the two supported transports named in the plan: an ordinary HTTPS
# credential helper, and standard OpenSSH including host aliases. Anything
# else -- a custom SSH command/variant, an HTTP auth header override, or an
# askpass fallback -- returns `unsupported_transport_auth` rather than probing
# a different, lower-precedence source and reporting on the wrong identity.
#
# No network call in this module is exercised during development or in the
# test suite: `lookup_login` is always injected by the caller (production
# wiring calls `lookup_authenticated_login_https`; tests inject a stub).


class AccountVerificationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_ssh_overrides(repo_dir: Path) -> str | None:
    """Return the name of a higher-precedence SSH command/variant override, if any."""
    for env_var in ("GIT_SSH_COMMAND", "GIT_SSH"):
        if os.environ.get(env_var):
            return env_var
    status, output = read_command(["git", "config", "core.sshCommand"], cwd=repo_dir)
    if status == 0 and output:
        return "core.sshCommand"
    if os.environ.get("GIT_SSH_VARIANT"):
        return "GIT_SSH_VARIANT"
    status, output = read_command(["git", "config", "ssh.variant"], cwd=repo_dir)
    if status == 0 and output:
        return "ssh.variant"
    return None


def detect_https_auth_overrides(repo_dir: Path, url: str) -> str | None:
    """Return the name of a higher-precedence HTTP auth override, if any.

    A separate authorization header or other URL-matched auth setting means
    the credential helper does not speak for the account Git will actually
    use; probing it anyway would attest to the wrong identity.
    """
    for key in ("http.extraHeader", f"http.{url}.extraHeader"):
        status, output = read_command(["git", "config", "--get-all", key], cwd=repo_dir)
        if status == 0 and output:
            return key
    return None


def detect_askpass_overrides() -> str | None:
    for env_var in ("GIT_ASKPASS", "SSH_ASKPASS"):
        if os.environ.get(env_var):
            return env_var
    return None


def fill_https_credential(repo_dir: Path, url: str) -> dict[str, str] | None:
    """Resolve the credential Git would use for *url* via `git credential fill`.

    Captured only in this process; the caller must never print, log, or
    persist the returned password. Returns None on any failure or missing
    field rather than raising, so an unavailable helper reads as
    `identity_unavailable`, not a traceback.
    """
    env = {**os.environ, **NONINTERACTIVE_ENV_OVERRIDES}
    try:
        completed = subprocess.run(
            ["git", "credential", "fill"],
            cwd=str(repo_dir),
            input=f"url={url}\n\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=COMMAND_TIMEOUT,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key] = value
    if "username" not in fields or "password" not in fields:
        return None
    return fields


def lookup_authenticated_login_https(credential: dict[str, str]) -> str | None:
    """Call GitHub's authenticated-user endpoint with the resolved credential.

    Production wiring only. Not called during this change's development or
    test suite -- every test injects `lookup_login`. Live evidence is a
    separate, explicitly-run step in the user's own environment.
    """
    import urllib.error
    import urllib.request

    token = f"{credential['username']}:{credential['password']}"
    basic = base64.b64encode(token.encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Basic {basic}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "dev-skill-resolve-repository",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    login = payload.get("login")
    return str(login) if isinstance(login, str) else None


def verify_https_account(
    repo_dir: Path,
    url: str,
    expected_account: str,
    *,
    lookup_login: Callable[[dict[str, str]], str | None] = lookup_authenticated_login_https,
) -> dict[str, object]:
    """Verify the account an HTTPS credential helper would present for *url*."""
    override = detect_https_auth_overrides(repo_dir, url)
    if override:
        return {
            "status": "incomplete",
            "reason_code": "unsupported_transport_auth",
            "reason": f"`{override}` overrides HTTPS authentication for this URL",
        }
    askpass_override = detect_askpass_overrides()
    if askpass_override:
        return {
            "status": "incomplete",
            "reason_code": "unsupported_transport_auth",
            "reason": f"`{askpass_override}` is set; a helper-only probe cannot be guaranteed noninteractive",
        }
    credential = fill_https_credential(repo_dir, url)
    if credential is None:
        return {
            "status": "incomplete",
            "reason_code": "identity_unavailable",
            "reason": "no credential helper resolved a credential for this URL",
        }
    login = lookup_login(credential)
    if login is None:
        return {
            "status": "incomplete",
            "reason_code": "identity_unavailable",
            "reason": "the resolved credential did not authenticate against GitHub",
        }
    if login.casefold() != expected_account.casefold():
        return {
            "status": "incomplete",
            "reason_code": "account_mismatch",
            "reason": f"authenticated as {login}, but .dev.json names {expected_account}",
        }
    return {"status": "verified", "reason_code": "account_matches", "reason": f"authenticated as {login}"}


def probe_ssh_account(
    repo_dir: Path, host: str, *, ssh_command: tuple[str, ...] = ("ssh",)
) -> tuple[int, str]:
    env = {**os.environ, **NONINTERACTIVE_ENV_OVERRIDES}
    command = [*ssh_command, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", f"git@{host}"]
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=COMMAND_TIMEOUT,
            env=env,
            check=False,
        )
    except OSError as exc:
        return (-1, str(exc))
    except subprocess.SubprocessError as exc:
        return (124, str(exc))
    return completed.returncode, completed.stdout.strip()


def verify_ssh_account(
    repo_dir: Path,
    host: str,
    expected_account: str,
    *,
    prober: Callable[[Path, str], tuple[int, str]] = probe_ssh_account,
) -> dict[str, object]:
    """Verify the account an OpenSSH probe authenticates as for *host*.

    GitHub's documented successful SSH test exits **1** with an account-bearing
    greeting; a generic zero-exit rule would misclassify both directions.
    """
    override = detect_ssh_overrides(repo_dir)
    if override:
        return {
            "status": "incomplete",
            "reason_code": "unsupported_transport_auth",
            "reason": f"`{override}` overrides the SSH transport",
        }
    status, output = prober(repo_dir, host)
    if status == -1:
        return {
            "status": "incomplete",
            "reason_code": "identity_unavailable",
            "reason": "ssh is not installed or not in PATH",
        }
    match = GITHUB_SSH_GREETING.search(output)
    if status != 1 or not match:
        return {
            "status": "incomplete",
            "reason_code": "identity_unavailable",
            "reason": "did not receive the documented GitHub SSH greeting/exit status",
        }
    login = match.group(1)
    if login.casefold() != expected_account.casefold():
        return {
            "status": "incomplete",
            "reason_code": "account_mismatch",
            "reason": f"authenticated as {login}, but .dev.json names {expected_account}",
        }
    return {"status": "verified", "reason_code": "account_matches", "reason": f"authenticated as {login}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("resolve", "check-https-account", "check-ssh-account"),
        default="resolve",
        help="'resolve' (default) decides repository identity; the check-* modes verify the transport account",
    )
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--expect", help="canonical OWNER/REPO for this operation's configured target")
    parser.add_argument("--configured-remote", help=".dev.json's pushRemote; mismatch with the effective push remote stops")
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
    parser.add_argument("--url", help="HTTPS remote URL for --mode check-https-account")
    parser.add_argument("--host", help="SSH host/alias for --mode check-ssh-account")
    parser.add_argument("--account", help="expected account for either check-*-account mode")
    return parser.parse_args()


def _run_resolve(args: argparse.Namespace) -> int:
    try:
        if args.fixture is not None:
            fixture = load_fixture(args.fixture)
            remotes = {str(k): _as_list(v) for k, v in fixture["remotes"].items()}
            push_raw = fixture.get("push_remotes")
            push_remotes = {str(k): _as_list(v) for k, v in push_raw.items()} if isinstance(push_raw, dict) else None
            raw_default = fixture.get("gh_default")
            gh_default = None if raw_default is None else str(raw_default)
            access_verified = bool(fixture.get("access_verified", False))
            raw_verified = fixture.get("verified_name")
            verified_name = None if raw_verified is None else str(raw_verified)
            remote_name = str(fixture.get("effective_push_remote", args.remote))
            configured_remote = fixture.get("configured_remote", args.configured_remote)
            configured_remote = None if configured_remote is None else str(configured_remote)
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
            configured_remote = args.configured_remote

        decision = resolve_repository(
            remotes=remotes,
            push_remotes=push_remotes,
            gh_default=gh_default,
            verified_name=verified_name,
            access_verified=access_verified,
            expected=args.expect,
            remote_name=remote_name,
            configured_remote=configured_remote,
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
            "notes": [],
            "reason_code": exc.code,
            "reason": str(exc),
        }

    ready = decision["status"] == "ready"

    if args.print_push_remote:
        if ready:
            print(decision["effective_push_remote"])
        else:
            print(decision["reason"], file=sys.stderr)
        return 0 if ready else 2

    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0 if ready else 2


def _run_check_account(args: argparse.Namespace) -> int:
    if not args.account:
        print(json.dumps({"status": "incomplete", "reason_code": "missing_argument", "reason": "--account is required"}))
        return 2
    repo_dir = args.repo_dir.resolve()
    if args.mode == "check-https-account":
        if not args.url:
            print(json.dumps({"status": "incomplete", "reason_code": "missing_argument", "reason": "--url is required"}))
            return 2
        result = verify_https_account(repo_dir, args.url, args.account)
    else:
        if not args.host:
            print(json.dumps({"status": "incomplete", "reason_code": "missing_argument", "reason": "--host is required"}))
            return 2
        result = verify_ssh_account(repo_dir, args.host, args.account)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "verified" else 2


def main() -> int:
    args = parse_args()
    if args.mode == "resolve":
        return _run_resolve(args)
    return _run_check_account(args)


if __name__ == "__main__":
    raise SystemExit(main())
