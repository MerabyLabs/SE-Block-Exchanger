"""Tests for Space Engineers 2 readiness scoring."""

from __future__ import annotations

import unittest

from blueprint_analytics import compute_se2_readiness


class TestSE2Readiness(unittest.TestCase):
    def test_vanilla_grid_is_optimal(self):
        result = compute_se2_readiness(
            {"LargeBlockArmorBlock": 40, "LargeBlockCockpit": 1, "LargeBlockBatteryBlock": 2}
        )
        self.assertEqual(result.score, 100)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertEqual(result.dlc_count, 0)
        self.assertEqual(result.script_count, 0)
        self.assertEqual(result.subgrid_count, 0)

    def test_dlc_and_scripts_reduce_score(self):
        result = compute_se2_readiness(
            {
                "LargeBlockSmallThrustSciFi": 3,
                "MyProgrammableBlock": 2,
                "LargeAdvancedRotor": 1,
            }
        )
        self.assertEqual(result.dlc_count, 3)
        self.assertEqual(result.script_count, 2)
        self.assertEqual(result.subgrid_count, 1)
        self.assertEqual(result.score, 50)
        self.assertEqual(result.status, "COMPLEX")

    def test_score_has_floor_and_fragile_status(self):
        result = compute_se2_readiness(
            {
                "LargeBlockSmallThrustSciFi": 20,
                "MyProgrammableBlock": 10,
                "MotorStator": 10,
                "PistonBase": 10,
                "LargeHinge": 10,
            }
        )
        self.assertEqual(result.score, 20)
        self.assertEqual(result.status, "FRAGILE")

    def test_complex_threshold(self):
        result = compute_se2_readiness({"MotorRotor": 4, "MyProgrammableBlock": 1})
        self.assertEqual(result.score, 60)
        self.assertEqual(result.status, "STABLE")


if __name__ == "__main__":
    unittest.main()
