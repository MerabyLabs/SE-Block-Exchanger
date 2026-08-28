"""Tests for BlueprintScanner metadata extraction and filtering."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from blueprint_fixtures import write_blueprint, write_blueprint_dir
from blueprint_scanner import BlueprintScanner
from mappings import build_registry


class TestBlueprintScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scanner = BlueprintScanner(
            registry=build_registry(include_builtin=True),
            enabled_categories=["armor", "thrusters"],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_parses_counts_and_convertible_blocks(self):
        write_blueprint_dir(
            self.root,
            "Alpha",
            ["LargeBlockArmorBlock", "LargeBlockArmorBlock", "LargeBlockSmallThrust", "LargeReactor"],
        )
        write_blueprint_dir(self.root, "Beta", ["LargeHeavyBlockArmorBlock"])
        (self.root / "NotABlueprint").mkdir()
        (self.root / "skip.txt").write_text("x", encoding="utf-8")

        results = self.scanner.scan_blueprints(self.root)
        names = {bp.name for bp in results}
        self.assertEqual(names, {"Alpha", "Beta"})

        alpha = self.scanner.get_blueprint_by_name("Alpha")
        self.assertIsNotNone(alpha)
        self.assertEqual(alpha.grid_size, "Large")
        self.assertEqual(alpha.block_count, 4)
        self.assertEqual(alpha.light_armor_count, 2)
        self.assertEqual(alpha.heavy_armor_count, 0)
        self.assertIn("armor", alpha.category_counts)
        self.assertIn("thrusters", alpha.category_counts)
        self.assertTrue(any("LargeBlockArmorBlock->" in key for key in alpha.convertible_counts))

        as_dict = alpha.to_dict()
        self.assertEqual(as_dict["name"], "Alpha")
        self.assertEqual(as_dict["block_count"], 4)

    def test_filter_blueprints(self):
        write_blueprint_dir(self.root, "LightFighter", ["LargeBlockArmorBlock"] * 3)
        write_blueprint_dir(self.root, "HeavyHauler", ["LargeHeavyBlockArmorBlock"])
        self.scanner.scan_blueprints(self.root)

        by_name = self.scanner.filter_blueprints(search_term="fighter")
        self.assertEqual([bp.name for bp in by_name], ["LightFighter"])

        by_armor = self.scanner.filter_blueprints(min_light_armor=2)
        self.assertEqual([bp.name for bp in by_armor], ["LightFighter"])

    def test_reverse_mapping_counts_heavy_as_convertible(self):
        folder = write_blueprint_dir(self.root, "Heavy", ["LargeHeavyBlockArmorBlock"])
        self.scanner.set_reverse(True)
        info = self.scanner.parse_folder(folder)
        self.assertEqual(info.heavy_armor_count, 1)
        self.assertTrue(any("LargeHeavyBlockArmorBlock->" in key for key in info.convertible_counts))

        self.scanner.set_reverse(False)
        forward = self.scanner.parse_folder(folder)
        self.assertFalse(forward.convertible_counts)

    def test_category_counts_include_mapping_targets(self):
        folder = write_blueprint_dir(self.root, "Upgraded", ["LargeBlockLargeThrust"])
        info = self.scanner.parse_folder(folder)
        self.assertIn("thrusters", info.category_counts)

    def test_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            self.scanner.scan_blueprints(self.root / "missing")

    def test_parse_folder_without_bp(self):
        empty = self.root / "Empty"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError):
            self.scanner.parse_folder(empty)

    def test_blueprint_without_cubegrid_is_still_counted(self):
        folder = self.root / "Legacy"
        folder.mkdir()
        write_blueprint(folder / "bp.sbc", ["LargeBlockArmorBlock"], include_grid=False)
        info = self.scanner.parse_folder(folder)
        self.assertEqual(info.block_count, 1)
        self.assertEqual(info.grid_size, "Unknown")

    def test_default_paths_require_appdata(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("APPDATA", None)
            with self.assertRaises(RuntimeError):
                self.scanner.get_default_blueprint_path()
            with self.assertRaises(RuntimeError):
                self.scanner.get_workshop_blueprint_path()

        with patch.dict(os.environ, {"APPDATA": str(self.root)}):
            local = self.scanner.get_default_blueprint_path()
            workshop = self.scanner.get_workshop_blueprint_path()
            self.assertTrue(str(local).endswith(os.path.join("SpaceEngineers", "Blueprints", "local")))
            self.assertTrue(str(workshop).endswith(os.path.join("SpaceEngineers", "Blueprints", "workshop")))

    def test_get_missing_name_returns_none(self):
        self.assertIsNone(self.scanner.get_blueprint_by_name("nope"))


if __name__ == "__main__":
    unittest.main()
