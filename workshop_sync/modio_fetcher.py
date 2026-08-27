"""
Mod.io Blueprint Ingestion Engine for Space Engineers (Crossplay / Console blueprints).
Handles Mod.io URL parsing and zip/package extraction to local blueprints.
"""

from __future__ import annotations
import os
import re
import zipfile
import shutil
from dataclasses import dataclass
from pathlib import Path
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

    @classmethod
    def extract_zip_blueprint(cls, zip_path: Path, destination_folder: Path) -> Path:
        """Safely extracts a mod.io zip archive into a Space Engineers blueprint folder."""
        zip_path = Path(zip_path)
        destination_folder = Path(destination_folder)
        destination_folder.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            dest_resolved = destination_folder.resolve()
            for member in zf.infolist():
                # Defend against zip slip using is_relative_to
                target_resolved = (destination_folder / member.filename).resolve()
                try:
                    if not target_resolved.is_relative_to(dest_resolved):
                        raise ValueError(f"Illegal zip entry path: {member.filename}")
                except AttributeError:
                    # Fallback for Python < 3.9
                    if not str(target_resolved).startswith(str(dest_resolved)):
                        raise ValueError(f"Illegal zip entry path: {member.filename}")
            zf.extractall(destination_folder)

        return destination_folder
