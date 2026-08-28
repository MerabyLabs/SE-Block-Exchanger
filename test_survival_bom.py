"""
Unit tests for Survival BOM and TIM/Isy LCD string generators.
"""

import unittest
from blueprint_analytics import BlueprintAnalyticsEngine


class TestSurvivalBOM(unittest.TestCase):
    def test_01_refinery_duration_calculation(self):
        ores = {"Iron": 2000.0, "Cobalt": 300.0, "Uranium": 4.0}
        times = BlueprintAnalyticsEngine.calculate_refining_time(ores, refinery_speed_mult=1.0)
        # Iron: 2000 / 20 = 100s
        self.assertEqual(times["Iron"], 100.0)
        # Cobalt: 300 / 0.3 = 1000s
        self.assertEqual(times["Cobalt"], 1000.0)
        # Uranium: 4 / 0.004 = 1000s
        self.assertEqual(times["Uranium"], 1000.0)

    def test_02_tim_and_isy_configs(self):
        components = {"Steel Plate": 500, "Interior Plate": 200, "Thruster": 20}
        tim_cfg = BlueprintAnalyticsEngine.generate_tim_config(components)
        self.assertIn("Component:SteelPlate:500", tim_cfg)
        self.assertIn("Component:InteriorPlate:200", tim_cfg)

        isy_cfg = BlueprintAnalyticsEngine.generate_isy_config(components)
        self.assertIn("Steel Plate=500", isy_cfg)
        self.assertIn("Interior Plate=200", isy_cfg)


if __name__ == "__main__":
    unittest.main()
