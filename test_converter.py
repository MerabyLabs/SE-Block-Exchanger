"""Tests for BlueprintConverter: copy conversion, undo, prefixes, grid rescale."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile

from blueprint_converter import BlueprintConverter
from blueprint_fixtures import write_blueprint_dir


class TestBlueprintConverter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.converter = BlueprintConverter(verbose=True, include_profiles=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_heavy_armor_blueprint_and_remove_binary_cache(self):
        source = write_blueprint_dir(
            self.root,
            "MyShip",
            ["LargeBlockArmorBlock"],
            extra_files=["bp.sbcB5"],
        )
        dest, scanned, converted = self.converter.create_heavy_armor_blueprint(source)
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        self.assertEqual(dest.name, "HEAVYARMOR_MyShip")
        self.assertFalse((dest / "bp.sbcB5").exists())
        self.assertTrue((source / "bp.sbcB5").exists())
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeHeavyBlockArmorBlock", xml)

    def test_reverse_prefix(self):
        converter = BlueprintConverter(reverse=True, include_profiles=False)
        source = write_blueprint_dir(self.root, "Tank", ["LargeHeavyBlockArmorBlock"])
        dest, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 1)
        self.assertEqual(dest.name, "LIGHTARMOR_Tank")

    def test_multi_category_prefix(self):
        converter = BlueprintConverter(
            enabled_categories=["armor", "thrusters"],
            include_profiles=False,
        )
        source = write_blueprint_dir(self.root, "Fighter", ["LargeBlockArmorBlock"])
        dest, _, _ = converter.create_converted_blueprint(source)
        self.assertEqual(dest.name, "CONVERTED_Fighter")

    def test_overwrite_existing_destination(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        first, _, _ = self.converter.create_converted_blueprint(source)
        marker = first / "marker.txt"
        marker.write_text("old", encoding="utf-8")
        second, _, converted = self.converter.create_converted_blueprint(source)
        self.assertEqual(first, second)
        self.assertEqual(converted, 1)
        self.assertFalse(marker.exists())

    def test_undo_last_conversion(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        dest, _, _ = self.converter.create_converted_blueprint(source)
        self.assertTrue(dest.exists())
        undone = self.converter.undo_last_conversion()
        self.assertEqual(undone, dest)
        self.assertFalse(dest.exists())
        self.assertIsNone(self.converter.undo_last_conversion())

    def test_delete_converted_blueprint(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        dest, _, _ = self.converter.create_converted_blueprint(source)
        self.assertTrue(self.converter.delete_converted_blueprint(source))
        self.assertFalse(dest.exists())
        self.assertFalse(self.converter.delete_heavy_armor_blueprint(source))

    def test_destination_exists_check(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        self.assertFalse(self.converter.check_destination_exists(source))
        self.converter.create_converted_blueprint(source)
        self.assertTrue(self.converter.check_destination_exists(source))

    def test_missing_source_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.converter.create_converted_blueprint(self.root / "missing")

    def test_file_instead_of_directory_raises(self):
        file_path = self.root / "bp.sbc"
        file_path.write_text("<xml/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.converter.create_converted_blueprint(file_path)

    def test_directory_without_bp_raises(self):
        empty = self.root / "Empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            self.converter.create_converted_blueprint(empty)

    def test_dlc_vanillafy_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["dlc_substitution"],
            include_profiles=False,
        )
        source = write_blueprint_dir(
            self.root,
            "DLCShip",
            ["LargeBlockSmallThrustSciFi", "IndustrialCockpit"],
        )
        dest, scanned, converted = converter.create_converted_blueprint(source)
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockSmallThrust", xml)
        self.assertIn("LargeBlockCockpit", xml)
        self.assertNotIn("SciFi", xml)
        self.assertNotIn("IndustrialCockpit", xml)

    def test_thruster_and_weapon_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["thrusters", "weapons"],
            include_profiles=False,
        )
        source = write_blueprint_dir(
            self.root,
            "Combat",
            ["LargeBlockSmallThrust", "LargeGatlingTurret"],
        )
        dest, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 2)
        xml = (dest / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockLargeThrust", xml)
        self.assertIn("LargeAutocannonTurret", xml)

    def test_functional_conversion(self):
        converter = BlueprintConverter(
            enabled_categories=["functional"],
            include_profiles=False,
        )
        source = write_blueprint_dir(self.root, "Factory", ["BasicRefinery", "BasicAssembler"])
        _, _, converted = converter.create_converted_blueprint(source)
        self.assertEqual(converted, 2)

    def test_scale_grid_large_to_small_scales_coords_and_keeps_inner_size(self):
        source = write_blueprint_dir(
            self.root,
            "BigGrid",
            [
                {"subtype": "LargeBlockLargeThrust", "min": (2, 0, 1)},
                {"subtype": "LargeBlockArmorBlock", "min": (0, 0, 0)},
            ],
            grid_size="Large",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Small")
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        self.assertTrue(dest.name.startswith("SCALED_SMALL_"))

        tree = ET.parse(dest / "bp.sbc")
        self.assertEqual(tree.find(".//CubeGrid/GridSizeEnum").text, "Small")
        subtypes = [elem.text for elem in tree.findall(".//SubtypeName")]
        self.assertIn("SmallBlockLargeThrust", subtypes)
        self.assertNotIn("SmallBlockSmallThrust", subtypes)
        self.assertIn("SmallBlockArmorBlock", subtypes)

        mins = tree.findall(".//Min")
        coords = {(m.attrib["x"], m.attrib["y"], m.attrib["z"]) for m in mins}
        self.assertIn(("10", "0", "5"), coords)
        self.assertIn(("0", "0", "0"), coords)

    def test_scale_grid_small_to_large(self):
        source = write_blueprint_dir(
            self.root,
            "SmallGrid",
            [{"subtype": "SmallBlockArmorBlock", "min": (10, 0, 5)}],
            grid_size="Small",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Large")
        self.assertEqual(scanned, 1)
        self.assertEqual(converted, 1)
        tree = ET.parse(dest / "bp.sbc")
        self.assertEqual(tree.find(".//CubeGrid/GridSizeEnum").text, "Large")
        self.assertEqual(tree.find(".//SubtypeName").text, "LargeBlockArmorBlock")
        min_elem = tree.find(".//Min")
        self.assertEqual(min_elem.attrib["x"], "2")
        self.assertEqual(min_elem.attrib["z"], "1")

    def test_scale_grid_small_to_large_truncates_negative_mins_toward_zero(self):
        source = write_blueprint_dir(
            self.root,
            "NegGrid",
            [
                {"subtype": "SmallBlockArmorBlock", "min": (-1, -5, -6)},
                {"subtype": "SmallBlockArmorBlock", "min": (4, 0, -10)},
            ],
            grid_size="Small",
        )
        dest, scanned, converted = self.converter.scale_grid_size(source, "Large")
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        tree = ET.parse(dest / "bp.sbc")
        mins = {(m.attrib["x"], m.attrib["y"], m.attrib["z"]) for m in tree.findall(".//Min")}
        # -1/5 → 0, -5/5 → -1, -6/5 → -1; 4/5 → 0, -10/5 → -2
        self.assertIn(("0", "-1", "-1"), mins)
        self.assertIn(("0", "0", "-2"), mins)
        self.assertNotIn(("-1", "-1", "-2"), mins)

    def test_scale_invalid_size(self):
        source = write_blueprint_dir(self.root, "Ship", ["LargeBlockArmorBlock"])
        with self.assertRaises(ValueError):
            self.converter.scale_grid_size(source, "Medium")

    def test_scale_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            self.converter.scale_grid_size(self.root / "nope", "Small")


if __name__ == "__main__":
    unittest.main()
