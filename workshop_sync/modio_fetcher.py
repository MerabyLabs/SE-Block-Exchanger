"""
Mod.io Blueprint Ingestion Engine for Space Engineers (Crossplay / Console blueprints).
Handles Mod.io URL parsing and zip/package extraction to local blueprints.
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional


@dataclass
class ModioBlueprintPackage:
    """Represents a Mod.io package file or folder."""
    mod_id: str
    source_path: Path
    title: str


class ModioFetcher:
    """Parses and imports Mod.io blueprints."""

    @classmethod
    def parse_modio_url(cls, url: str) -> Optional[str]:
        """Extracts mod slug or ID from Mod.io URLs."""
        match = re.search(r"mod\.io/(?:g/spaceengineers/)?m/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _is_within_dest(dest_resolved: Path, target_resolved: Path) -> bool:
        try:
            return os.path.commonpath([str(dest_resolved), str(target_resolved)]) == str(dest_resolved)
        except ValueError:
            return False

    @staticmethod
    def _normalized_member_path(filename: str) -> str:
        """Return a relative POSIX path, or raise if the zip entry is absolute/escaping."""
        member_path = filename.replace("\\", "/")
        posix = PurePosixPath(member_path)
        windows = PureWindowsPath(member_path)
        if (
            not member_path
            or posix.is_absolute()
            or windows.is_absolute()
            or bool(posix.anchor)
            or bool(windows.anchor)
            or ".." in posix.parts
            or ".." in windows.parts
        ):
            raise ValueError(f"Illegal zip entry path: {filename}")
        return str(posix)

    @classmethod
    def extract_zip_blueprint(cls, zip_path: Path, destination_folder: Path) -> Path:
        """Safely extracts a mod.io zip archive into a Space Engineers blueprint folder."""
        zip_path = Path(zip_path)
        destination_folder = Path(destination_folder)
        destination_folder.mkdir(parents=True, exist_ok=True)
        dest_resolved = destination_folder.resolve()

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_path = cls._normalized_member_path(member.filename)
                target_resolved = (destination_folder / member_path).resolve()
                if not cls._is_within_dest(dest_resolved, target_resolved):
                    raise ValueError(f"Illegal zip entry path: {member.filename}")
                if member.is_dir() or member.filename.replace("\\", "/").endswith("/"):
                    target_resolved.mkdir(parents=True, exist_ok=True)
                    continue
                target_resolved.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target_resolved, "wb") as out:
                    shutil.copyfileobj(src, out)

        return destination_folder
