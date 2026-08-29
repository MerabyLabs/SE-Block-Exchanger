"""Tests for isolating a subgrid on the ship map."""

from __future__ import annotations

import os
import unittest

import customtkinter as ctk

from ui.widgets.ship_canvas import ShipCanvas, VoxelBlock


def _block(x: int, z: int, grid: str, y: int = 0) -> VoxelBlock:
    return VoxelBlock(
        x=x,
        y=y,
        z=z,
        subtype="LargeBlockArmorBlock",
        grid_name=grid,
        is_subgrid=grid != "Main",
    )


class TestShipCanvasBounds(unittest.TestCase):
    def test_bounds_for_uses_only_supplied_blocks(self):
        hull = [_block(0, 0, "Main"), _block(20, 10, "Main")]
        turret = [_block(100, 80, "Turret")]
        min_c, max_c = ShipCanvas.bounds_for(hull + turret)
        self.assertEqual(min_c, (0, 0, 0))
        self.assertEqual(max_c, (100, 0, 80))
        min_c, max_c = ShipCanvas.bounds_for(turret)
        self.assertEqual(min_c, (100, 0, 80))
        self.assertEqual(max_c, (100, 0, 80))


class TestShipCanvasIsolateFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("DISPLAY is required to construct ShipCanvas")
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass  # CTk destroy is racy after tests that already quit the window

    def test_filter_fits_and_centers_the_selected_grid(self):
        canvas = ShipCanvas(self.app)
        canvas.load_structure_data(
            [
                _block(0, 0, "Main"),
                _block(40, 40, "Main"),
                _block(200, 180, "Turret"),
            ]
        )
        full_scale = canvas.scale
        min_c, max_c = canvas.bounds_for(canvas._visible_blocks())
        self.assertEqual(min_c, (0, 0, 0))
        self.assertEqual(max_c, (200, 0, 180))

        canvas.filter_by_grid("Turret")
        isolated_scale = canvas.scale
        min_c, max_c = canvas.bounds_for(canvas._visible_blocks())
        self.assertEqual(min_c, (200, 0, 180))
        self.assertEqual(max_c, (200, 0, 180))
        self.assertGreater(isolated_scale, full_scale)
        self.assertEqual(canvas.pan_x, 0.0)
        self.assertEqual(canvas.pan_y, 0.0)

        canvas.filter_by_grid(None)
        self.assertEqual(canvas.bounds_for(canvas._visible_blocks())[1], (200, 0, 180))
        self.assertLess(canvas.scale, isolated_scale)


if __name__ == "__main__":
    unittest.main()
