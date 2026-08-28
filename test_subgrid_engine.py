"""Tests for subgrid hierarchy parsing and voxel extraction."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blueprint_fixtures import write_blueprint
from subgrid_engine import GridMatrixVisualizer, SubgridHierarchyParser
from ui.theme import TacticalTheme
from ui.widgets.ship_canvas import ShipCanvas


class TestSubgridHierarchy(unittest.TestCase):
    def test_single_grid_is_listed_as_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_blueprint(
                Path(tmp) / "bp.sbc",
                [
                    {"subtype": "LargeBlockArmorBlock", "min": (0, 0, 0)},
                    {"subtype": "LargeBlockArmorBlock", "min": (1, 0, 0)},
                    {"subtype": "LargeBlockCockpit", "min": (2, 0, 0)},
                ],
            )
            structure = SubgridHierarchyParser.parse_file(path)
            self.assertEqual(structure.total_grids, 1)
            self.assertEqual(structure.total_blocks, 3)
            self.assertIsNotNone(structure.root_node)
            self.assertEqual(structure.root_node.block_count, 3)
            self.assertEqual(structure.root_node.children, [])

    def test_rotor_link_builds_parent_child_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bp.sbc"
            ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
            root = ET.Element("Definitions")
            ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
            grids = ET.SubElement(ship, "CubeGrids")

            main = ET.SubElement(grids, "CubeGrid")
            ET.SubElement(main, "EntityId").text = "100"
            ET.SubElement(main, "DisplayName").text = "Hull"
            ET.SubElement(main, "GridSizeEnum").text = "Large"
            main_blocks = ET.SubElement(main, "CubeBlocks")
            stator = ET.SubElement(main_blocks, "MyObjectBuilder_CubeBlock")
            stator.set("{http://www.w3.org/2001/XMLSchema-instance}type", "MyObjectBuilder_MotorStator")
            ET.SubElement(stator, "SubtypeName").text = "LargeStator"
            ET.SubElement(stator, "EntityId").text = "11"
            ET.SubElement(stator, "TopBlockId").text = "22"
            ET.SubElement(stator, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})

            turret = ET.SubElement(grids, "CubeGrid")
            ET.SubElement(turret, "EntityId").text = "200"
            ET.SubElement(turret, "DisplayName").text = "Turret"
            ET.SubElement(turret, "GridSizeEnum").text = "Small"
            turret_blocks = ET.SubElement(turret, "CubeBlocks")
            rotor = ET.SubElement(turret_blocks, "MyObjectBuilder_CubeBlock")
            rotor.set("{http://www.w3.org/2001/XMLSchema-instance}type", "MyObjectBuilder_MotorRotor")
            ET.SubElement(rotor, "SubtypeName").text = "SmallRotor"
            ET.SubElement(rotor, "EntityId").text = "22"
            ET.SubElement(rotor, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})

            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

            structure = SubgridHierarchyParser.parse_file(path)
            self.assertEqual(structure.total_grids, 2)
            self.assertEqual(structure.root_node.grid_name, "Hull")
            self.assertEqual(len(structure.root_node.children), 1)
            self.assertEqual(structure.root_node.children[0].grid_name, "Turret")
            self.assertIn("Rotor", structure.root_node.children[0].attachment_via or "")

            voxels = GridMatrixVisualizer.extract_all_voxels(path)
            names = {v["grid_name"] for v in voxels}
            self.assertEqual(names, {"Hull", "Turret"})
            self.assertTrue(any(v["is_subgrid"] for v in voxels))
            walked = structure.iter_nodes()
            self.assertEqual([node.grid_name for _, node in walked], ["Hull", "Turret"])
            self.assertEqual(walked[1][0], 1)

    def test_top_grid_id_links_child_cubegrid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bp.sbc"
            ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
            root = ET.Element("Definitions")
            ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
            grids = ET.SubElement(ship, "CubeGrids")

            main = ET.SubElement(grids, "CubeGrid")
            ET.SubElement(main, "EntityId").text = "100"
            ET.SubElement(main, "DisplayName").text = "Hull"
            ET.SubElement(main, "GridSizeEnum").text = "Large"
            main_blocks = ET.SubElement(main, "CubeBlocks")
            stator = ET.SubElement(main_blocks, "MyObjectBuilder_CubeBlock")
            stator.set("{http://www.w3.org/2001/XMLSchema-instance}type", "MyObjectBuilder_MotorStator")
            ET.SubElement(stator, "SubtypeName").text = "LargeStator"
            ET.SubElement(stator, "TopGridId").text = "200"
            ET.SubElement(stator, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})

            turret = ET.SubElement(grids, "CubeGrid")
            ET.SubElement(turret, "EntityId").text = "200"
            ET.SubElement(turret, "DisplayName").text = "Turret"
            ET.SubElement(turret, "GridSizeEnum").text = "Small"
            turret_blocks = ET.SubElement(turret, "CubeBlocks")
            block = ET.SubElement(turret_blocks, "MyObjectBuilder_CubeBlock")
            ET.SubElement(block, "SubtypeName").text = "SmallBlockArmorBlock"
            ET.SubElement(block, "Min").attrib.update({"x": "0", "y": "0", "z": "0"})

            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
            structure = SubgridHierarchyParser.parse_file(path)
            self.assertEqual(structure.total_grids, 2)
            self.assertEqual(structure.root_node.grid_name, "Hull")
            self.assertEqual(structure.root_node.children[0].grid_name, "Turret")


class TestVoxelsAndCanvas(unittest.TestCase):
    def test_extract_voxels_keeps_min_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_blueprint(
                Path(tmp) / "bp.sbc",
                [
                    {"subtype": "LargeBlockArmorBlock", "min": (3, 1, 2)},
                    {"subtype": "LargeBlockSmallThrust", "min": (4, 1, 2)},
                ],
            )
            voxels = GridMatrixVisualizer.extract_all_voxels(path)
            self.assertEqual(len(voxels), 2)
            self.assertEqual((voxels[0]["x"], voxels[0]["y"], voxels[0]["z"]), (3, 1, 2))

    def test_block_colors(self):
        fill, _ = ShipCanvas._get_block_color("LargeBlockCockpit", False)
        self.assertEqual(fill, TacticalTheme.COLOR_COCKPIT)
        fill, _ = ShipCanvas._get_block_color("LargeBlockLargeThrust", False)
        self.assertEqual(fill, TacticalTheme.COLOR_PROPULSION)
        fill, _ = ShipCanvas._get_block_color("LargeMissileTurret", False)
        self.assertEqual(fill, TacticalTheme.COLOR_WEAPONS)
        fill, _ = ShipCanvas._get_block_color("LargeBlockArmorBlock", True)
        self.assertEqual(fill, TacticalTheme.COLOR_SUBGRID)


class TestReadableFonts(unittest.TestCase):
    def test_box_fonts_are_at_least_15pt(self):
        self.assertGreaterEqual(TacticalTheme.FONT_SMALL[1], 15)
        self.assertGreaterEqual(TacticalTheme.FONT_NORMAL[1], 17)
        self.assertGreaterEqual(TacticalTheme.FONT_MONO_SMALL[1], 16)
        self.assertGreaterEqual(TacticalTheme.FONT_CODE_SMALL[1], 16)


if __name__ == "__main__":
    unittest.main()
