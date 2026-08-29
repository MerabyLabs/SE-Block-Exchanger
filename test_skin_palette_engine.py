"""
Unit tests for SkinPaletteEngine (Armor textures & HSV Color Conversion).
"""

import shutil
import tempfile
import unittest
from pathlib import Path
import safe_xml
from mappings.skin_palette_engine import SkinPaletteEngine
from blueprint_fixtures import write_blueprint_dir
from test_grid_matrix_generator import generate_all_test_grids


class TestSkinPaletteEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.grids = generate_all_test_grids(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_rgb_to_se_hsv_and_back(self):
        # White (255, 255, 255)
        se_x, se_y, se_z = SkinPaletteEngine.rgb_to_se_hsv(255, 255, 255)
        r, g, b = SkinPaletteEngine.se_hsv_to_rgb(se_x, se_y, se_z)
        self.assertAlmostEqual(r, 255, delta=5)
        self.assertAlmostEqual(g, 255, delta=5)
        self.assertAlmostEqual(b, 255, delta=5)

        # Red (255, 0, 0)
        se_x, se_y, se_z = SkinPaletteEngine.rgb_to_se_hsv(255, 0, 0)
        self.assertEqual(se_x, 0.0)

    def test_02_apply_skin_and_color_to_battleship(self):
        bp_dir = self.grids["Battleship_Vindicator"]
        reskinned, recolored = SkinPaletteEngine.apply_skin_and_palette(
            source_bp_path=bp_dir,
            skin_id="Carbon_Fiber",
            primary_hex="#0284c7",
            armor_only=True,
        )

        self.assertGreater(reskinned, 0)
        self.assertGreater(recolored, 0)

        output_dir = bp_dir.parent / "Battleship_Vindicator_RESKINNED"
        self.assertTrue((output_dir / "bp.sbc").exists())

        tree = safe_xml.parse(output_dir / "bp.sbc")
        armor_blocks = [
            b for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")
            if "armor" in (b.find("SubtypeName").text if b.find("SubtypeName") is not None else "").lower()
        ]
        self.assertGreater(len(armor_blocks), 0)
        for ab in armor_blocks:
            skin_tag = ab.find("SkinSubtypeId")
            self.assertIsNotNone(skin_tag)
            self.assertEqual(skin_tag.text, "Carbon_Fiber")

    def _color_xyz(self, block):
        color = block.find("ColorMaskHSV")
        self.assertIsNotNone(color)
        return color.get("x"), color.get("y"), color.get("z")

    def test_03_secondary_hex_paints_non_armor_accent(self):
        bp_dir = write_blueprint_dir(
            self.test_dir,
            "TwoToneHull",
            ["LargeBlockArmorBlock", "LargeBlockLargeThrust"],
        )
        primary = "#ff0000"
        secondary = "#00ff00"
        reskinned, recolored = SkinPaletteEngine.apply_skin_and_palette(
            source_bp_path=bp_dir,
            primary_hex=primary,
            secondary_hex=secondary,
            armor_only=False,
        )
        self.assertEqual(reskinned, 0)
        self.assertEqual(recolored, 2)

        output = bp_dir.parent / "TwoToneHull_RESKINNED" / "bp.sbc"
        tree = safe_xml.parse(output)
        blocks = {
            (b.find("SubtypeName").text): b
            for b in tree.getroot().findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
        }
        primary_hsv = SkinPaletteEngine._hsv_from_hex(primary)
        secondary_hsv = SkinPaletteEngine._hsv_from_hex(secondary)
        self.assertEqual(
            self._color_xyz(blocks["LargeBlockArmorBlock"]),
            (str(primary_hsv[0]), str(primary_hsv[1]), str(primary_hsv[2])),
        )
        self.assertEqual(
            self._color_xyz(blocks["LargeBlockLargeThrust"]),
            (str(secondary_hsv[0]), str(secondary_hsv[1]), str(secondary_hsv[2])),
        )

    def test_04_armor_only_splits_light_and_heavy_when_both_hexes_set(self):
        bp_dir = write_blueprint_dir(
            self.test_dir,
            "SplitArmor",
            ["LargeBlockArmorBlock", "LargeHeavyBlockArmorBlock", "LargeBlockLargeThrust"],
        )
        primary = "#0000ff"
        secondary = "#ffff00"
        _reskinned, recolored = SkinPaletteEngine.apply_skin_and_palette(
            source_bp_path=bp_dir,
            primary_hex=primary,
            secondary_hex=secondary,
            armor_only=True,
        )
        self.assertEqual(recolored, 2)

        output = bp_dir.parent / "SplitArmor_RESKINNED" / "bp.sbc"
        tree = safe_xml.parse(output)
        blocks = {
            (b.find("SubtypeName").text): b
            for b in tree.getroot().findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
        }
        primary_hsv = SkinPaletteEngine._hsv_from_hex(primary)
        secondary_hsv = SkinPaletteEngine._hsv_from_hex(secondary)
        self.assertEqual(
            self._color_xyz(blocks["LargeBlockArmorBlock"]),
            (str(primary_hsv[0]), str(primary_hsv[1]), str(primary_hsv[2])),
        )
        self.assertEqual(
            self._color_xyz(blocks["LargeHeavyBlockArmorBlock"]),
            (str(secondary_hsv[0]), str(secondary_hsv[1]), str(secondary_hsv[2])),
        )
        self.assertIsNone(blocks["LargeBlockLargeThrust"].find("ColorMaskHSV"))

    def test_05_secondary_only_paints_matching_blocks(self):
        bp_dir = write_blueprint_dir(
            self.test_dir,
            "AccentOnly",
            ["LargeBlockArmorBlock", "LargeBlockLargeThrust"],
        )
        secondary = "#00ffff"
        _reskinned, recolored = SkinPaletteEngine.apply_skin_and_palette(
            source_bp_path=bp_dir,
            secondary_hex=secondary,
            armor_only=False,
        )
        self.assertEqual(recolored, 2)
        hsv = SkinPaletteEngine._hsv_from_hex(secondary)
        output = bp_dir.parent / "AccentOnly_RESKINNED" / "bp.sbc"
        tree = safe_xml.parse(output)
        for block in tree.getroot().findall(".//CubeBlocks/MyObjectBuilder_CubeBlock"):
            self.assertEqual(
                self._color_xyz(block),
                (str(hsv[0]), str(hsv[1]), str(hsv[2])),
            )


if __name__ == "__main__":
    unittest.main()
