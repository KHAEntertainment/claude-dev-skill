#!/usr/bin/env python3
"""Inspect trusted external review evidence for one GitHub pull request.

The helper deliberately does not make semantic judgments about review comments.
It normalizes current-head evidence and accepts Tech Lead dispositions so the
workflow can distinguish blocking findings from advisory or false-positive
findings without relying on vendor-specific wording heuristics.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_IDENTITIES: dict[str, set[str]] = {
    "coderabbit": {
        "coderabbit",
        "coderabbitai",
        "coderabbitai[bot]",
    },
    "kilo": {
        "kilo-code",
        "kilo-code-bot",
        "kilo-code-bot[bot]",
        "kilo-code[bot]",
        "kilocode",
        "kilocode-bot",
        "kilocode-bot[bot]",
    },
    "github-copilot": {
        "copilot-pull-request-reviewer",
        "copilot-pull-request-reviewer[bot]",
    },
}

DEFAULT_CHECK_MARKERS: dict[str, set[str]] = {
    "coderabbit": {"coderabbit", "coderabbitai"},
    "kilo": {"kilo code", "kilocode", "kilo-code"},
    "github-copilot": {"copilot code review", "github copilot review"},
}

REQUEST_ALIASES: dict[str, set[str]] = {
    "github-copilot": {
        "copilot",
        "@copilot",
        "copilot-pull-request-reviewer",
        "copilot-pull-request-reviewer[bot]",
    },
}

VALID_DISPOSITIONS = {"blocking", "advisory", "false_positive"}


class InspectionError(RuntimeError):
    """Raised when GitHub evidence cannot be retrieved or decoded."""


@dataclass(frozen=True)
class ReviewerPolicy:
    identities: dict[str, set[str]]
    check_markers: dict[str, set[str]]
    required: set[str]
    ignored: set[str]


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def clip_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return nodes
    return []


def login_from(item: Any) -> str:
    if isinstance(item, str):
        return normalize(item)
    if not isinstance(item, dict):
        return ""
    for path in (
        ("login",),
        ("author", "login"),
        ("requestedReviewer", "login"),
        ("requestedReviewer", "slug"),
    ):
        candidate = nested(item, *path)
        if candidate:
            return normalize(candidate)
    return ""


def commit_oid(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for path in (("commit", "oid"), ("commit", "id"), ("originalCommit", "oid")):
        candidate = nested(item, *path)
        if candidate:
            return normalize(candidate)
    return normalize(item.get("commitOid") or item.get("headSha"))


def check_identity(check: dict[str, Any]) -> str:
    parts = [
        check.get("name"),
        check.get("context"),
        nested(check, "app", "slug"),
        nested(check, "app", "name"),
        nested(check, "workflow", "name"),
    ]
    return " ".join(normalize(part) for part in parts if part)


def looks_like_bot_login(login: str) -> bool:
    candidate = normalize(login)
    return candidate.endswith("[bot]") or candidate.endswith("-bot") or candidate.endswith("_bot")


def unknown_review_app_identity(check: dict[str, Any]) -> str:
    app_parts = [nested(check, "app", "slug"), nested(check, "app", "name")]
    app_identity = " ".join(normalize(part) for part in app_parts if part)
    if not app_identity:
        return ""
    if not any(marker in app_identity for marker in ("review", "reviewer", "bot", " ai", "ai-", "-ai")):
        return ""
    return check_identity(check)


def reviewer_for_login(login: str, policy: ReviewerPolicy, *, requested: bool = False) -> str | None:
    candidate = normalize(login)
    if not candidate:
        return None
    for reviewer, identities in policy.identities.items():
        allowed = set(identities)
        if requested:
            allowed.update(REQUEST_ALIASES.get(reviewer, set()))
        if candidate in {normalize(identity) for identity in allowed}:
            return reviewer
    return None


def reviewer_for_check(check: dict[str, Any], policy: ReviewerPolicy) -> str | None:
    identity = check_identity(check)
    for reviewer, markers in policy.check_markers.items():
        if any(normalize(marker) in identity for marker in markers):
            return reviewer
    return None


def parse_identity(
    spec: str,
    identities: dict[str, set[str]],
    check_markers: dict[str, set[str]],
) -> None:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("--identity must use reviewer=login[,login]")
    reviewer, values = spec.split("=", 1)
    reviewer = normalize(reviewer)
    aliases = {normalize(value) for value in values.split(",") if normalize(value)}
    if not reviewer or not aliases:
        raise argparse.ArgumentTypeError("--identity requires a reviewer and at least one login")
    identities.setdefault(reviewer, set()).update(aliases)
    check_markers.setdefault(reviewer, set()).update(aliases)


def run_json(command: list[str]) -> Any:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise InspectionError(f"command failed ({' '.join(command)}): {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InspectionError(f"command returned malformed JSON ({' '.join(command)}): {exc}") from exc


def fetch_threads(repo: str, pr_number: int) -> list[dict[str, Any]]:
    owner, separator, name = repo.partition("/")
    if not separator or not owner or not name:
        raise InspectionError("--repo must use OWNER/REPO")
    query = """
query($owner:String!,$repo:String!,$number:Int!,$cursor:String){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$number){
      reviewThreads(first:100,after:$cursor){
        nodes{
          id isResolved isOutdated path line
          comments(first:100){nodes{
            id body url createdAt isMinimized minimizedReason
            author{login}
            commit{oid}
            originalCommit{oid}
          }}
        }
        pageInfo{hasNextPage endCursor}
      }
    }
  }
}
""".strip()
    cursor = ""
    threads: list[dict[str, Any]] = []
    while True:
        command = [
            "rtk",
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={name}",
            "-F",
            f"number={pr_number}",
        ]
        if cursor:
            command.extend(["-f", f"cursor={cursor}"])
        response = run_json(command)
        connection = nested(response, "data", "repository", "pullRequest", "reviewThreads")
        if not isinstance(connection, dict):
            raise InspectionError("GitHub GraphQL response omitted pullRequest.reviewThreads")
        threads.extend(node for node in list_value(connection) if isinstance(node, dict))
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = str(page_info.get("endCursor") or "")
        if not cursor:
            raise InspectionError("GitHub reported another review-thread page without an end cursor")
    return threads


def fetch_pr(repo: str, pr_number: int) -> dict[str, Any]:
    value = run_json(
        [
            "rtk",
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "number,headRefOid,reviewRequests,reviews,latestReviews,statusCheckRollup,comments",
        ]
    )
    if not isinstance(value, dict):
        raise InspectionError("gh pr view did not return an object")
    return value


def fetch_recent(repo: str, current_pr: int, limit: int) -> list[dict[str, Any]]:
    if limit == 0:
        return []
    summaries = run_json(
        [
            "rtk",
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            str(limit + 1),
            "--json",
            "number",
        ]
    )
    recent: list[dict[str, Any]] = []
    for summary in list_value(summaries):
        number = summary.get("number") if isinstance(summary, dict) else None
        if not isinstance(number, int) or number == current_pr:
            continue
        recent.append(fetch_pr(repo, number))
        if len(recent) >= limit:
            break
    return recent


def load_fixture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectionError(f"cannot read fixture {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise InspectionError("fixture must contain a current PR object")
    threads: list[dict[str, Any]] = []
    raw_threads = payload.get("threads", [])
    if isinstance(raw_threads, list):
        for page in raw_threads:
            if isinstance(page, dict) and "nodes" in page:
                threads.extend(node for node in list_value(page) if isinstance(node, dict))
            elif isinstance(page, dict):
                threads.append(page)
    recent = [item for item in payload.get("recent", []) if isinstance(item, dict)]
    return payload["current"], threads, recent


def iter_reviews(pr: dict[str, Any]) -> Iterable[dict[str, Any]]:
    seen: set[str] = set()
    for key in ("latestReviews", "reviews"):
        for review in list_value(pr.get(key)):
            if not isinstance(review, dict):
                continue
            fallback = f"{login_from(review)}:{review.get('submittedAt')}:{review.get('body')}"
            identifier = str(review.get("id") or fallback)
            if identifier in seen:
                continue
            seen.add(identifier)
            yield review


def observed_in_pr(pr: dict[str, Any], policy: ReviewerPolicy) -> set[str]:
    observed: set[str] = set()
    for review in iter_reviews(pr):
        reviewer = reviewer_for_login(login_from(review), policy)
        if reviewer:
            observed.add(reviewer)
    for comment in list_value(pr.get("comments")):
        reviewer = reviewer_for_login(login_from(comment), policy)
        if reviewer:
            observed.add(reviewer)
    for request in list_value(pr.get("reviewRequests")):
        reviewer = reviewer_for_login(login_from(request), policy, requested=True)
        if reviewer:
            observed.add(reviewer)
    for check in list_value(pr.get("statusCheckRollup")):
        if isinstance(check, dict):
            reviewer = reviewer_for_check(check, policy)
            if reviewer:
                observed.add(reviewer)
    return observed


def inspect(
    current: dict[str, Any],
    threads: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    policy: ReviewerPolicy,
    dispositions: dict[str, str],
    max_body_chars: int = 2000,
) -> dict[str, Any]:
    head_oid = normalize(current.get("headRefOid"))
    errors: list[str] = []
    if not head_oid:
        errors.append("current PR is missing headRefOid")

    current_observed = observed_in_pr(current, policy)
    recent_observed: set[str] = set()
    for pr in recent:
        recent_observed.update(observed_in_pr(pr, policy))

    requested: set[str] = set()
    for request in list_value(current.get("reviewRequests")):
        reviewer = reviewer_for_login(login_from(request), policy, requested=True)
        if reviewer:
            requested.add(reviewer)

    thread_findings: list[dict[str, Any]] = []
    thread_reviewers: set[str] = set()
    completed_on_head: set[str] = set()
    for thread in threads:
        comments = [item for item in list_value(thread.get("comments")) if isinstance(item, dict)]
        trusted_comments: list[tuple[str, dict[str, Any]]] = []
        for comment in comments:
            reviewer = reviewer_for_login(login_from(comment), policy)
            if reviewer:
                trusted_comments.append((reviewer, comment))
                thread_reviewers.add(reviewer)
                if head_oid and commit_oid(comment) == head_oid:
                    completed_on_head.add(reviewer)
        if not trusted_comments:
            continue
        reviewer, latest = trusted_comments[-1]
        finding_id = str(thread.get("id") or latest.get("id") or latest.get("url") or "unknown")
        resolved = bool(thread.get("isResolved"))
        outdated = bool(thread.get("isOutdated"))
        minimized = bool(latest.get("isMinimized"))
        current_head = bool(head_oid and commit_oid(latest) == head_oid)
        active = not resolved and not outdated and not minimized and current_head
        disposition = dispositions.get(finding_id)
        if disposition and disposition not in VALID_DISPOSITIONS:
            errors.append(f"invalid disposition for {finding_id}: {disposition}")
        thread_findings.append(
            {
                "id": finding_id,
                "reviewer": reviewer,
                "body": clip_text(latest.get("body"), max_body_chars) if active else "",
                "url": str(latest.get("url") or ""),
                "path": str(thread.get("path") or ""),
                "line": thread.get("line"),
                "resolved": resolved,
                "outdated": outdated,
                "minimized": minimized,
                "current_head": current_head,
                "active": active,
                "disposition": disposition,
            }
        )

    current_observed.update(thread_reviewers)
    expected = (set(policy.required) | current_observed | recent_observed) - policy.ignored
    current_observed -= policy.ignored
    requested -= policy.ignored

    check_pending: set[str] = set()
    check_failed: set[str] = set()
    check_complete: set[str] = set()
    for check in list_value(current.get("statusCheckRollup")):
        if not isinstance(check, dict):
            continue
        reviewer = reviewer_for_check(check, policy)
        if not reviewer or reviewer in policy.ignored:
            continue
        status = normalize(check.get("status") or check.get("state"))
        conclusion = normalize(check.get("conclusion"))
        if status in {"queued", "pending", "in_progress", "requested", "waiting"}:
            check_pending.add(reviewer)
        elif conclusion in {"failure", "cancelled", "timed_out", "action_required", "startup_failure"} or status in {
            "failure",
            "error",
        }:
            check_failed.add(reviewer)
        elif conclusion in {"success", "neutral", "skipped"} or status in {"success", "completed"}:
            check_complete.add(reviewer)
            completed_on_head.add(reviewer)

    stale_reviewers: set[str] = set()
    for review in iter_reviews(current):
        reviewer = reviewer_for_login(login_from(review), policy)
        if not reviewer or reviewer in policy.ignored:
            continue
        oid = commit_oid(review)
        if oid and head_oid and oid == head_oid:
            completed_on_head.add(reviewer)
        elif oid and head_oid and oid != head_oid:
            stale_reviewers.add(reviewer)
    stale_reviewers -= completed_on_head

    active_findings = [finding for finding in thread_findings if finding["active"]]
    blocking = [finding for finding in active_findings if finding["disposition"] == "blocking"]
    untriaged = [finding for finding in active_findings if not finding["disposition"]]
    readable_by_reviewer = {finding["reviewer"] for finding in active_findings}
    unreadable_failed_checks = sorted(check_failed - readable_by_reviewer)
    if unreadable_failed_checks:
        errors.append(
            "trusted review check failed without readable current-head findings: "
            + ", ".join(unreadable_failed_checks)
        )

    untriaged_reviewers = {finding["reviewer"] for finding in untriaged}
    pending_reviewers = set(check_pending) | requested | stale_reviewers
    pending_reviewers.update(expected - completed_on_head)
    pending_reviewers.update(untriaged_reviewers)
    pending_reviewers -= check_complete - stale_reviewers - requested - check_pending - untriaged_reviewers

    known_logins = {
        normalize(identity)
        for identities in (*DEFAULT_IDENTITIES.values(), *policy.identities.values())
        for identity in identities
    }
    default_policy = ReviewerPolicy(
        identities=DEFAULT_IDENTITIES,
        check_markers=DEFAULT_CHECK_MARKERS,
        required=set(),
        ignored=set(),
    )
    unknown_bots: set[str] = set()
    for collection in (current.get("reviews"), current.get("latestReviews"), current.get("comments")):
        for item in list_value(collection):
            login = login_from(item)
            if login and login not in known_logins and looks_like_bot_login(login):
                unknown_bots.add(login)
    for check in list_value(current.get("statusCheckRollup")):
        if (
            not isinstance(check, dict)
            or reviewer_for_check(check, policy)
            or reviewer_for_check(check, default_policy)
        ):
            continue
        identity = unknown_review_app_identity(check)
        if identity:
            unknown_bots.add(identity)

    if errors:
        state = "incomplete"
    elif blocking:
        state = "blocking"
    elif not expected:
        state = "not_applicable"
    elif pending_reviewers or untriaged:
        state = "pending"
    else:
        state = "clear"

    return {
        "state": state,
        "pr_number": current.get("number"),
        "head_oid": head_oid,
        "expected_reviewers": sorted(expected),
        "observed_reviewers": sorted(current_observed),
        "recently_observed_reviewers": sorted(recent_observed),
        "requested_reviewers": sorted(requested),
        "completed_on_head": sorted(completed_on_head),
        "pending_reviewers": sorted(pending_reviewers),
        "stale_reviewers": sorted(stale_reviewers),
        "findings": thread_findings,
        "blocking_findings": blocking,
        "untriaged_findings": untriaged,
        "unknown_bot_identities": sorted(unknown_bots),
        "errors": errors,
    }


def load_dispositions(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectionError(f"cannot read dispositions {path}: {exc}") from exc
    valid_mapping = isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )
    if not valid_mapping:
        raise InspectionError("dispositions must be a JSON object mapping finding IDs to strings")
    return {key: normalize(item) for key, item in value.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="read deterministic GitHub-shaped fixture data")
    source.add_argument("--repo", help="GitHub repository in OWNER/REPO form")
    parser.add_argument("--pr", type=int, help="pull request number (required with --repo)")
    parser.add_argument("--recent-pr-limit", type=int, default=5)
    parser.add_argument("--max-body-chars", type=int, default=2000)
    parser.add_argument(
        "--trusted-reviewer",
        action="append",
        default=[],
        help="restrict trust to the repeated canonical reviewer names; defaults to all built-ins",
    )
    parser.add_argument("--required-reviewer", action="append", default=[])
    parser.add_argument("--ignored-reviewer", action="append", default=[])
    parser.add_argument("--identity", action="append", default=[], metavar="REVIEWER=LOGIN[,LOGIN]")
    parser.add_argument("--dispositions", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repo and not args.pr:
        print("ERROR: --pr is required with --repo", file=sys.stderr)
        return 2
    if args.recent_pr_limit < 0 or args.recent_pr_limit > 20:
        print("ERROR: --recent-pr-limit must be between 0 and 20", file=sys.stderr)
        return 2
    if args.max_body_chars < 200 or args.max_body_chars > 20000:
        print("ERROR: --max-body-chars must be between 200 and 20000", file=sys.stderr)
        return 2

    identities = {reviewer: set(values) for reviewer, values in DEFAULT_IDENTITIES.items()}
    check_markers = {reviewer: set(values) for reviewer, values in DEFAULT_CHECK_MARKERS.items()}
    try:
        for spec in args.identity:
            parse_identity(spec, identities, check_markers)
        trusted = {normalize(value) for value in args.trusted_reviewer}
        if trusted:
            unknown = trusted - identities.keys()
            if unknown:
                raise InspectionError("trusted reviewer has no identity mapping: " + ", ".join(sorted(unknown)))
            identities = {reviewer: values for reviewer, values in identities.items() if reviewer in trusted}
            check_markers = {
                reviewer: values for reviewer, values in check_markers.items() if reviewer in trusted
            }
        required = {normalize(value) for value in args.required_reviewer}
        untrusted_required = required - identities.keys()
        if untrusted_required:
            raise InspectionError(
                "required reviewer is not trusted or has no identity mapping: "
                + ", ".join(sorted(untrusted_required))
            )
        policy = ReviewerPolicy(
            identities=identities,
            check_markers=check_markers,
            required=required,
            ignored={normalize(value) for value in args.ignored_reviewer},
        )
        dispositions = load_dispositions(args.dispositions)
        if args.fixture:
            current, threads, recent = load_fixture(args.fixture)
        else:
            current = fetch_pr(args.repo, args.pr)
            threads = fetch_threads(args.repo, args.pr)
            recent = fetch_recent(args.repo, args.pr, args.recent_pr_limit)
        result = inspect(
            current,
            threads,
            recent,
            policy,
            dispositions,
            max_body_chars=args.max_body_chars,
        )
    except (InspectionError, argparse.ArgumentTypeError) as exc:
        result = {
            "state": "incomplete",
            "errors": [str(exc)],
        }
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if result["state"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
