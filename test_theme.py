"""Tests for theme helpers and platform-specific drag-and-drop."""

from __future__ import annotations

import os
import sys
import unittest

import customtkinter as ctk

from ui.dragdrop_windows import WindowsFileDropTarget
from ui.theme import TacticalTheme
from ui.widgets.toast import ToastManager


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


class TestToastManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("DISPLAY is required for toast overlay tests")
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_overlay_is_hidden_until_a_toast_is_shown(self):
        manager = ToastManager(self.app)
        self.app.update_idletasks()
        self.assertFalse(manager.visible)
        self.assertEqual(manager._container.place_info(), {})

        toast = manager.toast("Conversion complete", level="success", duration=0)
        self.app.update_idletasks()
        self.assertTrue(manager.visible)
        self.assertTrue(manager._container.place_info())

        toast.dismiss()
        self.app.update_idletasks()
        self.assertFalse(manager.visible)
        self.assertEqual(manager._container.place_info(), {})
        self.assertEqual(manager._toasts, [])

    def test_overlay_stays_until_last_toast_dismisses(self):
        manager = ToastManager(self.app)
        first = manager.toast("First", duration=0)
        second = manager.toast("Second", duration=0)
        self.app.update_idletasks()
        self.assertTrue(manager.visible)

        first.dismiss()
        self.app.update_idletasks()
        self.assertTrue(manager.visible)

        second.dismiss()
        self.app.update_idletasks()
        self.assertFalse(manager.visible)


if __name__ == "__main__":
    unittest.main()
