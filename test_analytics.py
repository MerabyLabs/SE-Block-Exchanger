import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blueprint_analytics import BlueprintAnalyticsEngine


class TestBlueprintAnalytics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.bp_file = self.tmp_path / "bp.sbc"
        self.engine = BlueprintAnalyticsEngine()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_blueprint(self, subtypes):
        root = ET.Element("Definitions")
        ship_blueprints = ET.SubElement(root, "ShipBlueprints")
        ship_blueprint = ET.SubElement(ship_blueprints, "ShipBlueprint")
        cube_grid = ET.SubElement(ship_blueprint, "CubeGrid")
        ET.SubElement(cube_grid, "GridSizeEnum").text = "Large"
        cube_blocks = ET.SubElement(cube_grid, "CubeBlocks")
        for subtype in subtypes:
            block = ET.SubElement(cube_blocks, "MyObjectBuilder_CubeBlock")
            ET.SubElement(block, "SubtypeName").text = subtype
        ET.ElementTree(root).write(self.bp_file, encoding="utf-8", xml_declaration=True)

    def test_analyze_blueprint(self):
        self._write_blueprint(
            [
                "LargeBlockArmorBlock",
                "LargeBlockArmorBlock",
                "LargeBlockCockpit",
                "LargeBlockBatteryBlock",
                "LargeBlockSmallThrust",
            ]
        )
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertEqual(result.block_count, 5)
        self.assertGreater(result.pcu_total, 0)
        self.assertIn("SteelPlate", result.component_totals)
        self.assertEqual(result.grid_size, "Large")
        self.assertTrue(all(issue.code != "missing_power" for issue in result.health_issues))

    def test_compare_conversion_cost(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockArmorBlock", "LargeBlockCockpit"])
        mapping = {"LargeBlockArmorBlock": "LargeHeavyBlockArmorBlock"}
        comparison = self.engine.compare_conversion_cost(
            self.bp_file,
            mapping=mapping,
            mode="light_to_heavy",
        )
        self.assertIn("LargeBlockArmorBlock -> LargeHeavyBlockArmorBlock", comparison.block_changes)
        self.assertGreater(comparison.component_delta.get("SteelPlate", 0), 0)

    def test_compare_conversion_cost_reuses_precomputed_result(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockArmorBlock", "LargeBlockCockpit"])
        mapping = {"LargeBlockArmorBlock": "LargeHeavyBlockArmorBlock"}
        result = self.engine.analyze_blueprint(self.bp_file)
        from_file = self.engine.compare_conversion_cost(
            self.bp_file,
            mapping=mapping,
            mode="light_to_heavy",
        )
        from_result = self.engine.compare_conversion_cost_from_result(
            result,
            mapping,
            "light_to_heavy",
        )
        self.assertEqual(from_file.block_changes, from_result.block_changes)
        self.assertEqual(from_file.pcu_delta, from_result.pcu_delta)
        self.assertEqual(from_file.mass_delta, from_result.mass_delta)

    def test_export_reports(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockCockpit"])
        comparison = self.engine.compare_conversion_cost(
            self.bp_file,
            mapping={"LargeBlockArmorBlock": "LargeHeavyBlockArmorBlock"},
            mode="light_to_heavy",
        )
        csv_path = self.tmp_path / "report.csv"
        txt_path = self.tmp_path / "report.txt"
        self.engine.export_comparison_csv(comparison, csv_path)
        self.engine.export_comparison_text(comparison, txt_path)
        self.assertTrue(csv_path.exists())
        self.assertTrue(txt_path.exists())

    def test_apply_fix_add_power(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockCockpit"])
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertTrue(any(issue.code == "missing_power" for issue in result.health_issues))

        applied = self.engine.apply_fix(self.bp_file, "add_power_block")
        self.assertTrue(applied)

        fixed = self.engine.analyze_blueprint(self.bp_file)
        self.assertFalse(any(issue.code == "missing_power" for issue in fixed.health_issues))

    def test_missing_control_and_unknown_fix_id(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockBatteryBlock"])
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertTrue(any(issue.code == "missing_control" for issue in result.health_issues))
        self.assertFalse(self.engine.apply_fix(self.bp_file, "not_a_real_fix"))
        self.assertTrue(self.engine.apply_fix(self.bp_file, "add_control_block"))
        fixed = self.engine.analyze_blueprint(self.bp_file)
        self.assertFalse(any(issue.code == "missing_control" for issue in fixed.health_issues))

    def test_unknown_blocks_and_cost_inference(self):
        self._write_blueprint(["LargeBlockArmorSlope", "TotallyModdedBlockXYZ"])
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertIn("TotallyModdedBlockXYZ", result.unknown_subtypes)
        self.assertTrue(any(issue.code == "unknown_blocks" for issue in result.health_issues))
        self.assertIn("SteelPlate", result.component_totals)
        self.assertGreater(result.mass_total, 0)

        inferred = self.engine.db.get_block("SmallHeavyBlockArmorSlope")
        self.assertIsNotNone(inferred)
        self.assertEqual(inferred["category"], "armor")
        self.assertEqual(self.engine.db.category_for_subtype("LargeGatlingTurret"), "weapons")
        self.assertEqual(self.engine.db.category_for_subtype("SomethingThrust"), "thrusters")

    def test_ore_and_ingot_rollups(self):
        self._write_blueprint(["LargeBlockArmorBlock", "LargeBlockCockpit", "LargeBlockBatteryBlock"])
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertTrue(result.ingot_totals)
        self.assertTrue(result.ore_totals)
        self.assertIn("Iron", result.ingot_totals)
        self.assertTrue(any(name.endswith(" Ore") for name in result.ore_totals))

    def test_thruster_imbalance_warning(self):
        subtypes = [
            {"subtype": "LargeBlockSmallThrust", "orientation": direction}
            for direction in ("Forward", "Forward", "Forward", "Forward", "Forward", "Up")
        ]
        root = ET.Element("Definitions")
        ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
        cube_grid = ET.SubElement(ship, "CubeGrid")
        ET.SubElement(cube_grid, "GridSizeEnum").text = "Large"
        cubes = ET.SubElement(cube_grid, "CubeBlocks")
        for spec in subtypes:
            block = ET.SubElement(cubes, "MyObjectBuilder_CubeBlock")
            ET.SubElement(block, "SubtypeName").text = spec["subtype"]
            ET.SubElement(block, "BlockOrientation").attrib.update(
                {"Forward": spec["orientation"], "Up": "Up"}
            )
        ET.ElementTree(root).write(self.bp_file, encoding="utf-8", xml_declaration=True)
        result = self.engine.analyze_blueprint(self.bp_file)
        self.assertTrue(any(issue.code == "thruster_imbalance" for issue in result.health_issues))

    def test_known_block_ids_not_empty(self):
        ids = self.engine.db.known_block_ids()
        self.assertIn("LargeBlockArmorBlock", ids)
        self.assertGreater(len(ids), 10)


if __name__ == "__main__":
    unittest.main()

