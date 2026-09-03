"""
Unit tests for Subgrid Hierarchy Parser and Matrix Visualizer.
"""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from subgrid_engine import GridMatrixVisualizer, SubgridHierarchyParser


def _write_minimal_blueprint(path: Path) -> Path:
    root = ET.Element("Definitions")
    ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
    grids = ET.SubElement(ship, "CubeGrids")
    grid = ET.SubElement(grids, "CubeGrid")
    ET.SubElement(grid, "EntityId").text = "1"
    ET.SubElement(grid, "DisplayName").text = "Hull"
    ET.SubElement(grid, "GridSizeEnum").text = "Large"
    blocks = ET.SubElement(grid, "CubeBlocks")
    block = ET.SubElement(blocks, "MyObjectBuilder_CubeBlock")
    ET.SubElement(block, "SubtypeName").text = "LargeBlockArmorBlock"
    ET.SubElement(block, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


class TestSubgridEngine(unittest.TestCase):
    def test_parse_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_minimal_blueprint(Path(tmp) / "bp.sbc")
            structure = SubgridHierarchyParser.parse_file(path)
            self.assertIsNotNone(structure.root_node)
            self.assertGreaterEqual(structure.total_blocks, 1)

    def test_visualizer_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_minimal_blueprint(Path(tmp) / "bp.sbc")
            summaries = GridMatrixVisualizer.analyze_grid_matrix(path)
            self.assertGreaterEqual(len(summaries), 1)
            self.assertIn("Top-Down Projection", summaries[0].ascii_top_down_view)
            self.assertIn("Side Profile Projection", summaries[0].ascii_side_view)
            self.assertIn("Armor", summaries[0].ascii_top_down_view)


if __name__ == "__main__":
    unittest.main()
