"""
Unit tests for SkinPaletteEngine (Armor textures & HSV Color Conversion).
"""

import shutil
import tempfile
import unittest
from pathlib import Path
import safe_xml
from mappings.skin_palette_engine import SkinPaletteEngine
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

        self.assertTrue(reskinned > 0)
        self.assertTrue(recolored > 0)

        output_dir = bp_dir.parent / "Battleship_Vindicator_RESKINNED"
        self.assertTrue((output_dir / "bp.sbc").exists())

        tree = safe_xml.parse(output_dir / "bp.sbc")
        armor_blocks = [
            b for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")
            if "armor" in (b.find("SubtypeName").text if b.find("SubtypeName") is not None else "").lower()
        ]
        self.assertTrue(len(armor_blocks) > 0)
        for ab in armor_blocks:
            skin_tag = ab.find("SkinSubtypeId")
            self.assertIsNotNone(skin_tag)
            self.assertEqual(skin_tag.text, "Carbon_Fiber")


if __name__ == "__main__":
    unittest.main()
