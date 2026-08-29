"""
Locate and validate a local Space Engineers 1 install.

Reads the user's Steam libraries and common install folders. Never copies
Bin64, Content, models, or textures into the application tree.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


SPACE_ENGINEERS_APP_ID = "244850"

_LIBRARY_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


@dataclass(frozen=True)
class InstallStatus:
    """Result of resolving a Space Engineers folder."""

    path: Optional[Path]
    valid: bool
    source: str  # "saved", "detected", "none"
    reason: str = ""


def normalize_install_root(path: Path) -> Path:
    """Accept the game root, Bin64, or Content and return the game root."""
    candidate = Path(path).expanduser()
    try:
        candidate = candidate.resolve()
    except OSError:
        candidate = candidate.absolute()

    if candidate.is_file() and candidate.name.lower() == "spaceengineers.exe":
        candidate = candidate.parent
    if candidate.name.lower() == "bin64":
        candidate = candidate.parent
    if candidate.name.lower() == "content" and (candidate.parent / "Bin64").is_dir():
        candidate = candidate.parent
    return candidate


def validate_install(path: Optional[Path]) -> bool:
    """True when the folder looks like a usable SE1 install."""
    if path is None:
        return False
    try:
        root = normalize_install_root(Path(path))
    except (OSError, ValueError):
        return False
    exe = root / "Bin64" / "SpaceEngineers.exe"
    cubes = root / "Content" / "Data" / "CubeBlocks"
    models = root / "Content" / "Models"
    return exe.is_file() and cubes.is_dir() and models.is_dir()


def _steam_library_roots() -> List[Path]:
    roots: List[Path] = []
    seen = set()

    def add(path: Path) -> None:
        try:
            resolved = path.expanduser()
            key = str(resolved).lower()
            if key in seen:
                return
            seen.add(key)
            roots.append(resolved)
        except OSError:
            return

    program_files = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if program_files:
        add(Path(program_files) / "Steam")

    home = Path.home()
    for extra in (
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / "Steam",
    ):
        add(extra)

    drives = [f"{letter}:" for letter in "CDEFG"]
    for drive in drives:
        add(Path(drive) / "Program Files (x86)" / "Steam")
        add(Path(drive) / "Program Files" / "Steam")
        add(Path(drive) / "Steam")
        add(Path(drive) / "SteamLibrary")

    steam_roots = list(roots)
    for steam_root in steam_roots:
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in _LIBRARY_PATH_RE.finditer(text):
            raw = match.group(1).replace("\\\\", "\\")
            add(Path(raw))

    return roots


def candidate_install_dirs(extra: Optional[Iterable[Path]] = None) -> List[Path]:
    """Folders that may contain SpaceEngineers.exe."""
    found: List[Path] = []
    seen = set()

    def add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(path)

    for item in extra or ():
        add(Path(item))

    for library in _steam_library_roots():
        add(library / "steamapps" / "common" / "SpaceEngineers")

    drives = [f"{letter}:" for letter in "CDEFG"]
    for drive in drives:
        add(Path(drive) / "Program Files (x86)" / "Steam" / "steamapps" / "common" / "SpaceEngineers")
        add(Path(drive) / "Program Files" / "Steam" / "steamapps" / "common" / "SpaceEngineers")
        add(Path(drive) / "SteamLibrary" / "steamapps" / "common" / "SpaceEngineers")
        add(Path(drive) / "Games" / "SpaceEngineers")

    return found


def detect_install(extra: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Return the first valid auto-detected install, or None."""
    for candidate in candidate_install_dirs(extra):
        if validate_install(candidate):
            return normalize_install_root(candidate)
    return None


def resolve_install(saved_path: Optional[str], extra: Optional[Iterable[Path]] = None) -> InstallStatus:
    """Prefer a saved path, then auto-detect."""
    if saved_path:
        try:
            saved = Path(saved_path)
        except (TypeError, ValueError):
            saved = None
        if saved is not None and validate_install(saved):
            return InstallStatus(
                path=normalize_install_root(saved),
                valid=True,
                source="saved",
            )
        if saved is not None:
            detected = detect_install(extra)
            if detected is not None:
                return InstallStatus(path=detected, valid=True, source="detected")
            return InstallStatus(
                path=None,
                valid=False,
                source="none",
                reason="Saved Space Engineers folder is not a valid install.",
            )

    detected = detect_install(extra)
    if detected is not None:
        return InstallStatus(path=detected, valid=True, source="detected")
    return InstallStatus(
        path=None,
        valid=False,
        source="none",
        reason="Space Engineers was not found. Locate the game folder to enable the 3D preview.",
    )
