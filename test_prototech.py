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
        self.assertIn("LargePrototechReactor", PROTOTECH_SUBTYPES)
        self.assertIn("LargeBlockPrototechThruster", PROTOTECH_SUBTYPES)
        self.assertIn("LargeBlockPrototechOxygenGenerator", PROTOTECH_SUBTYPES)


if __name__ == "__main__":
    unittest.main()
