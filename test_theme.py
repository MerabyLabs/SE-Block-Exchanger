"""Tests for theme helpers and platform-specific drag-and-drop."""

from __future__ import annotations

import sys
import unittest

from ui.theme import TacticalTheme
from ui.dragdrop_windows import WindowsFileDropTarget


class TestTheme(unittest.TestCase):
    def test_normalize_appearance_mode(self):
        self.assertEqual(TacticalTheme.normalize_appearance_mode("dark"), "Dark")
        self.assertEqual(TacticalTheme.normalize_appearance_mode("LIGHT"), "Light")
        self.assertEqual(TacticalTheme.normalize_appearance_mode("system"), "System")
        self.assertEqual(TacticalTheme.normalize_appearance_mode(""), "System")
        self.assertEqual(TacticalTheme.normalize_appearance_mode("neon"), "System")


class TestDragDrop(unittest.TestCase):
    def test_enable_is_false_off_windows(self):
        if sys.platform.startswith("win"):
            self.skipTest("Windows drop target requires a live HWND")
        target = WindowsFileDropTarget(tk_window=None, on_files=lambda paths: None)
        self.assertFalse(target.enable())
        target.disable()
        self.assertFalse(target.enabled)


if __name__ == "__main__":
    unittest.main()
