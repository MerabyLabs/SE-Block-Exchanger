import unittest
import tempfile
import shutil
from pathlib import Path
import xml.sax.saxutils as saxutils

from blueprint_converter import BlueprintConverter
from blueprint_analytics import BlueprintAnalyticsEngine
from pb_doctor import PBScriptExtractor, PBScriptValidator
from subgrid_engine import SubgridHierarchyParser, GridMatrixVisualizer
import safe_xml


class TestRealWorldSimulation(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.converter = BlueprintConverter(verbose=False)
        self.analytics = BlueprintAnalyticsEngine()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_complex_multigrid_capital_ship(self):
        """Simulates a realistic multi-grid carrier with main hull, rotor turret, and piston elevator."""
        bp_folder = self.test_dir / "Flagship_Yamato"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Flagship_Yamato" />
      <CubeGrids>
        <!-- MAIN HULL (Large Grid) -->
        <CubeGrid>
          <SubtypeName />
          <EntityId>10001</EntityId>
          <CustomName>Yamato Main Hull</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <EntityId>101</EntityId>
              <Min x="0" y="5" z="10" />
              <BlockOrientation Forward="Forward" Up="Up" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorAdvancedStator">
              <SubtypeName>LargeAdvancedStator</SubtypeName>
              <EntityId>102</EntityId>
              <Min x="0" y="6" z="5" />
              <TopBlockId>20001</TopBlockId>
              <BlockOrientation Forward="Forward" Up="Up" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_ExtendedPistonBase">
              <SubtypeName>LargePistonBase</SubtypeName>
              <EntityId>103</EntityId>
              <Min x="0" y="2" z="-10" />
              <TopPartEntityId>30001</TopPartEntityId>
              <BlockOrientation Forward="Forward" Up="Up" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_BatteryBlock">
              <SubtypeName>LargeBlockBatteryBlock</SubtypeName>
              <EntityId>104</EntityId>
              <Min x="0" y="0" z="0" />
              <BlockOrientation Forward="Forward" Up="Up" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <!-- SUBGRID 1: ROTOR TURRET HEAD -->
        <CubeGrid>
          <SubtypeName />
          <EntityId>20000</EntityId>
          <CustomName>Yamato Heavy Turret</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorAdvancedRotor">
              <SubtypeName>LargeAdvancedRotor</SubtypeName>
              <EntityId>20001</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_SmallMissileLauncher">
              <SubtypeName>LargeMissileTurret</SubtypeName>
              <EntityId>20002</EntityId>
              <Min x="0" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <!-- SUBGRID 2: PISTON HANGAR ELEVATOR -->
        <CubeGrid>
          <SubtypeName />
          <EntityId>30000</EntityId>
          <CustomName>Yamato Elevator Subgrid</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_PistonTop">
              <SubtypeName>LargePistonTop</SubtypeName>
              <EntityId>30001</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>30002</EntityId>
              <Min x="0" y="-1" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        # 1. Parse Hierarchy
        structure = SubgridHierarchyParser.parse_file(sbc_file)
        self.assertEqual(structure.total_grids, 3)
        self.assertEqual(structure.total_blocks, 8)
        self.assertIsNotNone(structure.root_node)
        self.assertEqual(structure.root_node.grid_name, "Yamato Main Hull")
        self.assertEqual(len(structure.root_node.children), 2)
        child_names = {c.grid_name for c in structure.root_node.children}
        self.assertIn("Yamato Heavy Turret", child_names)
        self.assertIn("Yamato Elevator Subgrid", child_names)

        # 2. Visualizer Matrix Projection
        matrix_summaries = GridMatrixVisualizer.analyze_grid_matrix(sbc_file)
        self.assertEqual(len(matrix_summaries), 3)
        hull_summary = matrix_summaries[0]
        self.assertIn("Top-Down Projection", hull_summary.ascii_top_down_view)
        self.assertIn("Side Profile Projection", hull_summary.ascii_side_view)

    def test_02_programmable_block_doctor_real_scripts(self):
        """Tests PB Doctor on both production MDK code and malicious/broken scripts."""
        bp_folder = self.test_dir / "Automated_Miner"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        valid_csharp = """public Program()
{
    Runtime.UpdateFrequency = UpdateFrequency.Update10;
}

public void Save()
{
    Storage = "Mining_State_Active";
}

public void Main(string argument, UpdateType updateSource)
{
    Echo("Status: Operational");
    var drills = new List<IMyShipDrill>();
    GridTerminalSystem.GetBlocksOfType(drills);
    foreach (var drill in drills)
    {
        drill.Enabled = true;
    }
}"""

        broken_csharp = """using System.IO;
using System.Threading;

public class BrokenScript
{
    #region UnclosedRegion
    public async void Main()
    {
        File.WriteAllText("C:/exploit.txt", "hacked");
        Thread.Sleep(5000);
        dynamic bad = 10;
    }
}"""

        valid_escaped = saxutils.escape(valid_csharp)
        broken_escaped = saxutils.escape(broken_csharp)

        sbc_content = f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MyProgrammableBlock">
              <SubtypeName>LargeProgrammableBlock</SubtypeName>
              <CustomName>Fleet AI Controller</CustomName>
              <Program>{valid_escaped}</Program>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MyProgrammableBlock">
              <SubtypeName>LargeProgrammableBlock</SubtypeName>
              <CustomName>Corrupted Script Host</CustomName>
              <Program>{broken_escaped}</Program>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        scripts = PBScriptExtractor.extract_from_file(sbc_file)
        self.assertEqual(len(scripts), 2)

        # Validate Valid Script
        rep1 = PBScriptValidator.validate_script(scripts[0].custom_name, scripts[0].program_code)
        self.assertTrue(rep1.is_valid)
        self.assertEqual(rep1.compliance_score, 100)
        self.assertTrue(rep1.has_main_method)
        self.assertTrue(rep1.has_program_constructor)
        self.assertTrue(rep1.has_save_method)

        # Validate Broken Script
        rep2 = PBScriptValidator.validate_script(scripts[1].custom_name, scripts[1].program_code)
        self.assertFalse(rep2.is_valid)
        self.assertLess(rep2.compliance_score, 50)
        rule_ids = {d.rule_id for d in rep2.diagnostics}
        self.assertIn("FORBIDDEN_NAMESPACE", rule_ids)
        self.assertIn("FORBIDDEN_SYNTAX", rule_ids)
        self.assertIn("UNBALANCED_REGIONS", rule_ids)

    def test_03_prosperity_and_contact_dlc_vanillafyer(self):
        """Tests stripping 2024-2026 Prosperity & Contact DLC blocks to pure base game equivalents."""
        bp_folder = self.test_dir / "Prosperity_Cruiser"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockOpenSlopedCockpit</SubtypeName>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockBatteryReskin</SubtypeName>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockSmallThrustSciFi</SubtypeName>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockBatteryReskinOffset</SubtypeName>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        dest, scanned, converted = self.converter.vanillafy_blueprint(bp_folder)
        self.assertEqual(scanned, 5)
        self.assertEqual(converted, 4)

        # Verify modified XML
        tree = safe_xml.parse(dest / "bp.sbc")
        root = tree.getroot()
        subtypes = [safe_xml.get_subtype(b) for b in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")]
        self.assertEqual(subtypes, [
            "LargeBlockCockpit",
            "LargeBlockBatteryBlock",
            "LargeBlockSmallThrust",
            "LargeBlockBatteryBlock",
            "LargeBlockArmorBlock"
        ])

    def test_04_prototech_survival_sanity_and_upgrade(self):
        """Real 1.210 identities: unsafe reactor swaps fail, safe gyros round-trip."""
        from tests.native_fixtures import armor_blueprint
        from se_assets.block_identity import BlockIdentity
        source = armor_blueprint(self.test_dir / "Factorum_Destroyer")
        tree = safe_xml.parse(source)
        cubes = tree.getroot().find(".//CubeBlocks")
        BlockIdentity("HydrogenEngine", "LargePrototechReactor").apply(cubes[0])
        safe_xml.safe_write(tree, source)
        original = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "Object-builder type"):
            self.converter.survival_sanity_prototech(source)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((source.parent.parent / "SURVIVAL_READY_Factorum_Destroyer").exists())

        for cube in cubes:
            BlockIdentity("Gyro", "LargeBlockPrototechGyro").apply(cube)
        safe_xml.safe_write(tree, source)
        sanity, scanned, converted = self.converter.survival_sanity_prototech(source)
        self.assertEqual((scanned, converted), (2, 2))
        restored, scanned, converted = self.converter.upgrade_to_prototech(sanity)
        self.assertEqual((scanned, converted), (2, 2))
        expected = [safe_xml.get_subtype(b) for b in cubes]
        actual = [safe_xml.get_subtype(b) for b in safe_xml.parse(restored / "bp.sbc").findall(".//CubeBlocks/*")]
        self.assertEqual(actual, expected)

    def test_05_grid_rescaler_coordinates_math(self):
        """Scaling changes metres per cell while preserving connected cell coordinates."""
        bp_folder = self.test_dir / "Fighter_Grid"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="2" y="3" z="-4" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        # Large -> Small: cell coordinates are not world metres.
        small_dest, scanned, converted = self.converter.scale_grid_size(bp_folder, "Small")
        tree = safe_xml.parse(small_dest / "bp.sbc")
        root = tree.getroot()
        self.assertEqual(root.find(".//CubeGrid/GridSizeEnum").text, "Small")
        block = root.find(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")
        self.assertEqual(safe_xml.get_subtype(block), "SmallBlockArmorBlock")
        min_elem = block.find("Min")
        self.assertEqual(min_elem.attrib["x"], "2")
        self.assertEqual(min_elem.attrib["y"], "3")
        self.assertEqual(min_elem.attrib["z"], "-4")

        # Round trip keeps negative coordinates exact.
        large_dest, l_scanned, l_converted = self.converter.scale_grid_size(small_dest, "Large")
        l_tree = safe_xml.parse(large_dest / "bp.sbc")
        l_root = l_tree.getroot()
        self.assertEqual(l_root.find(".//CubeGrid/GridSizeEnum").text, "Large")
        l_block = l_root.find(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock")
        self.assertEqual(safe_xml.get_subtype(l_block), "LargeBlockArmorBlock")
        l_min = l_block.find("Min")
        self.assertEqual(l_min.attrib["x"], "2")
        self.assertEqual(l_min.attrib["y"], "3")
        self.assertEqual(l_min.attrib["z"], "-4")

    def test_06_mega_blueprint_stress_and_performance(self):
        """Stress tests parsing, analytics, and conversion on a massive 10,000 block blueprint."""
        bp_folder = self.test_dir / "Mega_Dreadnought"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        blocks_xml = []
        for i in range(10_000):
            st = "LargeBlockArmorBlock" if i % 2 == 0 else "LargeHeavyBlockArmorBlock"
            blocks_xml.append(f'<MyObjectBuilder_CubeBlock><SubtypeName>{st}</SubtypeName><Min x="{i%50}" y="{(i//50)%50}" z="{i//2500}" /></MyObjectBuilder_CubeBlock>')

        sbc_content = f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            {"".join(blocks_xml)}
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        # 1. Test analytics on 10,000 blocks
        report = self.analytics.analyze_blueprint(sbc_file)
        self.assertEqual(report.block_count, 10_000)
        self.assertEqual(report.block_counts["LargeBlockArmorBlock"], 5_000)
        self.assertEqual(report.block_counts["LargeHeavyBlockArmorBlock"], 5_000)

        # 2. Test subgrid hierarchy on 10,000 blocks
        structure = SubgridHierarchyParser.parse_file(sbc_file)
        self.assertEqual(structure.total_blocks, 10_000)

    def test_07_corrupted_and_truncated_xml_resilience(self):
        """Tests that corrupted and truncated XML files raise BlueprintParseError without crashing."""
        corrupted_bp = self.test_dir / "Corrupted_Ship"
        corrupted_bp.mkdir(parents=True)
        sbc_file = corrupted_bp / "bp.sbc"
        sbc_file.write_text("<Definitions><ShipBlueprints><IncompleteTag", encoding="utf-8")

        with self.assertRaises(safe_xml.BlueprintParseError):
            safe_xml.parse(sbc_file)

        # Hierarchy parser returns empty structure on corrupted file instead of unhandled crash
        structure = SubgridHierarchyParser.parse_file(sbc_file)
        self.assertEqual(structure.total_grids, 0)
        self.assertEqual(structure.total_blocks, 0)

        # PB Extractor returns empty list on corrupted file
        scripts = PBScriptExtractor.extract_from_file(sbc_file)
        self.assertEqual(len(scripts), 0)


if __name__ == "__main__":
    unittest.main()
