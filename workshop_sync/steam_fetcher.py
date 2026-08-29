"""
Steam Workshop Blueprint Sync & Ingestion Engine for Space Engineers.
Discovers cached workshop items, parses workshop IDs/URLs, and imports blueprints.
"""

from __future__ import annotations
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


SPACE_ENGINEERS_APP_ID = "244850"


@dataclass
class WorkshopItem:
    """Represents a discovered Space Engineers workshop blueprint."""
    workshop_id: str
    folder_path: Path
    sbc_path: Path
    title: str
    thumbnail_path: Optional[Path] = None


class SteamWorkshopFetcher:
    """Discovers and imports blueprints from Steam Workshop folders or links."""

    @classmethod
    def parse_workshop_id(cls, text_or_url: str) -> Optional[str]:
        """Extracts numeric Workshop ID from raw ID or steamcommunity.com URL."""
        text = text_or_url.strip()
        if text.isdigit():
            return text
        match = re.search(r"[?&]id=(\d+)", text)
        if match:
            return match.group(1)
        match = re.search(r"/sharedfiles/filedetails/\?id=(\d+)", text)
        if match:
            return match.group(1)
        return None

    @classmethod
    def get_candidate_workshop_dirs(cls) -> List[Path]:
        """Finds common Space Engineers workshop directories on Windows."""
        dirs: List[Path] = []

        # Check AppData SpaceEngineers Workshop cache
        appdata = os.environ.get("APPDATA")
        if appdata:
            se_workshop = Path(appdata) / "SpaceEngineers" / "Blueprints" / "workshop"
            if se_workshop.is_dir():
                dirs.append(se_workshop)

        # Check standard Steam install locations
        drives = ["C", "D", "E", "F", "G"]
        for drive in drives:
            paths = [
                Path(f"{drive}:/Program Files (x86)/Steam/steamapps/workshop/content/{SPACE_ENGINEERS_APP_ID}"),
                Path(f"{drive}:/Program Files/Steam/steamapps/workshop/content/{SPACE_ENGINEERS_APP_ID}"),
                Path(f"{drive}:/SteamLibrary/steamapps/workshop/content/{SPACE_ENGINEERS_APP_ID}"),
                Path(f"{drive}:/Steam/steamapps/workshop/content/{SPACE_ENGINEERS_APP_ID}"),
            ]
            for p in paths:
                if p.is_dir():
                    dirs.append(p)

        return dirs

    @classmethod
    def list_cached_workshop_items(cls) -> List[WorkshopItem]:
        """Lists all locally downloaded workshop blueprints."""
        items: List[WorkshopItem] = []
        seen_ids = set()

        steam_content_marker = f"workshop/content/{SPACE_ENGINEERS_APP_ID}"
        for base_dir in cls.get_candidate_workshop_dirs():
            try:
                entries = list(base_dir.iterdir())
            except OSError:
                continue
            require_numeric_id = steam_content_marker.replace("\\", "/") in str(base_dir).replace("\\", "/")
            for entry in entries:
                if entry.is_symlink() or not entry.is_dir():
                    continue
                wid = entry.name
                if require_numeric_id and not wid.isdigit():
                    continue
                if wid in seen_ids:
                    continue

                sbc_file = entry / "bp.sbc"
                if not sbc_file.is_file():
                    # Check for any .sbc file in the folder
                    sbc_candidates = sorted(entry.glob("*.sbc"))
                    if sbc_candidates:
                        sbc_file = sbc_candidates[0]
                    else:
                        continue

                thumb = entry / "thumb.png"
                thumbnail_path = thumb if thumb.is_file() else None

                items.append(
                    WorkshopItem(
                        workshop_id=wid,
                        folder_path=entry,
                        sbc_path=sbc_file,
                        title=entry.name,
                        thumbnail_path=thumbnail_path,
                    )
                )
                seen_ids.add(wid)

        return items

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        try:
            info = path.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode):
            return True
        attributes = getattr(info, "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT

    @staticmethod
    def _is_within_dir(root: Path, candidate: Path) -> bool:
        root_key = os.path.normcase(os.path.normpath(str(root)))
        cand_key = os.path.normcase(os.path.normpath(str(candidate)))
        try:
            return os.path.commonpath([root_key, cand_key]) == root_key
        except ValueError:
            return False

    @classmethod
    def _prepare_import_destination(cls, local_bp_dir: Path, dest_dir: Path) -> Path:
        """Create dest_dir inside local_bp_dir, replacing a previous real folder only."""
        local_root = local_bp_dir.resolve()
        if os.path.normcase(str(dest_dir.parent.resolve())) != os.path.normcase(str(local_root)):
            raise ValueError(f"Illegal workshop destination: {dest_dir}")

        if cls._is_link_or_junction(dest_dir):
            raise ValueError(
                f"Refusing to replace a symlink or junction destination: {dest_dir}"
            )
        if dest_dir.is_file():
            dest_dir.unlink()
        elif dest_dir.is_dir():
            dest_resolved = dest_dir.resolve()
            if not cls._is_within_dir(local_root, dest_resolved):
                raise ValueError(
                    f"Refusing to delete a destination outside local blueprints: {dest_dir}"
                )
            shutil.rmtree(dest_dir)
        elif dest_dir.exists():
            raise ValueError(f"Cannot replace destination: {dest_dir}")

        dest_dir.mkdir(parents=True)
        dest_root = dest_dir.resolve()
        if cls._is_link_or_junction(dest_dir) or not cls._is_within_dir(local_root, dest_root):
            raise ValueError(f"Illegal workshop destination: {dest_dir}")
        return dest_root

    @classmethod
    def import_to_local_blueprints(cls, item: WorkshopItem, custom_name: Optional[str] = None) -> Path:
        """Copies a workshop blueprint folder into the user's SpaceEngineers local blueprint directory."""
        appdata = os.environ.get("APPDATA")
        appdata_path = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"

        local_bp_dir = appdata_path / "SpaceEngineers" / "Blueprints" / "local"
        local_bp_dir.mkdir(parents=True, exist_ok=True)

        raw_name = custom_name or f"Workshop_{item.workshop_id}"
        # Sanitize folder name to prevent path traversal or filesystem illegal characters
        target_name = re.sub(r'[<>:"/\\|?*]', '_', raw_name).strip('. ')
        if not target_name:
            target_name = f"Workshop_{item.workshop_id}"

        source_root = Path(item.folder_path)
        if source_root.is_symlink() or not source_root.is_dir():
            raise ValueError(
                f"Workshop source folder must be a real directory, not a symlink: {source_root}"
            )

        dest_dir = local_bp_dir / target_name
        dest_root = cls._prepare_import_destination(local_bp_dir, dest_dir)

        for dirpath, dirnames, filenames in os.walk(source_root, followlinks=False):
            dirnames[:] = [
                name for name in dirnames
                if not (Path(dirpath) / name).is_symlink()
            ]
            for name in filenames:
                src = Path(dirpath) / name
                if src.is_symlink() or not src.is_file():
                    continue
                dest_file = dest_dir / src.relative_to(source_root)
                try:
                    dest_file.resolve().relative_to(dest_root)
                except ValueError as exc:
                    raise ValueError(f"Illegal workshop path: {src}") from exc
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_file, follow_symlinks=False)

        bp_dest = dest_dir / "bp.sbc"
        if not bp_dest.is_file():
            fallback = Path(item.sbc_path)
            dest_fallback = None
            try:
                dest_fallback = dest_dir / fallback.relative_to(source_root)
            except ValueError:
                dest_fallback = None
            candidate = (
                dest_fallback
                if dest_fallback is not None and dest_fallback.is_file()
                else fallback
            )
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError(
                    f"Workshop import has no bp.sbc (fallback was {fallback.name})"
                )
            shutil.copy2(candidate, bp_dest, follow_symlinks=False)

        return dest_dir
