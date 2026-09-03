import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Configure TCL/TK libraries for headless test runner
tcl_dir = os.path.join(sys.base_prefix, "tcl", "tcl8.6")
tk_dir = os.path.join(sys.base_prefix, "tcl", "tk8.6")
if os.path.exists(tcl_dir):
    os.environ["TCL_LIBRARY"] = tcl_dir
if os.path.exists(tk_dir):
    os.environ["TK_LIBRARY"] = tk_dir

from blueprint_scanner import BlueprintScanner
from test_grid_matrix_generator import generate_all_test_grids
from ui.app import TacticalCommandCenter


@unittest.skipIf(
    sys.platform.startswith("linux") and "DISPLAY" not in os.environ,
    "No X11 display available on headless Linux CI",
)
class TestUIHeadlessAutomation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp())
        cls.grids = generate_all_test_grids(cls.temp_dir)
        cls.scanner = BlueprintScanner()
        cls.blueprints = cls.scanner.scan_blueprints(cls.temp_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_full_app_and_selective_panel_automation(self):
        """CTk 6: app lifecycle, current navigation and separate selective dialog."""
        import customtkinter as ctk
        from ui.selective_exchange_panel import SelectiveExchangePanel

        self.assertTrue(ctk.__version__.startswith("6."))
        # Widget contracts run without starting background I/O or saving settings.
        with patch("threading.Thread.start"), patch("app_settings.SettingsStore.save"):
            app = TacticalCommandCenter()
            app.withdraw()
            try:
                app.blueprints = self.blueprints
                app.blueprint_panel.set_blueprints(self.blueprints)
                battleship = next(b for b in self.blueprints if b.name == "Battleship_Vindicator")
                app.on_blueprint_select(battleship)
                self.assertEqual(app.selected_blueprint.name, battleship.name)

                panel = SelectiveExchangePanel(app)
                panel.load_blueprint(battleship)
                app.update()
                self.assertIsNotNone(panel.current_blueprint)
                self.assertGreater(len(panel._row_vars), 0)
                panel._select_all()
                self.assertTrue(all(v.get() for v in panel._row_vars.values()))
                panel._deselect_all()
                self.assertFalse(any(v.get() for v in panel._row_vars.values()))
                panel._select_only_armor()
                self.assertTrue(all("Armor" in st for st, v in panel._row_vars.items() if v.get()))

                for name in ("Overview", "XML", "Preview", "Subgrids", "Analytics", "SE2"):
                    app.preview_panel.tabview.set(name)
                    self.assertEqual(app.preview_panel.tabview.get(), name)
                for name in ("Blueprints", "Convert"):
                    app.sidebar_tabs.set(name)
                    self.assertEqual(app.sidebar_tabs.get(), name)

                app.run_dry_run_preview()
                with patch("threading.Thread") as thread:
                    app._run_selective_convert(
                        {"LargeBlockArmorSlope": "LargeHeavyBlockArmorSlope"},
                        {"LargeBlockArmorSlope"},
                    )
                    thread.return_value.start.assert_called_once()
                panel.destroy()
            finally:
                app._jobs.cancel_stale()
                app.destroy()


if __name__ == "__main__":
    unittest.main()
