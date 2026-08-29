"""Tests for Subgrids tab render caching on PreviewPanel."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

import customtkinter as ctk

from ui.preview_panel import PreviewPanel


class TestSubgridRenderCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("DISPLAY is required to construct PreviewPanel")
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass  # CTk destroy is racy after tests that already quit the window

    def test_render_subgrids_skips_rebuild_when_data_unchanged(self):
        panel = PreviewPanel(self.app)
        panel._pending_voxels = [
            {
                "x": 0,
                "y": 0,
                "z": 0,
                "subtype": "LargeBlockArmorBlock",
                "grid_name": "Main",
            }
        ]
        panel.hierarchy_view.render = MagicMock()
        panel.ship_canvas.load_structure_data = MagicMock()
        panel.ship_canvas.refresh = MagicMock()
        panel.after_idle = lambda callback: callback()

        panel._render_subgrids()
        panel.ship_canvas.load_structure_data.assert_called_once()
        panel.hierarchy_view.render.assert_called_once()

        panel._render_subgrids()
        panel.ship_canvas.load_structure_data.assert_called_once()
        panel.hierarchy_view.render.assert_called_once()
        panel.ship_canvas.refresh.assert_called()

        panel._subgrids_rendered_for = None
        panel._render_subgrids()
        self.assertEqual(panel.ship_canvas.load_structure_data.call_count, 2)
        self.assertEqual(panel.hierarchy_view.render.call_count, 2)


if __name__ == "__main__":
    unittest.main()
