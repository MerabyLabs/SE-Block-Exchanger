"""
Exhaustive User Workflow Simulation & Real-World Edge Case Test Suite.
Tests every user journey and edge case across all subsystems.
"""

import unittest
import tempfile
import shutil
import zipfile
from pathlib import Path

from blueprint_scanner import BlueprintScanner
from blueprint_converter import BlueprintConverter
from blueprint_analytics import BlueprintAnalyticsEngine
from mapping_profiles import ProfileManager
from pb_doctor import PBScriptExtractor, PBScriptValidator
from subgrid_engine import SubgridHierarchyParser, GridMatrixVisualizer
from workshop_sync import SteamWorkshopFetcher, ModioFetcher
from app_settings import AppSettings
import safe_xml


class TestUserWorkflowsExhaustive(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.converter = BlueprintConverter(verbose=False)
        self.analytics = BlueprintAnalyticsEngine()
        self.profile_mgr = ProfileManager(profile_dir=self.test_dir / "profiles")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_workflow_01_scanner_unicode_and_weird_folders(self):
        uni_bp = self.test_dir / "Valkyrie_123"
        uni_bp.mkdir(parents=True)
        sbl = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Unicode_Ship" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Russian_Flagship</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        (uni_bp / "bp.sbc").write_text(sbl, encoding="utf-8")

        empty_dir = self.test_dir / "Empty_Folder"
        empty_dir.mkdir(parents=True)

        thumb_only = self.test_dir / "Thumb_Only"
        thumb_only.mkdir(parents=True)
        (thumb_only / "thumb.png").write_bytes(b"PNG_BYTES")

        scanner = BlueprintScanner()
        bps = scanner.scan_directory(self.test_dir)
        bp_names = [b.name for b in bps]
        self.assertIn("Valkyrie_123", bp_names)
        self.assertNotIn("Empty_Folder", bp_names)
        self.assertNotIn("Thumb_Only", bp_names)

    def test_workflow_02_all_armor_shapes_conversion(self):
        bp_folder = self.test_dir / "Armor_Stress"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        armor_blocks = [
            "LargeBlockArmorBlock", "LargeBlockArmorSlope", "LargeBlockArmorCorner",
            "LargeBlockArmorCornerInv", "LargeHalfArmorBlock", "LargeHalfSlopeArmorBlock",
            "LargeBlockArmorRoundSlope", "LargeBlockArmorRoundCorner", "LargeBlockArmorRoundCornerInv",
            "LargeBlockArmorSlopedCorner", "LargeBlockArmorSlopedCornerBase", "LargeBlockArmorSlopedCornerTip",
            "LargeBlockArmorHalfSlopedCornerBase", "LargeBlockArmorHalfSlopedCornerTip"
        ]

        blocks_xml = "\n".join(
            f'<MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock"><SubtypeName>{b}</SubtypeName><Min x="{i}" y="0" z="0" /></MyObjectBuilder_CubeBlock>'
            for i, b in enumerate(armor_blocks)
        )

        sbc_file.write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Armor_Stress" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Armor_Grid</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            {blocks_xml}
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>""", encoding="utf-8")

        dest_path, scanned, converted = self.converter.create_converted_blueprint(sbc_file)
        self.assertGreater(converted, 0)

        text_after = (dest_path / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeHeavyBlockArmorSlope", text_after)
        self.assertIn("LargeHeavyBlockArmorCorner", text_after)

    def test_workflow_03_multi_category_profiles(self):
        from mapping_profiles import MappingProfile
        from mappings.registry import MappingCategory
        cat = MappingCategory(
            name="custom_mod",
            description="Custom Mod",
            pairs={"CustomModShield": "VanillaHeavyArmor"}
        )
        profile = MappingProfile(
            name="Combat_Profile",
            author="Meraby",
            version="1.0.0",
            description="Combat standard",
            game_version="1.204",
            categories=[cat]
        )
        self.profile_mgr.save_profile(profile)

        loaded = self.profile_mgr.get_profile("Combat_Profile")
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.categories), 1)
        self.assertIn("CustomModShield", loaded.categories[0].pairs)

        export_path = self.test_dir / "Combat_Profile.sebx-profile"
        self.profile_mgr.export_profile("Combat_Profile", export_path)
        self.assertTrue(export_path.exists())

        imported_prof, imported_path = self.profile_mgr.import_profile(export_path)
        self.assertEqual(imported_prof.name, "Combat_Profile")
        self.assertTrue(imported_path.exists())

    def test_workflow_04_vanillafyer_all_dlcs(self):
        bp_folder = self.test_dir / "DLC_Flagship"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        dlc_blocks = [
            ("Cockpit", "LargeBlockOpenSlopedCockpit"), ("Cockpit", "LargeBlockModularBridgeCockpit"),
            ("Thrust", "LargeBlockSmallThrustSciFi"), ("BatteryBlock", "LargeBlockBatteryReskin"),
            ("LargeGatlingTurret", "LargeGatlingTurretReskin"), ("LargeMissileTurret", "LargeMissileTurretReskin")
        ]

        blocks_xml = "\n".join(
            f'<MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_{kind}"><SubtypeName>{b}</SubtypeName><Min x="{i*5}" y="0" z="0" /></MyObjectBuilder_CubeBlock>'
            for i, (kind, b) in enumerate(dlc_blocks)
        )

        sbc_file.write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="DLC_Flagship" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>DLC_Grid</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            {blocks_xml}
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>""", encoding="utf-8")

        dest_path, scanned, converted = self.converter.vanillafy_blueprint(sbc_file)
        self.assertEqual(converted, len(dlc_blocks))

        text_after = (dest_path / "bp.sbc").read_text(encoding="utf-8")
        self.assertIn("LargeBlockCockpit", text_after)
        self.assertIn("LargeBlockSmallThrust", text_after)
        self.assertIn("MyObjectBuilder_LargeGatlingTurret", text_after)
        self.assertNotIn("TurretReskin", text_after)
        self.assertIn("LargeBlockBatteryBlock", text_after)

    def test_workflow_05_prototech_survival_sanity_and_upgrade(self):
        """Typed Prototech gyros preserve position, orientation and entity IDs."""
        from tests.native_fixtures import armor_blueprint
        from se_assets.block_identity import BlockIdentity
        source = armor_blueprint(self.test_dir / "Prototech_Ship")
        tree = safe_xml.parse(source)
        original_blocks = tree.getroot().findall(".//CubeBlocks/*")
        for block in original_blocks:
            BlockIdentity("Gyro", "LargeBlockPrototechGyro").apply(block)
        safe_xml.safe_write(tree, source)
        original = source.read_bytes()
        dest_sanity, scanned, converted = self.converter.survival_sanity_prototech(source)
        self.assertEqual((scanned, converted), (2, 2))
        dest_upgrade, _, converted_up = self.converter.upgrade_to_prototech(dest_sanity)
        self.assertEqual(converted_up, 2)
        restored = safe_xml.parse(dest_upgrade / "bp.sbc").findall(".//CubeBlocks/*")
        for before, after in zip(original_blocks, restored):
            self.assertEqual(safe_xml.get_subtype(before), safe_xml.get_subtype(after))
            self.assertEqual(before.findtext("EntityId"), after.findtext("EntityId"))
            self.assertEqual(before.find("Min").attrib, after.find("Min").attrib)
            self.assertEqual(before.find("BlockOrientation").attrib, after.find("BlockOrientation").attrib)
        self.assertEqual(source.read_bytes(), original)

    def test_workflow_06_pb_doctor_multigrid_and_syntax(self):
        bp_folder = self.test_dir / "Scripted_Drone"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        valid_script = "public Program() { Runtime.UpdateFrequency = UpdateFrequency.Update10; } public void Main(string arg) { Echo(arg); }"
        broken_script = 'public void Main() { System.IO.File.Delete("config.txt"); dynamic bad = 1; #region Unclosed'
        broken_escaped = broken_script.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        sbc_file.write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Scripted_Drone" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Drone Main</CustomName>
          <GridSizeEnum>Small</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MyProgrammableBlock">
              <SubtypeName>SmallProgrammableBlock</SubtypeName>
              <CustomName>Auto-Miner PB</CustomName>
              <Program>{valid_script}</Program>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MyProgrammableBlock">
              <SubtypeName>SmallProgrammableBlock</SubtypeName>
              <CustomName>Exploit PB</CustomName>
              <Program>{broken_escaped}</Program>
              <Min x="0" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>""", encoding="utf-8")

        scripts = PBScriptExtractor.extract_from_file(sbc_file)
        self.assertEqual(len(scripts), 2)

        rep_valid = PBScriptValidator.validate_script(scripts[0].program_code)
        self.assertTrue(rep_valid.is_valid)
        self.assertEqual(rep_valid.compliance_score, 100)

        rep_broken = PBScriptValidator.validate_script(scripts[1].program_code)
        self.assertFalse(rep_broken.is_valid)
        self.assertGreater(rep_broken.error_count, 0)
        codes = [i.rule_id for i in rep_broken.diagnostics]
        self.assertIn("FORBIDDEN_NAMESPACE", codes)
        self.assertIn("FORBIDDEN_SYNTAX", codes)

    def test_workflow_07_subgrid_hierarchy_and_matrix_views(self):
        bp_folder = self.test_dir / "Complex_Walker"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Complex_Walker" />
      <CubeGrids>
        <CubeGrid>
          <EntityId>1000</EntityId>
          <CustomName>Walker Body</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <Min x="0" y="2" z="5" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorAdvancedStator">
              <SubtypeName>LargeAdvancedStator</SubtypeName>
              <EntityId>1001</EntityId>
              <TopBlockId>2000</TopBlockId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <CubeGrid>
          <EntityId>2000</EntityId>
          <CustomName>Walker Leg Subgrid</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="-5" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        structure = SubgridHierarchyParser.parse_file(sbc_file)
        self.assertEqual(structure.total_grids, 2)
        self.assertEqual(len(structure.mechanical_links), 1)

        projections = GridMatrixVisualizer.analyze_grid_matrix(sbc_file)
        self.assertEqual(len(projections), 2)
        body_proj = projections[0]
        self.assertIn("Top-Down Projection", body_proj.ascii_top_down_view)
        self.assertIn("Side Profile Projection", body_proj.ascii_side_view)

    def test_workflow_08_grid_rescaling_math(self):
        bp_folder = self.test_dir / "Rescale_Test"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Rescale_Test" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Large Ship</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="3" y="-2" z="10" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        dest_small, scanned, converted = self.converter.scale_grid_size(sbc_file, target_size="Small")
        self.assertEqual(converted, 1)

        tree = safe_xml.parse(dest_small / "bp.sbc")
        root = tree.getroot()
        grid = root.find(".//CubeGrid")
        self.assertEqual(grid.find("GridSizeEnum").text, "Small")
        block = root.find(".//MyObjectBuilder_CubeBlock")
        min_elem = block.find("Min")
        self.assertEqual(int(min_elem.attrib["x"]), 3)
        self.assertEqual(int(min_elem.attrib["y"]), -2)
        self.assertEqual(int(min_elem.attrib["z"]), 10)

    def test_workflow_09_workshop_and_modio_parsing(self):
        self.assertEqual(SteamWorkshopFetcher.parse_workshop_id("123456789"), "123456789")
        self.assertEqual(SteamWorkshopFetcher.parse_workshop_id("https://steamcommunity.com/sharedfiles/filedetails/?id=987654321"), "987654321")
        self.assertIsNone(SteamWorkshopFetcher.parse_workshop_id("https://google.com"))

        self.assertEqual(ModioFetcher.parse_modio_url("https://mod.io/g/spaceengineers/m/battle-cruiser-v2"), "battle-cruiser-v2")
        self.assertIsNone(ModioFetcher.parse_modio_url("https://invalid.com"))

        zip_file = self.test_dir / "sample_blueprint.zip"
        with zipfile.ZipFile(zip_file, "w") as z:
            z.writestr("bp.sbc", "<Definitions><ShipBlueprints/></Definitions>")

        target_dir = self.test_dir / "Extracted_Modio"
        res_path = ModioFetcher.extract_zip_blueprint(zip_file, target_dir)
        self.assertIsNotNone(res_path)
        self.assertTrue((target_dir / "bp.sbc").exists())

    def test_workflow_10_analytics_and_health_fixes(self):
        bp_folder = self.test_dir / "Mining_Barge"
        bp_folder.mkdir(parents=True)
        sbc_file = bp_folder / "bp.sbc"

        sbc_content = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Mining_Barge" />
      <CubeGrids>
        <CubeGrid>
          <CustomName>Mining Barge Hull</CustomName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""
        sbc_file.write_text(sbc_content, encoding="utf-8")

        report = self.analytics.analyze_blueprint(sbc_file)
        self.assertEqual(report.block_count, 1)
        self.assertGreater(report.mass_total, 0)
        self.assertGreater(report.pcu_total, 0)
        self.assertIn("SteelPlate", report.component_totals)
        self.assertIn("Iron Ore", report.ore_totals)

        issue_codes = [iss.code for iss in report.health_issues]
        self.assertIn("missing_power", issue_codes)
        self.assertIn("missing_control", issue_codes)

        fix_res = self.analytics.apply_fix(sbc_file, "add_power")
        self.assertTrue(fix_res)
        text_fixed = sbc_file.read_text(encoding="utf-8")
        self.assertIn("LargeBlockBatteryBlock", text_fixed)

    def test_workflow_11_settings_persistence(self):
        from app_settings import SettingsStore
        settings_file = self.test_dir / "settings.json"
        store = SettingsStore(path=settings_file)
        settings = AppSettings(appearance_mode="Dark", enabled_categories=["armor", "thrusters"])
        store.save(settings)

        settings2 = store.load()
        self.assertEqual(settings2.appearance_mode, "Dark")
        self.assertEqual(settings2.enabled_categories, ["armor", "thrusters"])

        settings_file.write_text("{INVALID_JSON", encoding="utf-8")
        settings_recovered = store.load()
        self.assertIsNotNone(settings_recovered.appearance_mode)


if __name__ == "__main__":
    unittest.main()
