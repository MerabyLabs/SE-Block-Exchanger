"""Tests for theme helpers and platform-specific drag-and-drop."""

from __future__ import annotations

import os
import sys
import unittest

import customtkinter as ctk

from ui.dragdrop_windows import WindowsFileDropTarget
from ui.theme import TacticalTheme
from ui.widgets.toast import ToastManager


class TestAppShutdown(unittest.TestCase):
    def test_window_defines_close_handler(self):
        from ui.app import TacticalCommandCenter

        self.assertTrue(callable(TacticalCommandCenter._on_close))

    def test_windows_close_messages_are_detected(self):
        from ui.dragdrop_windows import (
            SC_CLOSE,
            WM_CLOSE,
            WM_DROPFILES,
            WM_SYSCOMMAND,
            _is_close_message,
        )

        self.assertTrue(_is_close_message(WM_CLOSE, 0))
        self.assertTrue(_is_close_message(WM_SYSCOMMAND, SC_CLOSE))
        self.assertTrue(_is_close_message(WM_SYSCOMMAND, SC_CLOSE | 0x0002))
        self.assertFalse(_is_close_message(WM_DROPFILES, 0))
        self.assertFalse(_is_close_message(WM_SYSCOMMAND, 0xF030))  # SC_MAXIMIZE

    def test_on_close_destroys_window_and_exits(self):
        if not os.environ.get("DISPLAY"):
            self.skipTest("DISPLAY is required to construct the main window")
        from unittest.mock import patch

        from ui.app import TacticalCommandCenter

        with patch("ui.app.os._exit") as mock_exit:
            app = TacticalCommandCenter()
            try:
                app.update_idletasks()
                app._on_close()
                mock_exit.assert_called_with(0)
                self.assertTrue(app._closing)
            except Exception:
                try:
                    app.destroy()
                except Exception:
                    pass  # window may already be destroyed by _on_close
                raise


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

    def test_drop_callback_errors_are_logged(self):
        from io import StringIO
        from unittest.mock import patch

        def boom(_paths):
            raise RuntimeError("drop failed")

        target = WindowsFileDropTarget(tk_window=None, on_files=boom)
        with patch("sys.stderr", new_callable=StringIO) as err:
            target._invoke_drop_callback([r"C:\ship"])
        text = err.getvalue()
        self.assertIn("drop callback failed", text)
        self.assertIn("RuntimeError", text)


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
            pass  # CTk destroy is racy after tests that already quit the window

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

    def test_dismiss_all_hides_overlay(self):
        manager = ToastManager(self.app)
        manager.toast("One", duration=0)
        manager.toast("Two", duration=0)
        self.app.update_idletasks()
        manager.dismiss_all()
        self.app.update_idletasks()
        self.assertFalse(manager.visible)
        self.assertEqual(manager._toasts, [])


class TestGridHierarchyTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("DISPLAY is required to construct GridHierarchyView")
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass  # CTk destroy is racy after tests that already quit the window

    def test_canvas_uses_theme_background(self):
        from ui.widgets.grid_tree import GridHierarchyView

        view = GridHierarchyView(self.app)
        self.assertEqual(str(view.canvas.cget("bg")).lower(), TacticalTheme.BG_DARK.lower())


if __name__ == "__main__":
    unittest.main()
