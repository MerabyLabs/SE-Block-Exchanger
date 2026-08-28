"""
Unit tests for Armor Hardening & Lightweighting Engine.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
import safe_xml
from mappings.armor_hardening import ArmorHardeningEngine
from test_grid_matrix_generator import generate_all_test_grids


class TestArmorHardening(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.grids = generate_all_test_grids(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_harden_vital_cores(self):
        bp_dir = self.grids["Battleship_Vindicator"]
        res = ArmorHardeningEngine.harden_vital_cores(bp_dir, reinforce_radius=2)

        self.assertTrue(res.critical_cores_found > 0)
        self.assertTrue(res.armor_blocks_hardened > 0)
        self.assertTrue((res.output_path / "bp.sbc").exists())

        tree = safe_xml.parse(res.output_path / "bp.sbc")
        heavy_blocks = [
            b for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")
            if "Heavy" in (b.find("SubtypeName").text if b.find("SubtypeName") is not None else "")
        ]
        self.assertTrue(len(heavy_blocks) > 0)

    def test_02_lightweight_outer_hull(self):
        bp_dir = self.grids["Battleship_Vindicator"]
        res = ArmorHardeningEngine.lightweight_outer_hull(bp_dir, preserve_radius=1)

        self.assertTrue((res.output_path / "bp.sbc").exists())


if __name__ == "__main__":
    unittest.main()
