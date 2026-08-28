"""End-to-end CLI tests for se_armor_replacer.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from blueprint_fixtures import write_blueprint, write_blueprint_dir


ROOT = Path(__file__).resolve().parent
CLI = ROOT / "se_armor_replacer.py"


class TestCLI(unittest.TestCase):
    def _run(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_version(self):
        from version import __version__

        result = self._run("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn(__version__, result.stdout)

    def test_help_without_input(self):
        result = self._run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage:", result.stdout.lower())

    def test_list_categories_marks_armor_active(self):
        result = self._run("--list-categories")
        self.assertEqual(result.returncode, 0)
        self.assertIn("armor:", result.stdout)
        self.assertIn("(active)", result.stdout)
        self.assertIn("dlc_substitution:", result.stdout)
        self.assertIn("thrusters:", result.stdout)

    def test_list_mappings_default_armor(self):
        result = self._run("--list-mappings")
        self.assertEqual(result.returncode, 0)
        self.assertIn("LargeBlockArmorBlock", result.stdout)
        self.assertIn("Categories: armor", result.stdout)

    def test_list_mappings_thrusters(self):
        result = self._run("--list-mappings", "--categories", "thrusters")
        self.assertEqual(result.returncode, 0)
        self.assertIn("LargeBlockSmallThrust", result.stdout)
        self.assertNotIn("LargeBlockArmorBlock", result.stdout)

    def test_unknown_category_fails(self):
        result = self._run("--list-mappings", "--categories", "not-a-category")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown mapping category", result.stderr)

    def test_all_categories_succeeds_with_profiles_loaded(self):
        result = self._run("--list-mappings", "--all-categories")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dlc_substitution", result.stdout)
        self.assertIn("thrusters", result.stdout)
        self.assertIn("weapons", result.stdout)

    def test_dry_run_does_not_modify_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bp = write_blueprint(Path(tmp) / "bp.sbc", ["LargeBlockArmorBlock"])
            original = bp.read_bytes()
            result = self._run(str(bp), "--dry-run", cwd=Path(tmp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DRY RUN", result.stdout)
            self.assertIn("would change", result.stdout)
            self.assertEqual(bp.read_bytes(), original)

    def test_in_place_conversion_and_backup(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            folder = write_blueprint_dir(Path(tmp), "Ship", ["LargeBlockArmorBlock"])
            result = self._run(str(folder), cwd=Path(tmp))
            self.assertEqual(result.returncode, 0, result.stderr)
            content = (folder / "bp.sbc").read_text(encoding="utf-8")
            self.assertIn("LargeHeavyBlockArmorBlock", content)
            self.assertTrue((folder / "bp.sbc.backup").exists())

    def test_output_path_and_no_backup(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = write_blueprint(Path(tmp) / "bp.sbc", ["LargeBlockArmorBlock"])
            out = Path(tmp) / "converted" / "out.sbc"
            result = self._run(str(src), "-o", str(out), "--no-backup")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            self.assertIn("LargeBlockArmorBlock", src.read_text(encoding="utf-8"))
            self.assertIn("LargeHeavyBlockArmorBlock", out.read_text(encoding="utf-8"))
            self.assertFalse(src.with_suffix(".sbc.backup").exists())

    def test_reverse_conversion(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bp = write_blueprint(Path(tmp) / "bp.sbc", ["LargeHeavyBlockArmorBlock"])
            result = self._run(str(bp), "--reverse", "--no-backup")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("LargeBlockArmorBlock", bp.read_text(encoding="utf-8"))

    def test_missing_blueprint_returns_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(str(Path(tmp) / "missing"), "--dry-run")
            self.assertEqual(result.returncode, 1)
            self.assertIn("Could not find bp.sbc", result.stderr)

    def test_sample_blueprint_file(self):
        result = self._run(str(ROOT / "test_bp.sbc"), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would change", result.stdout)


if __name__ == "__main__":
    unittest.main()
