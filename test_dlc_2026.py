"""
Unit tests for 2024-2026 DLC substitution mappings.
"""

import unittest
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS, get_category


class TestDLC2026(unittest.TestCase):
    def test_prosperity_pack_substitutions(self):
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeBlockOpenSlopedCockpit"], "LargeBlockCockpit")
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeBlockBatteryReskin"], "LargeBlockBatteryBlock")

    def test_contact_and_signal_pack_substitutions(self):
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeGatlingTurretReskin"], "LargeGatlingTurret/")
        self.assertEqual(DLC_TO_BASE_PAIRS["LargeMissileTurretReskin"], "LargeMissileTurret/")
        self.assertNotIn("ContactRadarAntenna", DLC_TO_BASE_PAIRS)

    def test_category_valid(self):
        cat = get_category()
        self.assertEqual(cat.name, "dlc_substitution")
        from se_assets.compatibility import baseline_catalog, validate_mapping
        valid, disabled = validate_mapping(cat.pairs, baseline_catalog())
        self.assertGreater(len(valid), 15)
        self.assertTrue(disabled)  # Footprint-changing alternatives stay unavailable.


if __name__ == "__main__":
    unittest.main()
