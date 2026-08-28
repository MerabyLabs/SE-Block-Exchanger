"""Tests for player-facing labels — no Tk required."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from ui.labels import (
    card_status_label,
    category_label,
    convert_button_text,
    convertible_total,
    grouped_category_ids,
    mode_label,
)


class TestCategoryLabel(unittest.TestCase):
    def test_builtin_armor(self):
        self.assertEqual(category_label("armor"), "Armor")

    def test_functional_is_plain_language(self):
        self.assertEqual(category_label("functional"), "Production & power")

    def test_dlc_substitution(self):
        self.assertEqual(category_label("dlc_substitution"), "DLC → vanilla")

    def test_profile_id_is_title_cased(self):
        self.assertEqual(
            category_label("profile:assertive armaments:aa small weapons"),
            "Assertive Armaments · Aa Small Weapons",
        )

    def test_unknown_snake_case(self):
        self.assertEqual(category_label("gyro_upgrades"), "Gyro Upgrades")

    def test_empty(self):
        self.assertEqual(category_label(""), "")


class TestConvertCta(unittest.TestCase):
    def test_no_blueprint(self):
        self.assertEqual(
            convert_button_text(count=0, reverse=False, enabled=False, has_blueprint=False),
            "Select a blueprint to convert",
        )

    def test_nothing_to_convert(self):
        self.assertEqual(
            convert_button_text(count=0, reverse=False, enabled=False, has_blueprint=True),
            "Nothing to convert with current settings",
        )

    def test_forward_count(self):
        self.assertEqual(
            convert_button_text(count=22, reverse=False, enabled=True, has_blueprint=True),
            "Convert 22 blocks to heavy armor",
        )

    def test_singular(self):
        self.assertEqual(
            convert_button_text(count=1, reverse=True, enabled=True, has_blueprint=True),
            "Convert 1 block to light armor",
        )


class TestHelpers(unittest.TestCase):
    def test_mode_label(self):
        self.assertEqual(mode_label(False), "Light → Heavy")
        self.assertEqual(mode_label(True), "Heavy → Light")

    def test_card_status(self):
        self.assertEqual(card_status_label(22, True), "22 ready to convert")
        self.assertEqual(card_status_label(0, True), "Already matches")
        self.assertEqual(card_status_label(0, False), "Not scanned yet")

    def test_convertible_total(self):
        bp = SimpleNamespace(convertible_counts={"A->B": 10, "C->D": 5})
        self.assertEqual(convertible_total(bp), 15)
        self.assertEqual(convertible_total(SimpleNamespace()), 0)

    def test_grouped_ids_put_profiles_last(self):
        groups = grouped_category_ids(
            ["armor", "profile:weaponcore:turrets", "thrusters", "weapons"]
        )
        titles = [title for title, _ in groups]
        self.assertEqual(titles[0], "Core")
        self.assertIn("armor", groups[0][1])
        self.assertEqual(titles[-1], "Installed profiles")
        self.assertEqual(groups[-1][1], ["profile:weaponcore:turrets"])


if __name__ == "__main__":
    unittest.main()
