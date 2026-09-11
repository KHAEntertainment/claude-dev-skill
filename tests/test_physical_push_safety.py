"""Physical proof of the writer-call-site pattern every `/dev` push must follow:
never push on a verdict that is not `ready`, and only ever push through the
remote name and refspec the resolver itself validated -- including the
branch/refspec dry-run check (finding 3 of the independent review).

Two real local bare repositories stand in for the intended and wrong-target
destinations. This is deliberately not a simulation of a hostile transport --
it asserts the ordinary case (a legitimate push reaches only its intended
target) and the guarded cases (a hijacked push-remote default, and a wrong
current branch, each leave both repositories' refs untouched), using real
`git push` and `git push --dry-run` calls.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from unittest.mock import patch

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "skills" / "dev" / "scripts" / "resolve_repository.py"
SPEC = importlib.util.spec_from_file_location("resolve_repository", RESOLVER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANONICAL = "KHAEntertainment/claude-dev-skill"
ORIGIN_HTTPS = "https://github.com/KHAEntertainment/claude-dev-skill.git"
UPSTREAM_HTTPS = "https://github.com/hnaymyh123-henry/claude-dev-skill.git"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _rev(bare: Path, ref: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True, text=True,
    )
    return completed.stdout.strip() or None


def _gated_push(clone: Path, verdict: dict[str, object]) -> bool:
    """The pattern every writer call site must follow: test the exit code
    before invoking the real command, and use only the remote name the
    resolver validated -- never a default the check just rejected."""
    if verdict.get("status") != "ready":
        return False
    remote = verdict.get("effective_push_remote")
    refspec = verdict.get("dry_run", {}).get("refspec")
    if not remote or not refspec or verdict["dry_run"].get("remote") != remote:
        return False
    _git("push", "-q", str(remote), str(refspec), cwd=clone)
    return True


def _production_verdict(clone, *, remotes=None, push_remotes=None,
                        expected=CANONICAL, remote_name="origin", configured_remote="origin",
                        gh_default=None, assigned_branch="feature", dest_ref=None):
    """Exercise the CLI with real config, branch checks and local dry-run.

    Inject only remote URL observations and GitHub account/access boundaries:
    the local bare repositories stand in for the named GitHub repositories.
    Git remote selection and the actual dry-run/push remain real.
    """
    config = MODULE.dev_config.build_config(
        host="github.com", account="KHAEntertainment", push_repository=expected,
        pull_request_repository=expected, push_remote=configured_remote)
    path = clone / ".dev.json"
    MODULE.dev_config.create_config(path, config)
    MODULE.dev_config.ensure_excluded(clone)
    _git("config", "remote.pushDefault", remote_name, cwd=clone)
    remotes = remotes or {"origin": ORIGIN_HTTPS}
    output = io.StringIO()
    argv = ["resolver", "--repo-dir", str(clone), "--assigned-branch", assigned_branch]
    if dest_ref:
        argv += ["--dest-ref", dest_ref]
    with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output), \
            patch.object(MODULE, "collect_remotes", return_value=(remotes, push_remotes or {})), \
            patch.object(MODULE, "collect_gh_default", return_value=gh_default), \
            patch.object(MODULE, "collect_verified_name", return_value=CANONICAL), \
            patch.object(MODULE, "verify_https_account", return_value={"status": "verified"}):
        code = MODULE.main()
    verdict = json.loads(output.getvalue())
    assert (code == 0) == (verdict["status"] == "ready")
    return verdict


class PhysicalPushSafetyTests(unittest.TestCase):
    def _make_bare(self, root: Path, name: str) -> Path:
        bare = root / name
        _git("init", "--bare", "-q", str(bare), cwd=root)
        return bare

    def _make_clone_with_commit(self, root: Path, origin_bare: Path, branch: str = "main") -> Path:
        clone = root / "work"
        _git("clone", "-q", str(origin_bare), str(clone), cwd=root)
        _git("config", "user.email", "test@example.com", cwd=clone)
        _git("config", "user.name", "Test", cwd=clone)
        _git("checkout", "-q", "-B", branch, cwd=clone)
        (clone / "README.md").write_text("hello\n", encoding="utf-8")
        _git("add", "README.md", cwd=clone)
        _git("commit", "-q", "-m", "initial", cwd=clone)
        _git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=clone)
        if branch == "main":
            _git("checkout", "-q", "-b", "feature", cwd=clone)
        return clone

    def _add_feature_commit(self, clone: Path) -> None:
        (clone / "feature.txt").write_text("change\n", encoding="utf-8")
        _git("add", "feature.txt", cwd=clone)
        _git("commit", "-q", "-m", "feature", cwd=clone)

    def test_ready_verdict_pushes_only_the_intended_remote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "add", "upstream", str(wrong), cwd=clone)

            self._add_feature_commit(clone)
            verdict = _production_verdict(
                clone,
                remotes={"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                push_remotes=None,
                gh_default=None,
                expected=CANONICAL,
                remote_name="origin",
                configured_remote="origin",
            )
            self.assertEqual("ready", verdict["status"])

            pushed = _gated_push(clone, verdict)

            self.assertTrue(pushed)
            self.assertIsNotNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_configured_remote_mismatch_leaves_both_remotes_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "add", "upstream", str(wrong), cwd=clone)

            self._add_feature_commit(clone)
            verdict = _production_verdict(
                clone,
                remotes={"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                push_remotes=None,
                gh_default=None,
                expected=CANONICAL,
                remote_name="upstream",
                configured_remote="origin",
            )
            self.assertEqual("incomplete", verdict["status"])
            self.assertEqual("configured_remote_mismatch", verdict["reason_code"])
            self.assertIsNone(verdict["effective_push_remote"])

            pushed = _gated_push(clone, verdict)

            self.assertFalse(pushed)
            self.assertIsNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_expected_mismatch_leaves_both_remotes_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "add", "upstream", str(wrong), cwd=clone)

            self._add_feature_commit(clone)
            verdict = _production_verdict(
                clone,
                remotes={"origin": ORIGIN_HTTPS},
                push_remotes=None,
                gh_default=None,
                expected="hnaymyh123-henry/claude-dev-skill",
                remote_name="origin",
                configured_remote="origin",
            )
            self.assertEqual("incomplete", verdict["status"])
            self.assertEqual("expected_mismatch", verdict["reason_code"])

            pushed = _gated_push(clone, verdict)

            self.assertFalse(pushed)
            self.assertIsNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_split_fetch_upstream_push_fork_physically_pushes_only_the_fork(self) -> None:
        """Finding 2's supported shape, proven physically: fetch points at
        `wrong.git` (standing in for upstream), push points at
        `intended.git` (the fork). The verdict must be `ready`, and the real
        push must reach only `intended.git`."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "set-url", "origin", str(wrong), cwd=clone)
            _git("remote", "set-url", "--push", "origin", str(intended), cwd=clone)

            self._add_feature_commit(clone)
            verdict = _production_verdict(
                clone,
                remotes={"origin": UPSTREAM_HTTPS},
                push_remotes={"origin": [ORIGIN_HTTPS]},
                gh_default=None,
                expected=CANONICAL,
                remote_name="origin",
                configured_remote="origin",
            )
            self.assertEqual("ready", verdict["status"])

            pushed = _gated_push(clone, verdict)

            self.assertTrue(pushed)
            self.assertIsNotNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_dry_run_on_wrong_branch_fails_before_any_push_reproduction(self) -> None:
        """Finding 3 reproduction, at the physical level: the checkout is on
        the wrong branch relative to the ledger assignment. The branch check
        must stop before the dry run (and therefore before any real push) is
        ever attempted, leaving the bare repository's ref untouched."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            clone = self._make_clone_with_commit(root, intended, branch="main")
            _git("checkout", "-q", "-B", "wrong-branch", cwd=clone)
            self._add_feature_commit(clone)

            result = _production_verdict(
                clone, assigned_branch="feature/expected"
            )
            self.assertEqual("incomplete", result["status"])
            self.assertEqual("branch_mismatch", result["reason_code"])
            self.assertIsNone(_rev(intended, "refs/heads/feature/expected"))

    def test_dry_run_on_correct_branch_succeeds_without_advancing_refs(self) -> None:
        """A real `git push --dry-run` against a real bare repository: it
        reports success but never actually creates the ref."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            clone = self._make_clone_with_commit(root, intended, branch="feature/expected")
            # The initial commit is already on the bare repo from the clone
            # setup's own push; capture that baseline before the local-only
            # feature commit, so "unchanged" means "still at the baseline",
            # not merely "some ref exists".
            baseline = _rev(intended, "refs/heads/feature/expected")
            self._add_feature_commit(clone)

            result = _production_verdict(
                clone, assigned_branch="feature/expected"
            )
            self.assertEqual("ready", result["status"])
            self.assertEqual(
                baseline,
                _rev(intended, "refs/heads/feature/expected"),
                "a dry run must never advance the real ref",
            )

            # Only now does the gated pattern perform the real push.
            self.assertTrue(_gated_push(clone, result))
            self.assertNotEqual(baseline, _rev(intended, "refs/heads/feature/expected"))

    def test_feature_to_main_is_rejected_without_advancing_either_repo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            before = _rev(intended, "refs/heads/main")
            _git("checkout", "-q", "-b", "task/expected", cwd=clone)
            self._add_feature_commit(clone)
            verdict = _production_verdict(
                clone, assigned_branch="task/expected", dest_ref="refs/heads/main")
            self.assertEqual("destination_mismatch", verdict["reason_code"])
            self.assertFalse(_gated_push(clone, verdict))
            self.assertEqual(before, _rev(intended, "refs/heads/main"))
            self.assertIsNone(_rev(intended, "refs/heads/task/expected"))
            self.assertIsNone(_rev(wrong, "refs/heads/main"))


if __name__ == "__main__":
    unittest.main()
