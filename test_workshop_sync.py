"""
Unit tests for Steam Workshop and Mod.io sync utilities.
"""

import unittest
from workshop_sync import SteamWorkshopFetcher, ModioFetcher


class TestWorkshopSync(unittest.TestCase):
    def test_parse_steam_id(self):
        self.assertEqual(SteamWorkshopFetcher.parse_workshop_id("123456789"), "123456789")
        self.assertEqual(
            SteamWorkshopFetcher.parse_workshop_id("https://steamcommunity.com/sharedfiles/filedetails/?id=987654321"),
            "987654321"
        )
        self.assertEqual(
            SteamWorkshopFetcher.parse_workshop_id("steamcommunity.com/sharedfiles/filedetails/?id=55555&searchtext="),
            "55555"
        )

    def test_parse_modio_url(self):
        self.assertEqual(
            ModioFetcher.parse_modio_url("https://mod.io/g/spaceengineers/m/flagship-cruiser"),
            "flagship-cruiser"
        )


if __name__ == "__main__":
    unittest.main()
