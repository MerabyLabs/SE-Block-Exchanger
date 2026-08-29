"""
Unit tests for Steam Workshop and Mod.io sync utilities.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from workshop_sync import ModioFetcher, SteamWorkshopFetcher
from workshop_sync.steam_fetcher import WorkshopItem


class TestWorkshopSync(unittest.TestCase):
    def test_parse_steam_id(self):
        self.assertEqual(SteamWorkshopFetcher.parse_workshop_id("123456789"), "123456789")
        self.assertEqual(
            SteamWorkshopFetcher.parse_workshop_id(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=987654321"
            ),
            "987654321",
        )
        self.assertEqual(
            SteamWorkshopFetcher.parse_workshop_id(
                "steamcommunity.com/sharedfiles/filedetails/?id=55555&searchtext="
            ),
            "55555",
        )

    def test_parse_modio_url(self):
        self.assertEqual(
            ModioFetcher.parse_modio_url("https://mod.io/g/spaceengineers/m/flagship-cruiser"),
            "flagship-cruiser",
        )

    def test_zip_slip_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "evil.zip"
            dest = Path(tmp) / "out"
            dest.mkdir()
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../escaped.txt", "nope")
            with self.assertRaises(ValueError):
                ModioFetcher.extract_zip_blueprint(zip_path, dest)
            self.assertFalse((Path(tmp) / "escaped.txt").exists())

    def test_import_copies_nested_files_and_replaces_destination(self):
        previous = os.environ.get("APPDATA")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "12345"
            nested = src / "sub"
            nested.mkdir(parents=True)
            (src / "bp.sbc").write_text("<Definitions/>", encoding="utf-8")
            (nested / "extra.txt").write_text("nested", encoding="utf-8")
            os.environ["APPDATA"] = tmp
            try:
                local = Path(tmp) / "SpaceEngineers" / "Blueprints" / "local" / "Workshop_12345"
                local.mkdir(parents=True)
                (local / "stale.txt").write_text("old", encoding="utf-8")
                item = WorkshopItem(
                    workshop_id="12345",
                    folder_path=src,
                    sbc_path=src / "bp.sbc",
                    title="12345",
                )
                dest = SteamWorkshopFetcher.import_to_local_blueprints(item)
                self.assertTrue((dest / "bp.sbc").exists())
                self.assertTrue((dest / "sub" / "extra.txt").exists())
                self.assertFalse((dest / "stale.txt").exists())
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous

    def test_import_skips_symlinks(self):
        previous = os.environ.get("APPDATA")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "99999"
            src.mkdir()
            (src / "bp.sbc").write_text("<Definitions/>", encoding="utf-8")
            secret = Path(tmp) / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            link = src / "leak.txt"
            try:
                link.symlink_to(secret)
            except OSError:
                self.skipTest("symlinks are not available")
            os.environ["APPDATA"] = tmp
            try:
                item = WorkshopItem(
                    workshop_id="99999",
                    folder_path=src,
                    sbc_path=src / "bp.sbc",
                    title="99999",
                )
                dest = SteamWorkshopFetcher.import_to_local_blueprints(item)
                self.assertTrue((dest / "bp.sbc").exists())
                self.assertFalse((dest / "leak.txt").exists())
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous

    def test_import_rejects_symlink_root(self):
        previous = os.environ.get("APPDATA")
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real_item"
            real.mkdir()
            (real / "bp.sbc").write_text("<Definitions/>", encoding="utf-8")
            link = Path(tmp) / "88888"
            try:
                link.symlink_to(real)
            except OSError:
                self.skipTest("symlinks are not available")
            os.environ["APPDATA"] = tmp
            try:
                item = WorkshopItem(
                    workshop_id="88888",
                    folder_path=link,
                    sbc_path=link / "bp.sbc",
                    title="88888",
                )
                with self.assertRaises(ValueError):
                    SteamWorkshopFetcher.import_to_local_blueprints(item)
                dest = Path(tmp) / "SpaceEngineers" / "Blueprints" / "local" / "Workshop_88888"
                self.assertFalse(dest.exists())
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous

    def test_zip_drive_letter_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "drive.zip"
            dest = Path(tmp) / "out"
            dest.mkdir()
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("C:/Windows/file.txt", "nope")
            with self.assertRaises(ValueError):
                ModioFetcher.extract_zip_blueprint(zip_path, dest)
            self.assertFalse((dest / "Windows" / "file.txt").exists())
            self.assertFalse((dest / "C:" / "Windows" / "file.txt").exists())

    def test_zip_backslash_entries_extract_as_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "win.zip"
            dest = Path(tmp) / "out"
            dest.mkdir()
            posix_name = "subdir/nested/file.txt"
            win_name = "subdir\\nested\\file.txt"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr(posix_name, "ok")
            raw = zip_path.read_bytes()
            zip_path.write_bytes(
                raw.replace(posix_name.encode("ascii"), win_name.encode("ascii"))
            )
            ModioFetcher.extract_zip_blueprint(zip_path, dest)
            extracted = dest / "subdir" / "nested" / "file.txt"
            self.assertTrue(extracted.is_file())
            self.assertEqual(extracted.read_text(encoding="utf-8"), "ok")

    def test_list_cached_workshop_items_picks_sorted_sbc(self):
        previous = os.environ.get("APPDATA")
        with tempfile.TemporaryDirectory() as tmp:
            workshop = Path(tmp) / "SpaceEngineers" / "Blueprints" / "workshop" / "4242"
            workshop.mkdir(parents=True)
            (workshop / "zebra.sbc").write_text("<Definitions/>", encoding="utf-8")
            (workshop / "alpha.sbc").write_text("<Definitions/>", encoding="utf-8")
            os.environ["APPDATA"] = tmp
            try:
                items = SteamWorkshopFetcher.list_cached_workshop_items()
                matching = [item for item in items if item.workshop_id == "4242"]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].sbc_path.name, "alpha.sbc")
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
