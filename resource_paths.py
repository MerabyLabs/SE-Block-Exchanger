"""Resolve bundled data files for source runs and PyInstaller frozen builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory that contains packaged assets (PyInstaller _MEIPASS or repo root)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def project_root() -> Path:
    """Directory the user launched from (exe folder when frozen, repo root otherwise)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "SEBlockExchanger" if appdata else Path.home() / ".se_block_exchanger"
    base.mkdir(parents=True, exist_ok=True)
    return base


def bundled_profiles_dir() -> Path:
    return resource_path("profiles")


def user_profiles_dir() -> Path:
    path = user_data_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def writable_profiles_dir() -> Path:
    """User-editable profiles. Frozen builds write to AppData so updates survive relaunch."""
    if is_frozen():
        return user_profiles_dir()
    return bundled_profiles_dir()
