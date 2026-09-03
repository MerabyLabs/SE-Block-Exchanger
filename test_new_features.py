import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import tempfile
import shutil

from blueprint_converter import BlueprintConverter
from mappings import build_registry


class TestNewCommunityFeatures(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.converter = BlueprintConverter(verbose=False, include_profiles=False)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_blueprint_dir(self, grid_size: str, blocks: list) -> Path:
        bp_dir = self.test_dir / "Test_Blueprint"
        bp_dir.mkdir(parents=True, exist_ok=True)
        
        root = ET.Element("Definitions")
        ship_blueprints = ET.SubElement(root, "ShipBlueprints")
        ship_blueprint = ET.SubElement(ship_blueprints, "ShipBlueprint")
        cube_grid = ET.SubElement(ship_blueprint, "CubeGrid")
        
        grid_size_elem = ET.SubElement(cube_grid, "GridSizeEnum")
        grid_size_elem.text = grid_size
        
        cube_blocks = ET.SubElement(cube_grid, "CubeBlocks")
        for subtype_id in blocks:
            block = ET.SubElement(cube_blocks, "MyObjectBuilder_CubeBlock")
            sub_elem = ET.SubElement(block, "SubtypeId")
            sub_elem.text = subtype_id
            name_elem = ET.SubElement(block, "SubtypeName")
            name_elem.text = subtype_id
            
        tree = ET.ElementTree(root)
        tree.write(bp_dir / "bp.sbc", encoding="utf-8", xml_declaration=True)
        return bp_dir

    def test_dlc_substitution_category(self):
        """Verify the DLC substitution category is loaded and functions correctly."""
        registry = build_registry()
        self.assertTrue(registry.exists("dlc_substitution"))
        
        mapping = registry.build_mapping(enabled_categories=["dlc_substitution"])
        self.assertEqual(mapping["LargeBlockSmallThrustSciFi"], "LargeBlockSmallThrust")
        self.assertEqual(mapping["LargeBlockModularBridgeCockpit"], "LargeBlockCockpit")

    def test_scale_grid_large_to_small(self):
        """Verify blueprint grid scaling from Large to Small results in updated tags and sizes."""
        bp_dir = self._create_blueprint_dir(
            "Large",
            ["LargeBlockArmorBlock", "LargeHeavyBlockArmorSlope"]
        )
        dest_dir, scanned, converted = self.converter.scale_grid_size(bp_dir, "Small")
        
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)
        
        # Verify changes in destination bp.sbc
        tree = ET.parse(dest_dir / "bp.sbc")
        root = tree.getroot()
        
        grid_size_elem = root.find(".//CubeGrid/GridSizeEnum")
        self.assertIsNotNone(grid_size_elem)
        self.assertEqual(grid_size_elem.text, "Small")
        
        subtypes = [elem.text for elem in root.findall(".//SubtypeId")]
        self.assertIn("SmallBlockArmorBlock", subtypes)
        self.assertIn("SmallHeavyBlockArmorSlope", subtypes)

    def test_vanillafy_blueprint(self):
        """Verify vanillafying removes DLC blocks."""
        bp_dir = self._create_blueprint_dir(
            "Large",
            ["LargeBlockOpenSlopedCockpit", "LargeBlockBatteryReskin", "LargeBlockArmorBlock"]
        )
        dest_dir, scanned, converted = self.converter.vanillafy_blueprint(bp_dir)
        self.assertEqual(scanned, 3)
        self.assertEqual(converted, 2)
        
        tree = ET.parse(dest_dir / "bp.sbc")
        root = tree.getroot()
        subtypes = [elem.text for elem in root.findall(".//SubtypeId")]
        self.assertIn("LargeBlockCockpit", subtypes)
        self.assertIn("LargeBlockBatteryBlock", subtypes)

    def test_survival_sanity_prototech(self):
        """Verify the safe same-footprint Prototech gyro downgrade."""
        bp_dir = self._create_blueprint_dir(
            "Large",
            ["LargeBlockPrototechGyro", "LargeBlockPrototechGyro", "LargeBlockArmorBlock"]
        )
        dest_dir, scanned, converted = self.converter.survival_sanity_prototech(bp_dir)
        self.assertEqual(scanned, 3)
        self.assertEqual(converted, 2)

        tree = ET.parse(dest_dir / "bp.sbc")
        root = tree.getroot()
        subtypes = [elem.text for elem in root.findall(".//SubtypeId")]
        self.assertEqual(subtypes.count("LargeBlockGyro"), 2)

    def test_upgrade_to_prototech(self):
        """Verify upgrading standard blocks to Prototech."""
        bp_dir = self._create_blueprint_dir(
            "Large",
            ["LargeBlockGyro", "LargeBlockGyro"]
        )
        dest_dir, scanned, converted = self.converter.upgrade_to_prototech(bp_dir)
        self.assertEqual(scanned, 2)
        self.assertEqual(converted, 2)

        tree = ET.parse(dest_dir / "bp.sbc")
        root = tree.getroot()
        subtypes = [elem.text for elem in root.findall(".//SubtypeId")]
        self.assertEqual(subtypes.count("LargeBlockPrototechGyro"), 2)

    def test_unsupported_type_and_footprint_changes_do_not_write(self):
        bp_dir = self._create_blueprint_dir("Large", ["LargeBlockLargeGenerator", "LargeBlockLargeThrust"])
        before = (bp_dir / "bp.sbc").read_bytes()
        with self.assertRaisesRegex(ValueError, "Object-builder type|footprint"):
            self.converter.upgrade_to_prototech(bp_dir)
        self.assertFalse((bp_dir.parent / f"PROTOTECH_{bp_dir.name}").exists())
        self.assertEqual((bp_dir / "bp.sbc").read_bytes(), before)

    def test_functional_grid_scaling_is_explicitly_unsupported(self):
        bp_dir = self._create_blueprint_dir("Large", ["LargeBlockCockpit"])
        with self.assertRaisesRegex(ValueError, "Scaling blocked"):
            self.converter.scale_grid_size(bp_dir, "Small")
        self.assertFalse((bp_dir.parent / f"SCALED_SMALL_{bp_dir.name}").exists())


if __name__ == "__main__":
    unittest.main()

