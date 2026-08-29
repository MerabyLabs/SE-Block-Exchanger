"""
Unit tests for Granular Selective Block Exchanging & Custom Rule Overrides.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from blueprint_converter import BlueprintConverter
from blueprint_scanner import BlueprintScanner
import safe_xml
from test_grid_matrix_generator import generate_all_test_grids


class TestSelectiveBlockExchanging(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.grids = generate_all_test_grids(self.test_dir)
        self.scanner = BlueprintScanner()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_scanner_captures_all_subtypes(self):
        bps = self.scanner.scan_blueprints(self.test_dir)
        self.assertEqual(len(bps), 5)
        
        bp_map = {b.name: b for b in bps}
        battleship = bp_map["Battleship_Vindicator"]
        self.assertIn("LargeBlockArmorSlope", battleship.subtype_counts)
        self.assertIn("LargeBlockLargeThrust", battleship.subtype_counts)
        self.assertIn("LargeHeavyBlockArmorBlock", battleship.subtype_counts)

    def test_02_selective_conversion_only_slopes(self):
        """Test converting only LargeBlockArmorSlope to LargeHeavyBlockArmorSlope, leaving LargeBlockArmorBlock intact."""
        converter = BlueprintConverter()
        source_bp = self.grids["Battleship_Vindicator"]

        custom_map = {
            "LargeBlockArmorSlope": "LargeHeavyBlockArmorSlope",
        }
        selected_types = {"LargeBlockArmorSlope"}

        dest_path, scanned, converted = converter.create_selective_converted_blueprint(
            source_bp,
            custom_mapping=custom_map,
            selected_subtypes=selected_types,
        )

        self.assertTrue((dest_path / "bp.sbc").exists())
        self.assertEqual(converted, 1)

        tree = safe_xml.parse(dest_path / "bp.sbc")
        subtypes = [b.find("SubtypeName").text for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/*") if b.find("SubtypeName") is not None]

        # Slope was converted
        self.assertIn("LargeHeavyBlockArmorSlope", subtypes)
        # Flat light armor block was NOT converted
        self.assertIn("LargeBlockArmorBlock", subtypes)

    def test_03_custom_thruster_substitution(self):
        """Test swapping standard thrusters for custom hydrogen thrusters selectively."""
        converter = BlueprintConverter()
        source_bp = self.grids["Battleship_Vindicator"]

        custom_map = {
            "LargeBlockLargeThrust": "LargeBlockLargeHydrogenThrust",
            "LargeBlockSmallThrust": "LargeBlockSmallHydrogenThrust",
        }
        selected_types = {"LargeBlockLargeThrust", "LargeBlockSmallThrust"}

        dest_path, scanned, converted = converter.create_selective_converted_blueprint(
            source_bp,
            custom_mapping=custom_map,
            selected_subtypes=selected_types,
        )

        self.assertEqual(converted, 2)
        tree = safe_xml.parse(dest_path / "bp.sbc")
        subtypes = [b.find("SubtypeName").text for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/*") if b.find("SubtypeName") is not None]
        self.assertIn("LargeBlockLargeHydrogenThrust", subtypes)
        self.assertIn("LargeBlockSmallHydrogenThrust", subtypes)
        self.assertNotIn("LargeBlockLargeThrust", subtypes)

    def test_04_selective_dlc_replacement(self):
        """Test selectively converting only Industrial Assembler to standard vanilla Assembler while keeping Beacon unchanged."""
        converter = BlueprintConverter()
        source_bp = self.grids["Industrial_Excavator"]

        custom_map = {
            "LargeAssemblerIndustrial": "LargeAssembler",
        }
        selected_types = {"LargeAssemblerIndustrial"}

        dest_path, scanned, converted = converter.create_selective_converted_blueprint(
            source_bp,
            custom_mapping=custom_map,
            selected_subtypes=selected_types,
        )

        self.assertEqual(converted, 1)
        tree = safe_xml.parse(dest_path / "bp.sbc")
        subtypes = [b.find("SubtypeName").text for b in tree.getroot().findall(".//CubeGrid/CubeBlocks/*") if b.find("SubtypeName") is not None]
        self.assertIn("LargeAssembler", subtypes)
        self.assertIn("LargeSignalBeacon", subtypes)  # Beacon remained untouched


if __name__ == "__main__":
    unittest.main()
