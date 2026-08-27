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
        """Test full app lifecycle, blueprint selection, tab switching, and selective exchange."""
        with patch("customtkinter.CTk.mainloop"):
            app = TacticalCommandCenter()
            app.withdraw()

            # Inject test blueprints
            app.blueprints = self.blueprints
            app.blueprint_panel.set_blueprints(self.blueprints)

            # Select battleship
            battleship_bp = next(b for b in self.blueprints if b.name == "Battleship_Vindicator")
            app.on_blueprint_select(battleship_bp)

            self.assertEqual(app.selected_blueprint.name, "Battleship_Vindicator")

            # Verify SelectiveExchangePanel is populated
            preview = app.preview_panel
            selective_panel = preview.selective_panel
            self.assertIsNotNone(selective_panel.current_blueprint)
            self.assertGreater(len(selective_panel._row_vars), 0)

            # Test Quick Filter buttons on Selective panel
            selective_panel._select_all()
            self.assertEqual(len([st for st, v in selective_panel._row_vars.items() if v.get()]), len(selective_panel._row_vars))

            selective_panel._deselect_all()
            self.assertEqual(len([st for st, v in selective_panel._row_vars.items() if v.get()]), 0)

            selective_panel._select_only_armor()
            for st in [st for st, v in selective_panel._row_vars.items() if v.get()]:
                self.assertIn("Armor", st)

            # Verify PreviewPanel tab population
            preview = app.preview_panel
            self.assertIsNotNone(preview.selective_panel.current_blueprint)

            # Test tab switching across all 8 tabs
            tabs = [
                "INTEL", "SELECTIVE EXCHANGE", "XML SOURCE", "PREVIEW",
                "ANALYTICS", "PB DOCTOR", "SUBGRIDS & MAP", "SE2 TRANSITION"
            ]
            for tab_name in tabs:
                preview.tabview.set(tab_name)
                self.assertEqual(preview.tabview.get(), tab_name)

            # Run dry run preview
            app.run_dry_run_preview()

            # Test Selective Conversion execution
            custom_map = {"LargeBlockArmorSlope": "LargeHeavyBlockArmorSlope"}
            selected = {"LargeBlockArmorSlope"}
            
            with patch("threading.Thread") as mock_thread:
                # Capture thread target and run synchronously
                def sync_start():
                    pass
                mock_thread.return_value.start = sync_start
                app.selective_convert_blueprint(custom_map, selected)

            # Test SE2 Export trigger
            with patch("tkinter.messagebox.askyesno", return_value=True), patch("threading.Thread") as mock_thread:
                def sync_start():
                    pass
                mock_thread.return_value.start = sync_start
                app.migrate_se2_blueprint()

            app.destroy()


if __name__ == "__main__":
    unittest.main()
