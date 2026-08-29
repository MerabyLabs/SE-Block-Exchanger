"""
Unit tests for Engine Compatibility & Future-Proofing Framework (SE1 & SE2).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine_compat import (
    BlueprintFormat,
    EngineVersionDetector,
    GameEngine,
    SE1_TO_SE2_TRANSLATION_TABLE,
    SE2_TO_SE1_TRANSLATION_TABLE,
    SE2MigrationBridge,
)
import safe_xml


class TestEngineCompat(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bidirectional_translation_table(self):
        self.assertGreater(len(SE1_TO_SE2_TRANSLATION_TABLE), 10)
        for se1, se2 in SE1_TO_SE2_TRANSLATION_TABLE.items():
            self.assertEqual(SE2_TO_SE1_TRANSLATION_TABLE[se2], se1)

    def test_format_and_engine_detection_se1(self):
        se1_folder = self.test_dir / "SE1_Frigate"
        se1_folder.mkdir(parents=True)
        sbc_file = se1_folder / "bp.sbc"
        sbc_file.write_text(
            '<?xml version="1.0"?><Definitions><ShipBlueprints><ShipBlueprint><CubeGrids><CubeGrid><GridSizeEnum>Large</GridSizeEnum><CubeBlocks><MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock></CubeBlocks></CubeGrid></CubeGrids></ShipBlueprint></ShipBlueprints></Definitions>',
            encoding="utf-8"
        )

        fmt = EngineVersionDetector.detect_file_format(se1_folder)
        self.assertEqual(fmt, BlueprintFormat.SE1_SBC_XML)

        engine = EngineVersionDetector.detect_engine(se1_folder)
        self.assertEqual(engine, GameEngine.SPACE_ENGINEERS_1)

        report = EngineVersionDetector.inspect_compatibility(se1_folder)
        self.assertTrue(report.is_se1_compatible)
        self.assertFalse(report.is_se2_compatible)
        self.assertTrue(report.se2_migratable)

    def test_format_and_engine_detection_se2(self):
        se2_folder = self.test_dir / "SE2_Cruiser"
        se2_folder.mkdir(parents=True)
        json_file = se2_folder / "blueprint.json"
        json_file.write_text(
            json.dumps({"engine_target": "SE2_VRAGE3", "grids": []}),
            encoding="utf-8"
        )

        fmt = EngineVersionDetector.detect_file_format(se2_folder)
        self.assertEqual(fmt, BlueprintFormat.SE2_JSON)

        engine = EngineVersionDetector.detect_engine(se2_folder)
        self.assertEqual(engine, GameEngine.SPACE_ENGINEERS_2)

        report = EngineVersionDetector.inspect_compatibility(se2_folder)
        self.assertFalse(report.is_se1_compatible)
        self.assertTrue(report.is_se2_compatible)

    def test_migrate_se1_to_se2_and_back(self):
        se1_folder = self.test_dir / "Original_Carrier"
        se1_folder.mkdir(parents=True)
        sbc_file = se1_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Original_Carrier" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Carrier Hull</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <Min x="0" y="1" z="5" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_BatteryBlock">
              <SubtypeName>LargeBlockBatteryBlock</SubtypeName>
              <Min x="0" y="-1" z="2" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        # 1. Forward Migration: SE1 -> SE2
        dest_se2, scanned_se2, converted_se2 = SE2MigrationBridge.migrate_se1_to_se2(se1_folder)
        self.assertTrue((dest_se2 / "blueprint.json").exists())
        self.assertEqual(scanned_se2, 3)
        self.assertEqual(converted_se2, 3)

        with open(dest_se2 / "blueprint.json", "r", encoding="utf-8") as f:
            se2_data = json.load(f)
        self.assertEqual(se2_data["engine_target"], "SE2_VRAGE3")
        self.assertEqual(len(se2_data["grids"]), 1)
        blocks = se2_data["grids"][0]["blocks"]
        self.assertEqual(blocks[0]["subtype"], "VR3_Large_Armor_Cube")
        self.assertEqual(blocks[1]["subtype"], "VR3_Large_Cockpit_Enclosed")
        self.assertEqual(blocks[2]["subtype"], "VR3_Large_Battery_Standard")

        # 2. Backward Translation: SE2 -> SE1
        dest_se1, scanned_se1, converted_se1 = SE2MigrationBridge.migrate_se2_to_se1(dest_se2)
        self.assertTrue((dest_se1 / "bp.sbc").exists())
        self.assertEqual(scanned_se1, 3)
        self.assertEqual(converted_se1, 3)

        tree = safe_xml.parse(dest_se1 / "bp.sbc")
        root = tree.getroot()
        subtypes = [b.find("SubtypeName").text for b in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")]
        self.assertIn("LargeBlockArmorBlock", subtypes)
        self.assertIn("LargeBlockCockpit", subtypes)
        self.assertIn("LargeBlockBatteryBlock", subtypes)


if __name__ == "__main__":
    unittest.main()
