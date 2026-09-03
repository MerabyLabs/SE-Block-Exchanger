import tempfile
import unittest
from pathlib import Path

from se_assets.install_locator import (
    detect_install,
    normalize_install_root,
    resolve_install,
    validate_install,
)


def _fake_install(root: Path) -> Path:
    (root / "Bin64").mkdir(parents=True)
    (root / "Content" / "Data" / "CubeBlocks").mkdir(parents=True)
    (root / "Content" / "Models").mkdir(parents=True)
    (root / "Bin64" / "SpaceEngineers.exe").write_bytes(b"mz")
    return root


class InstallLocatorTests(unittest.TestCase):
    def test_rejects_missing_folder(self):
        self.assertFalse(validate_install(None))
        self.assertFalse(validate_install(Path("/definitely/not/space-engineers")))

    def test_accepts_complete_tree_and_bin64_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_install(Path(tmp) / "SE")
            self.assertTrue(validate_install(root))
            self.assertTrue(validate_install(root / "Bin64"))
            self.assertEqual(normalize_install_root(root / "Bin64"), root.resolve())
            self.assertEqual(normalize_install_root(root / "Bin64" / "SpaceEngineers.exe"), root.resolve())

    def test_rejects_incomplete_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Almost"
            (root / "Bin64").mkdir(parents=True)
            (root / "Bin64" / "SpaceEngineers.exe").write_bytes(b"mz")
            self.assertFalse(validate_install(root))

    def test_detect_and_resolve_saved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_install(Path(tmp) / "Game")
            found = detect_install(extra=[root])
            self.assertEqual(found, root.resolve())
            from se_assets.install_locator import _volume_ready

            self.assertTrue(_volume_ready(root))
            status = resolve_install(str(root))
            self.assertTrue(status.valid)
            self.assertEqual(status.source, "saved")
            missing = resolve_install(str(Path(tmp) / "nope"), extra=[], allow_detect=False)
            self.assertFalse(missing.valid)
            self.assertEqual(missing.source, "none")

    def test_explicit_clear_does_not_redetect(self):
        cleared = resolve_install("", allow_detect=False)
        self.assertFalse(cleared.valid)
        self.assertEqual(cleared.source, "none")
        self.assertIsNone(cleared.path)

    def test_rejects_se2_style_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "SpaceEngineers2"
            (root / "Bin64").mkdir(parents=True)
            (root / "Content" / "Data").mkdir(parents=True)
            (root / "Bin64" / "SpaceEngineers2.exe").write_bytes(b"mz")
            self.assertFalse(validate_install(root))


if __name__ == "__main__":
    unittest.main()
