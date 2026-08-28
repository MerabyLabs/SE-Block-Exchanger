import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from update_checker import UpdateChecker


class TestUpdateChecker(unittest.TestCase):
    def test_uses_cache_and_detects_newer_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            payload = {
                "tag_name": "v99.0.0",
                "html_url": "https://example.com/release",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "release notes",
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_path.write_text(json.dumps(payload), encoding="utf-8")

            checker = UpdateChecker(cache_path=cache_path, cache_hours=24)
            info = checker.check_for_updates(force=False)
            self.assertTrue(info.available)
            self.assertEqual(info.latest_version, "99.0.0")
            self.assertEqual(info.release_url, "https://example.com/release")

    def test_cache_version_not_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            payload = {
                "tag_name": "v0.0.1",
                "html_url": "https://example.com/release",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "release notes",
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_path.write_text(json.dumps(payload), encoding="utf-8")

            checker = UpdateChecker(cache_path=cache_path, cache_hours=24)
            info = checker.check_for_updates(force=False)
            self.assertFalse(info.available)

    def test_invalid_repo_rejected(self):
        with self.assertRaises(ValueError):
            UpdateChecker(repo="not a repo")
        with self.assertRaises(ValueError):
            UpdateChecker(repo="https://github.com/MerabyLabs/SE-Block-Exchanger")

    def test_version_tuple_and_normalize(self):
        self.assertEqual(UpdateChecker._normalize_version("v3.1.2"), "3.1.2")
        self.assertEqual(UpdateChecker._version_tuple("3.1"), (3, 1, 0))
        self.assertEqual(UpdateChecker._version_tuple("nope"), (0, 0, 0))
        self.assertTrue(UpdateChecker._version_tuple("3.2.0") > UpdateChecker._version_tuple("3.1.2"))

    def test_expired_cache_refetches(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            payload = {
                "tag_name": "v0.0.1",
                "html_url": "https://example.com/old",
                "published_at": "2020-01-01T00:00:00Z",
                "body": "old",
                "cached_at": "2000-01-01T00:00:00+00:00",
            }
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            checker = UpdateChecker(cache_path=cache_path, cache_hours=24)
            fresh = {
                "tag_name": "v99.9.9",
                "html_url": "https://example.com/new",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "new notes",
            }
            with patch.object(checker, "_fetch_release", return_value=fresh):
                info = checker.check_for_updates(force=False)
            self.assertTrue(info.available)
            self.assertEqual(info.latest_version, "99.9.9")
            self.assertEqual(info.changelog, "new notes")

    def test_live_github_latest_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            checker = UpdateChecker(cache_path=Path(tmp) / "cache.json", cache_hours=24)
            try:
                info = checker.check_for_updates(force=True)
            except Exception as exc:
                self.skipTest(f"GitHub API unavailable: {exc}")
            self.assertTrue(info.latest_version)
            self.assertIn("github.com", info.release_url)


if __name__ == "__main__":
    unittest.main()

