"""
Unit tests for Subgrid Hierarchy Parser and Matrix Visualizer.
"""

import unittest
from pathlib import Path
from subgrid_engine import SubgridHierarchyParser, GridMatrixVisualizer


class TestSubgridEngine(unittest.TestCase):
    def setUp(self):
        self.bp_path = Path("test_bp.sbc")

    def test_parse_hierarchy(self):
        if not self.bp_path.exists():
            self.skipTest("test_bp.sbc not found")
        structure = SubgridHierarchyParser.parse_file(self.bp_path)
        self.assertIsNotNone(structure.root_node)
        self.assertGreaterEqual(structure.total_blocks, 1)

    def test_visualizer_matrix(self):
        if not self.bp_path.exists():
            self.skipTest("test_bp.sbc not found")
        summaries = GridMatrixVisualizer.analyze_grid_matrix(self.bp_path)
        self.assertGreaterEqual(len(summaries), 1)
        self.assertIn("Top-Down Projection", summaries[0].ascii_top_down_view)
        self.assertIn("Side Profile Projection", summaries[0].ascii_side_view)


if __name__ == "__main__":
    unittest.main()
