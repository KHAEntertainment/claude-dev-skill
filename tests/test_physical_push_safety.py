"""Physical proof of the writer-call-site pattern every `/dev` push must follow:
never push on a verdict that is not `ready`, and only ever push through the
remote name the resolver itself validated.

Two real local bare repositories stand in for the intended and wrong-target
destinations. This is deliberately not a simulation of a hostile transport --
it asserts the ordinary case (a legitimate push reaches only its intended
target) and the guarded case (a hijacked push-remote default leaves both
repositories' refs untouched), using real `git push` calls.
"""

from __future__ import annotations

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


def _gated_push(clone: Path, verdict: dict[str, object], branch: str) -> bool:
    """The pattern every writer call site must follow: test the exit code
    before invoking the real command, and use only the remote name the
    resolver validated -- never a default the check just rejected."""
    if verdict.get("status") != "ready":
        return False
    remote = verdict.get("effective_push_remote")
    if not remote:
        return False
    _git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=clone)
    return True


class PhysicalPushSafetyTests(unittest.TestCase):
    def _make_bare(self, root: Path, name: str) -> Path:
        bare = root / name
        _git("init", "--bare", "-q", str(bare), cwd=root)
        return bare

    def _make_clone_with_commit(self, root: Path, origin_bare: Path) -> Path:
        clone = root / "work"
        _git("clone", "-q", str(origin_bare), str(clone), cwd=root)
        _git("config", "user.email", "test@example.com", cwd=clone)
        _git("config", "user.name", "Test", cwd=clone)
        (clone / "README.md").write_text("hello\n", encoding="utf-8")
        _git("add", "README.md", cwd=clone)
        _git("commit", "-q", "-m", "initial", cwd=clone)
        _git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=clone)
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

            verdict = MODULE.resolve_repository(
                remotes={"origin": ORIGIN_HTTPS, "upstream": UPSTREAM_HTTPS},
                push_remotes=None,
                gh_default=None,
                expected=CANONICAL,
                remote_name="origin",
                configured_remote="origin",
            )
            self.assertEqual("ready", verdict["status"])

            self._add_feature_commit(clone)
            pushed = _gated_push(clone, verdict, "feature")

            self.assertTrue(pushed)
            self.assertIsNotNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_configured_remote_mismatch_leaves_both_remotes_untouched(self) -> None:
        """A hijacked `remote.pushDefault` would have git push to `upstream`
        (the wrong target). `.dev.json` names `origin`; the mismatch must stop
        the push before either bare repository's refs change."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "add", "upstream", str(wrong), cwd=clone)

            verdict = MODULE.resolve_repository(
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

            self._add_feature_commit(clone)
            pushed = _gated_push(clone, verdict, "feature")

            self.assertFalse(pushed)
            self.assertIsNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))

    def test_expected_mismatch_leaves_both_remotes_untouched(self) -> None:
        """A worktree assigned to a different repository than `.dev.json`
        confirms (`--expect`) must also refuse to push, even when the local
        Git remotes themselves are internally consistent."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intended = self._make_bare(root, "intended.git")
            wrong = self._make_bare(root, "wrong.git")
            clone = self._make_clone_with_commit(root, intended)
            _git("remote", "add", "upstream", str(wrong), cwd=clone)

            verdict = MODULE.resolve_repository(
                remotes={"origin": ORIGIN_HTTPS},
                push_remotes=None,
                gh_default=None,
                expected="hnaymyh123-henry/claude-dev-skill",
                remote_name="origin",
                configured_remote="origin",
            )
            self.assertEqual("incomplete", verdict["status"])
            self.assertEqual("expected_mismatch", verdict["reason_code"])

            self._add_feature_commit(clone)
            pushed = _gated_push(clone, verdict, "feature")

            self.assertFalse(pushed)
            self.assertIsNone(_rev(intended, "refs/heads/feature"))
            self.assertIsNone(_rev(wrong, "refs/heads/feature"))


if __name__ == "__main__":
    unittest.main()
