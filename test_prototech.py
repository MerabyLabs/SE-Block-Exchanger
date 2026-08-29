"""
Unit tests for Prototech mappings and Survival Sanity conversions.
"""

import unittest
from mappings.prototech import (
    get_category,
    get_survival_sanity_mapping,
    VANILLA_TO_PROTOTECH_PAIRS,
    PROTOTECH_SUBTYPES,
)


class TestPrototech(unittest.TestCase):
    def test_category_definition(self):
        cat = get_category()
        self.assertEqual(cat.name, "prototech")
        self.assertIn("endgame", cat.tags)
        self.assertGreater(len(cat.pairs), 10)

    def test_bidirectional_consistency(self):
        sanity_map = get_survival_sanity_mapping()
        self.assertGreaterEqual(len(sanity_map), len(VANILLA_TO_PROTOTECH_PAIRS))
        for v_block, proto_block in VANILLA_TO_PROTOTECH_PAIRS.items():
            self.assertEqual(sanity_map[proto_block], v_block)

    def test_subtypes_contain_generators_and_thrusters(self):
        self.assertIn("LargePrototechGenerator", PROTOTECH_SUBTYPES)
        self.assertIn("LargePrototechThruster", PROTOTECH_SUBTYPES)
        self.assertIn("LargePrototechO2H2", PROTOTECH_SUBTYPES)

    def test_survival_sanity_and_upgrade_create_copies(self):
        import tempfile
        from pathlib import Path

        from blueprint_converter import BlueprintConverter
        from blueprint_fixtures import write_blueprint_dir
        import safe_xml

        converter = BlueprintConverter(include_profiles=False)
        with tempfile.TemporaryDirectory() as tmp:
            source = write_blueprint_dir(
                Path(tmp),
                "ProtoShip",
                ["LargePrototechGenerator", "LargeBlockArmorBlock"],
            )
            dest, scanned, converted = converter.survival_sanity_prototech(source)
            self.assertGreaterEqual(scanned, 2)
            self.assertEqual(converted, 1)
            tree = safe_xml.parse(dest / "bp.sbc")
            subtypes = [
                (b.find("SubtypeName").text or "")
                for b in tree.getroot().findall(".//MyObjectBuilder_CubeBlock")
            ]
            self.assertIn("LargeBlockLargeGenerator", subtypes)
            self.assertIn("LargeBlockArmorBlock", subtypes)

            upgraded, _, up_count = converter.upgrade_to_prototech(source)
            self.assertEqual(up_count, 0)  # source already prototech + armor
            vanilla_source = write_blueprint_dir(
                Path(tmp),
                "VanillaShip",
                ["LargeBlockLargeGenerator"],
            )
            proto_dest, _, proto_count = converter.upgrade_to_prototech(vanilla_source)
            self.assertEqual(proto_count, 1)
            tree = safe_xml.parse(proto_dest / "bp.sbc")
            subtypes = [
                (b.find("SubtypeName").text or "")
                for b in tree.getroot().findall(".//MyObjectBuilder_CubeBlock")
            ]
            self.assertIn("LargePrototechGenerator", subtypes)


if __name__ == "__main__":
    unittest.main()
