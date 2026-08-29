import json
import tempfile
import unittest
from pathlib import Path

from mapping_profiles import MappingProfile, ProfileManager
from mappings import build_registry
from mappings.registry import MappingCategory


class TestProfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_dir = Path(self.tmp.name)
        self.manager = ProfileManager(self.profile_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_load_profile(self):
        profile = MappingProfile(
            name="Test Profile",
            author="Tester",
            version="1.0",
            description="Test",
            game_version="1.205+",
            categories=[
                MappingCategory(
                    name="profile:test:weapons",
                    description="Test category",
                    pairs={"SmallGatlingGun": "CustomGun"},
                    source="profile:Test",
                    enabled_by_default=False,
                    tags=("profile",),
                )
            ],
        )
        saved = self.manager.upsert_profile(profile)
        self.assertTrue(saved.exists())

        self.manager.load_all()
        loaded = self.manager.get("Test Profile")
        self.assertEqual(loaded.name, "Test Profile")
        self.assertEqual(len(loaded.categories), 1)
        self.assertIn("SmallGatlingGun", loaded.categories[0].pairs)

    def test_register_profile_categories(self):
        payload = {
            "name": "Imported",
            "author": "Tester",
            "version": "1.0",
            "description": "Imported profile",
            "game_version": "1.205+",
            "categories": [
                {
                    "name": "ModCat",
                    "pairs": [["A", "B"]],
                }
            ],
        }
        path = self.profile_dir / "imported.sebx-profile"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.manager.load_all()

        registry = build_registry(include_builtin=True)
        count = self.manager.register_profile_categories(registry)
        self.assertEqual(count, 1)
        self.assertTrue(any(cat.name.startswith("profile:imported:") for cat in registry.list_categories()))

    def test_duplicate_profile(self):
        payload = {
            "name": "Original",
            "author": "Tester",
            "version": "1.0",
            "description": "Original profile",
            "game_version": "1.205+",
            "categories": [
                {
                    "name": "Cat1",
                    "pairs": [["X", "Y"]],
                }
            ],
        }
        path = self.profile_dir / "original.sebx-profile"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.manager.load_all()

        duplicated = self.manager.duplicate_profile("Original", "Original Copy")
        self.assertEqual(duplicated.name, "Original Copy")
        self.assertEqual(duplicated.categories[0].pairs["X"], "Y")

    def test_validation_rejects_bad_profiles(self):
        with self.assertRaises(Exception):
            self.manager.validate_profile_json({})
        with self.assertRaises(Exception):
            self.manager.validate_profile_json(
                {
                    "name": "Bad",
                    "author": "A",
                    "version": "1",
                    "description": "d",
                    "game_version": "1",
                    "categories": [],
                }
            )
        with self.assertRaises(Exception):
            self.manager.validate_profile_json(
                {
                    "name": "Circular",
                    "author": "A",
                    "version": "1",
                    "description": "d",
                    "game_version": "1",
                    "categories": [{"name": "C", "pairs": [["A", "B"], ["B", "A"]]}],
                }
            )
        with self.assertRaises(Exception):
            self.manager.validate_profile_json(
                {
                    "name": "DupCat",
                    "author": "A",
                    "version": "1",
                    "description": "d",
                    "game_version": "1",
                    "categories": [
                        {"name": "Same", "pairs": [["A", "B"]]},
                        {"name": "Same", "pairs": [["C", "D"]]},
                    ],
                }
            )

    def test_export_to_directory_and_custom_file(self):
        payload = {
            "name": "Share Me",
            "author": "Tester",
            "version": "1.0",
            "description": "Shareable",
            "game_version": "1.205+",
            "categories": [{"name": "Cat1", "pairs": [["Alpha", "Beta"]]}],
        }
        path = self.profile_dir / "share.sebx-profile"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.manager.load_all()

        dest_dir = self.profile_dir / "exports"
        dest_dir.mkdir()
        exported = self.manager.export_profile("Share Me", dest_dir)
        self.assertTrue(exported.exists())
        self.assertTrue(exported.name.endswith(".sebx-profile"))

        custom = self.profile_dir / "custom.json"
        custom_exported = self.manager.export_profile("Share Me", custom)
        self.assertEqual(custom_exported, custom)
        self.assertTrue(custom.exists())

        suffixless = self.profile_dir / "shareme"
        suffixless.write_text("placeholder", encoding="utf-8")
        suffixless_exported = self.manager.export_profile("Share Me", suffixless)
        self.assertEqual(suffixless_exported, suffixless.with_suffix(".sebx-profile"))
        self.assertTrue(suffixless_exported.exists())
        self.assertIn("Share Me", suffixless_exported.read_text(encoding="utf-8"))

        share = self.manager.discord_share_text("Share Me")
        self.assertIn("**Share Me**", share)
        self.assertIn("```json", share)
        self.assertIn("Alpha", share)

    def test_import_from_file_and_url(self):
        from unittest.mock import patch

        payload = {
            "name": "Remote",
            "author": "Net",
            "version": "1.0",
            "description": "From URL",
            "game_version": "1.205+",
            "categories": [{"name": "NetCat", "pairs": [["One", "Two"]]}],
        }
        source = self.profile_dir / "remote.sebx-profile"
        source.write_text(json.dumps(payload), encoding="utf-8")

        other_dir = Path(self.tmp.name) / "other"
        other = ProfileManager(other_dir)
        imported, saved = other.import_profile(str(source))
        self.assertEqual(imported.name, "Remote")
        self.assertTrue(saved.exists())

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=FakeResponse()):
            profile, saved_path = self.manager.import_profile("https://example.com/profile.sebx-profile")
        self.assertEqual(profile.name, "Remote")
        self.assertTrue(saved_path.exists())

    def test_unknown_profile_and_known_block_ids(self):
        with self.assertRaises(KeyError):
            self.manager.get("missing")
        registry = build_registry(include_builtin=True)
        ids = ProfileManager.list_known_block_ids(registry)
        self.assertIn("LargeBlockArmorBlock", ids)
        self.assertIn("LargeHeavyBlockArmorBlock", ids)

    def test_bundled_profiles_load(self):
        manager = ProfileManager(Path("profiles"))
        loaded = manager.load_all()
        names = {profile.name for profile in loaded}
        self.assertIn("WeaponCore Upgrades", names)
        self.assertIn("Assertive Armaments", names)
        self.assertIn("Build Vision Enhancements", names)


if __name__ == "__main__":
    unittest.main()

