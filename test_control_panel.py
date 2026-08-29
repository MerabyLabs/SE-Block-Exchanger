"""Tests for Convert CTA stale-count handling on ControlPanel."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

import customtkinter as ctk

from ui.control_panel import ControlPanel


class TestConvertCountsStale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("DISPLAY is required to construct ControlPanel")
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass  # CTk destroy is racy after tests that already quit the window

    def test_mark_counts_stale_disables_cta_until_refresh(self):
        clicked = {"n": 0}
        panel = ControlPanel(self.app, on_convert=lambda: clicked.__setitem__("n", clicked["n"] + 1))
        bp = SimpleNamespace(
            display_name="Ship",
            grid_size="Large",
            block_count=10,
            light_armor_count=4,
            heavy_armor_count=6,
            convertible_counts={"armor": 4},
        )
        panel.update_details(bp)
        self.assertEqual(str(panel.convert_btn.cget("state")), "normal")
        self.assertEqual(panel.ready_chip.value_label.cget("text"), "4")

        panel.mark_counts_stale()
        self.assertTrue(panel.counts_are_stale)
        self.assertEqual(str(panel.convert_btn.cget("state")), "disabled")
        self.assertEqual(panel.ready_chip.value_label.cget("text"), "…")
        self.assertIn("Updating", panel.convert_btn.cget("text"))

        panel._refresh_cta()
        self.assertEqual(str(panel.convert_btn.cget("state")), "disabled")
        self.assertEqual(panel.ready_chip.value_label.cget("text"), "…")

        panel._convert()
        self.assertEqual(clicked["n"], 0)

        panel.set_convert_ready(enabled=True, count=2, reverse=False, has_blueprint=True)
        self.assertFalse(panel.counts_are_stale)
        self.assertEqual(str(panel.convert_btn.cget("state")), "normal")
        self.assertEqual(panel.ready_chip.value_label.cget("text"), "2")

        panel._convert()
        self.assertEqual(clicked["n"], 1)

    def test_clear_details_unsticks_stale_cta(self):
        panel = ControlPanel(self.app)
        bp = SimpleNamespace(
            display_name="Ship",
            grid_size="Large",
            block_count=10,
            light_armor_count=4,
            heavy_armor_count=6,
            convertible_counts={"armor": 4},
        )
        panel.update_details(bp)
        panel.mark_counts_stale()
        panel.clear_details()
        self.assertFalse(panel.counts_are_stale)
        self.assertEqual(str(panel.convert_btn.cget("state")), "disabled")
        self.assertNotIn("Updating", panel.convert_btn.cget("text"))
        self.assertEqual(panel.ready_chip.value_label.cget("text"), "--")


if __name__ == "__main__":
    unittest.main()
