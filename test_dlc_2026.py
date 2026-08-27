"""
Unit tests for 2024-2026 DLC substitution mappings.
"""

import unittest
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS, get_category


class TestDLC2026(unittest.TestCase):
    def test_prosperity_pack_substitutions(self):
        self.assertIn("LargeSlopedCockpit", DLC_TO_BASE_PAIRS)
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeSlopedCockpit"], "LargeBlockCockpit")
        self.assertIn("LargeBatteryBank", DLC_TO_BASE_PAIRS)
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeBatteryBank"], "LargeBlockBatteryBlock")

    def test_contact_and_signal_pack_substitutions(self):
        self.assertIn("ContactRadarAntenna", DLC_TO_BASE_PAIRS)
        self.assertEqual(DLC_TO_BASE_PAIRS["ContactRadarAntenna"], "LargeBlockBeacon")
        self.assertIn("SignalBeacon", DLC_TO_BASE_PAIRS)
        self.assertEqual(DLC_TO_BASE_PAIRS["SignalBeacon"], "LargeBlockBeacon")

    def test_category_valid(self):
        cat = get_category()
        self.assertEqual(cat.name, "dlc_substitution")
        self.assertGreater(len(cat.pairs), 30)


if __name__ == "__main__":
    unittest.main()
