"""Tests for persistent AppSettings."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
import tempfile

from app_settings import AppSettings, SettingsStore


class TestAppSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"
        self.store = SettingsStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_returns_defaults(self):
        settings = self.store.load()
        self.assertEqual(settings.appearance_mode, "System")
        self.assertTrue(settings.auto_check_updates)
        self.assertEqual(settings.enabled_categories, ["armor"])
        self.assertEqual(settings.cache_hours, 24)

    def test_round_trip(self):
        settings = AppSettings(
            appearance_mode="Dark",
            auto_check_updates=False,
            enabled_categories=["armor", "thrusters"],
            cache_hours=12,
        )
        self.store.save(settings)
        loaded = self.store.load()
        self.assertEqual(loaded.appearance_mode, "Dark")
        self.assertFalse(loaded.auto_check_updates)
        self.assertEqual(loaded.enabled_categories, ["armor", "thrusters"])
        self.assertEqual(loaded.cache_hours, 12)

    def test_add_recent_dir_dedupes_and_caps(self):
        settings = AppSettings()
        for index in range(10):
            settings = self.store.add_recent_dir(settings, f"/blueprints/{index}", limit=8)
        settings = self.store.add_recent_dir(settings, "/blueprints/9", limit=8)
        self.assertEqual(settings.recent_blueprint_dirs[0], "/blueprints/9")
        self.assertEqual(len(settings.recent_blueprint_dirs), 8)
        self.assertEqual(settings.recent_blueprint_dirs.count("/blueprints/9"), 1)

    def test_add_recent_blueprint_dedupes(self):
        settings = AppSettings()
        settings = self.store.add_recent_blueprint(settings, "Ship A")
        settings = self.store.add_recent_blueprint(settings, "Ship B")
        settings = self.store.add_recent_blueprint(settings, "Ship A")
        self.assertEqual(settings.recent_blueprints[:2], ["Ship A", "Ship B"])

    def test_from_dict_handles_partial_payload(self):
        settings = AppSettings.from_dict({"appearance_mode": "Light"})
        self.assertEqual(settings.appearance_mode, "Light")
        self.assertEqual(settings.enabled_categories, ["armor"])
        self.assertEqual(settings.to_dict()["appearance_mode"], "Light")

    def test_saved_file_is_json(self):
        self.store.save(AppSettings(appearance_mode="Light"))
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["appearance_mode"], "Light")


if __name__ == "__main__":
    unittest.main()
