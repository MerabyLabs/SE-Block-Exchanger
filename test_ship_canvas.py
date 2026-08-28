"""
Unit tests for 2D / 2.5D Ship Blueprint Canvas & Voxel Matrix.
"""

import unittest
from pathlib import Path
from ui.widgets.ship_canvas import ShipCanvas
from subgrid_engine import GridMatrixVisualizer
from test_grid_matrix_generator import generate_all_test_grids
import tempfile
import shutil


class TestShipCanvas(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.grids = generate_all_test_grids(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_extract_all_voxels_from_blueprint(self):
        bp_file = self.grids["Battleship_Vindicator"] / "bp.sbc"
        voxels = GridMatrixVisualizer.extract_all_voxels(bp_file)
        self.assertTrue(len(voxels) > 0)
        
        first = voxels[0]
        self.assertIn("x", first)
        self.assertIn("y", first)
        self.assertIn("z", first)
        self.assertIn("subtype", first)
        self.assertIn("grid_name", first)

    def test_02_voxel_block_color_classification(self):
        # Cockpit
        fill, outline = ShipCanvas._get_block_color("LargeBlockCockpit", False)
        self.assertEqual(fill, "#f59e0b")

        # Thruster
        fill, outline = ShipCanvas._get_block_color("LargeBlockLargeThrust", False)
        self.assertEqual(fill, "#06b6d4")

        # Weapon
        fill, outline = ShipCanvas._get_block_color("LargeMissileTurret", False)
        self.assertEqual(fill, "#ef4444")

        # Subgrid
        fill, outline = ShipCanvas._get_block_color("LargeBlockArmorBlock", True)
        self.assertEqual(fill, "#10b981")


if __name__ == "__main__":
    unittest.main()
