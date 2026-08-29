"""
Unit tests for Subgrid Projector Splitter Engine.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
import safe_xml
from subgrid_engine import ProjectorSplitter
from test_grid_matrix_generator import generate_all_test_grids


class TestProjectorSplitter(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.grids = generate_all_test_grids(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_split_mech_walker_multigrid(self):
        walker_dir = self.grids["MultiGrid_Walker"]
        result = ProjectorSplitter.split_blueprint(walker_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.total_subgrids, 3)
        self.assertTrue(result.output_directory.exists())
        self.assertTrue((result.output_directory / "PRINTING_GUIDE.md").exists())

        # Check that individual sub-blueprint folders exist
        sub_dirs = list(result.output_directory.iterdir())
        folder_names = [d.name for d in sub_dirs if d.is_dir()]
        self.assertTrue(any("MAIN_HULL" in name for name in folder_names))
        self.assertTrue(any("Left Leg" in name for name in folder_names))
        self.assertTrue(any("Right Arm" in name for name in folder_names))

        # Check each sub-blueprint contains exactly 1 CubeGrid in valid XML format
        xsi = "{http://www.w3.org/2001/XMLSchema-instance}type"
        for entry in result.sub_blueprints:
            self.assertTrue(entry.sbc_path.exists())
            raw = entry.sbc_path.read_text(encoding="utf-8")
            self.assertIn("xmlns:xsi=", raw)
            tree = safe_xml.parse(entry.sbc_path)
            cube_grids = tree.getroot().findall(".//CubeGrid")
            self.assertEqual(len(cube_grids), 1)
            ship_bp = tree.getroot().find(".//ShipBlueprint")
            self.assertIsNotNone(ship_bp)
            self.assertEqual(ship_bp.get(xsi), "MyObjectBuilder_ShipBlueprintDefinition")

    def test_02_single_grid_reports_no_splitting_needed(self):
        battleship_dir = self.grids["Battleship_Vindicator"]
        result = ProjectorSplitter.split_blueprint(battleship_dir)

        self.assertTrue(result.success)
        self.assertEqual(result.total_subgrids, 1)
        self.assertIsNone(result.error_message)


if __name__ == "__main__":
    unittest.main()
