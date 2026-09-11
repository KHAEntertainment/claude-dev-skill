from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "dev" / "scripts" / "dev_config.py"
SPEC = importlib.util.spec_from_file_location("dev_config", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


VALID_DOC = {
    "version": 1,
    "github": {
        "host": "github.com",
        "account": "KHAEntertainment",
        "pushRepository": "KHAEntertainment/claude-dev-skill",
        "pullRequestRepository": "KHAEntertainment/claude-dev-skill",
        "pushRemote": "origin",
    },
}


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=check, capture_output=True, text=True
    )


class SchemaValidationTests(unittest.TestCase):
    def test_valid_document_round_trips(self) -> None:
        parsed = MODULE.parse_config(json.dumps(VALID_DOC))
        self.assertEqual(VALID_DOC, parsed)

    def test_missing_version_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        del doc["version"]
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("missing_field", caught.exception.code)

    def test_unknown_version_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["version"] = 2
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("unsupported_version", caught.exception.code)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["extra"] = "nope"
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("unknown_field", caught.exception.code)

    def test_unknown_github_field_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["workType"] = "independent-fork"
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("unknown_field", caught.exception.code)

    def test_missing_required_github_field_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        del doc["github"]["pullRequestRepository"]
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("missing_field", caught.exception.code)

    def test_empty_field_values_are_rejected(self) -> None:
        for field in ("host", "account", "pushRepository", "pullRequestRepository", "pushRemote"):
            with self.subTest(field=field):
                doc = json.loads(json.dumps(VALID_DOC))
                doc["github"][field] = ""
                with self.assertRaises(MODULE.ConfigError):
                    MODULE.parse_config(json.dumps(doc))

    def test_malformed_repository_identifier_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["pushRepository"] = "not-owner-slash-repo-format/../x"
        with self.assertRaises(MODULE.ConfigError):
            MODULE.parse_config(json.dumps(doc))

    def test_unsupported_host_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["host"] = "gitlab.com"
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("unsupported_host", caught.exception.code)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        raw = (
            '{"version": 1, "github": {"host": "github.com", "account": "a", '
            '"pushRepository": "a/b", "pullRequestRepository": "a/b", '
            '"pushRemote": "origin", "pushRemote": "upstream"}}'
        )
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(raw)
        self.assertEqual("duplicate_key", caught.exception.code)

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config("{not json")
        self.assertEqual("malformed_json", caught.exception.code)

    def test_token_like_field_is_rejected_even_if_shaped_like_a_valid_value(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["token"] = "ghp_doesnotmatter"
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("unknown_field", caught.exception.code)

    def test_repository_value_with_userinfo_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["pushRepository"] = "https://token@github.com/KHAEntertainment/claude-dev-skill"
        with self.assertRaises(MODULE.ConfigError) as caught:
            MODULE.parse_config(json.dumps(doc))
        self.assertEqual("credential_bearing_value", caught.exception.code)

    def test_account_with_userinfo_is_rejected(self) -> None:
        doc = json.loads(json.dumps(VALID_DOC))
        doc["github"]["account"] = "user@host"
        with self.assertRaises(MODULE.ConfigError):
            MODULE.parse_config(json.dumps(doc))

    def test_build_config_matches_parse_config(self) -> None:
        built = MODULE.build_config(
            host="github.com",
            account="KHAEntertainment",
            push_repository="KHAEntertainment/claude-dev-skill",
            pull_request_repository="KHAEntertainment/claude-dev-skill",
            push_remote="origin",
        )
        self.assertEqual(VALID_DOC, built)


class ProvenanceAndPersistenceTests(unittest.TestCase):
    def _init_repo(self, root: Path) -> None:
        _git("init", "-q", cwd=root)
        _git("config", "user.email", "test@example.com", cwd=root)
        _git("config", "user.name", "Test", cwd=root)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        _git("add", "README.md", cwd=root)
        _git("commit", "-q", "-m", "initial", cwd=root)

    def test_tracked_config_is_detected_and_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            config_path = root / MODULE.CONFIG_FILENAME
            config_path.write_text(json.dumps(VALID_DOC), encoding="utf-8")
            _git("add", MODULE.CONFIG_FILENAME, cwd=root)
            _git("commit", "-q", "-m", "add config", cwd=root)

            result = MODULE.resolve_status(config_path)
            self.assertEqual("tracked", result["status"])
            self.assertEqual("tracked_config", result["reason_code"])
            self.assertIsNone(result["config"])

    def test_missing_config_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            result = MODULE.resolve_status(root / MODULE.CONFIG_FILENAME)
            self.assertEqual("missing", result["status"])

    def test_invalid_config_is_reported_and_never_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            config_path = root / MODULE.CONFIG_FILENAME
            original_text = '{"version": 1, "github": {"host": "github.com"}}'
            config_path.write_text(original_text, encoding="utf-8")

            result = MODULE.resolve_status(config_path)
            self.assertEqual("invalid", result["status"])
            self.assertEqual("missing_field", result["reason_code"])
            self.assertEqual(original_text, config_path.read_text(encoding="utf-8"))

    def test_untracked_unignored_valid_config_is_flagged_not_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            config_path = root / MODULE.CONFIG_FILENAME
            config_path.write_text(json.dumps(VALID_DOC), encoding="utf-8")

            result = MODULE.resolve_status(config_path)
            self.assertEqual("not_ignored", result["status"])
            self.assertIsNotNone(result["config"])

    def test_ensure_excluded_then_status_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            config_path = root / MODULE.CONFIG_FILENAME
            config_path.write_text(json.dumps(VALID_DOC), encoding="utf-8")

            ignored = MODULE.ensure_excluded(root)
            self.assertTrue(ignored)

            result = MODULE.resolve_status(config_path)
            self.assertEqual("valid", result["status"])
            self.assertEqual(VALID_DOC, result["config"])

    def test_ensure_excluded_is_idempotent_and_never_touches_global_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            self.assertTrue(MODULE.ensure_excluded(root))
            self.assertTrue(MODULE.ensure_excluded(root))
            exclude_status = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=str(root), capture_output=True, text=True,
            )
            resolved = Path(exclude_status.stdout.strip())
            if not resolved.is_absolute():
                resolved = (root / resolved).resolve()
            contents = resolved.read_text(encoding="utf-8")
            self.assertEqual(1, contents.count(MODULE.CONFIG_FILENAME))

    def test_create_config_refuses_to_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / MODULE.CONFIG_FILENAME
            config_path.write_text("{}", encoding="utf-8")
            with self.assertRaises(MODULE.ConfigError) as caught:
                MODULE.create_config(config_path, VALID_DOC)
            self.assertEqual("already_exists", caught.exception.code)
            self.assertEqual("{}", config_path.read_text(encoding="utf-8"))

    def test_create_config_then_reload_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            config_path = root / MODULE.CONFIG_FILENAME
            MODULE.create_config(config_path, VALID_DOC)
            MODULE.ensure_excluded(root)

            result = MODULE.resolve_status(config_path)
            self.assertEqual("valid", result["status"])
            self.assertEqual(VALID_DOC, result["config"])

    def test_pre_git_project_root_validates_without_provenance_checks(self) -> None:
        """Before Git exists, an explicitly selected project root's file is
        still validated -- there is simply no tracked/ignored check yet."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / MODULE.CONFIG_FILENAME
            MODULE.create_config(config_path, VALID_DOC)

            result = MODULE.resolve_status(config_path)
            self.assertEqual("valid", result["status"])
            self.assertEqual(VALID_DOC, result["config"])


class CommandLineTests(unittest.TestCase):
    def test_create_then_status_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git("init", "-q", cwd=root)
            _git("config", "user.email", "test@example.com", cwd=root)
            _git("config", "user.name", "Test", cwd=root)
            (root / "README.md").write_text("hello\n", encoding="utf-8")
            _git("add", "README.md", cwd=root)
            _git("commit", "-q", "-m", "initial", cwd=root)

            create = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "create",
                    "--path", str(root / MODULE.CONFIG_FILENAME),
                    "--account", "KHAEntertainment",
                    "--push-repository", "KHAEntertainment/claude-dev-skill",
                    "--pull-request-repository", "KHAEntertainment/claude-dev-skill",
                    "--push-remote", "origin",
                ],
                capture_output=True, text=True, cwd=str(root),
            )
            self.assertEqual(0, create.returncode, create.stdout + create.stderr)
            payload = json.loads(create.stdout)
            self.assertEqual("created", payload["status"])
            self.assertTrue(payload["ignored"])

            status = subprocess.run(
                [sys.executable, str(SCRIPT), "status", "--path", str(root / MODULE.CONFIG_FILENAME)],
                capture_output=True, text=True, cwd=str(root),
            )
            self.assertEqual(0, status.returncode, status.stdout + status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual("valid", status_payload["status"])

    def test_create_refuses_when_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git("init", "-q", cwd=root)
            _git("config", "user.email", "test@example.com", cwd=root)
            _git("config", "user.name", "Test", cwd=root)
            config_path = root / MODULE.CONFIG_FILENAME
            config_path.write_text(json.dumps(VALID_DOC), encoding="utf-8")
            _git("add", MODULE.CONFIG_FILENAME, cwd=root)
            _git("commit", "-q", "-m", "add config", cwd=root)
            config_path.unlink()

            create = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "create",
                    "--path", str(config_path),
                    "--account", "KHAEntertainment",
                    "--push-repository", "KHAEntertainment/claude-dev-skill",
                    "--pull-request-repository", "KHAEntertainment/claude-dev-skill",
                ],
                capture_output=True, text=True, cwd=str(root),
            )
            self.assertEqual(2, create.returncode)
            payload = json.loads(create.stdout)
            self.assertEqual("tracked_config", payload["reason_code"])


if __name__ == "__main__":
    unittest.main()
