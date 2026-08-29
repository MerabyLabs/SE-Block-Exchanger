"""
Persistent application settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


def _default_settings_path() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        base = Path(appdata) / "SEBlockExchanger"
    else:
        base = Path.home() / ".se_block_exchanger"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


@dataclass
class AppSettings:
    appearance_mode: str = "System"
    auto_check_updates: bool = True
    recent_blueprint_dirs: List[str] = field(default_factory=list)
    enabled_categories: List[str] = field(default_factory=lambda: ["armor"])
    recent_blueprints: List[str] = field(default_factory=list)
    cache_hours: int = 24
    space_engineers_install: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "AppSettings":
        return cls(
            appearance_mode=data.get("appearance_mode", "System"),
            auto_check_updates=bool(data.get("auto_check_updates", True)),
            recent_blueprint_dirs=list(data.get("recent_blueprint_dirs", [])),
            enabled_categories=list(data.get("enabled_categories", ["armor"])),
            recent_blueprints=list(data.get("recent_blueprints", [])),
            cache_hours=int(data.get("cache_hours", 24)),
            space_engineers_install=str(data.get("space_engineers_install", "") or ""),
        )

    def to_dict(self) -> Dict:
        return {
            "appearance_mode": self.appearance_mode,
            "auto_check_updates": self.auto_check_updates,
            "recent_blueprint_dirs": self.recent_blueprint_dirs,
            "enabled_categories": self.enabled_categories,
            "recent_blueprints": self.recent_blueprints,
            "cache_hours": self.cache_hours,
            "space_engineers_install": self.space_engineers_install,
        }


class SettingsStore:
    """Load and save AppSettings from a local JSON file."""

    def __init__(self, path: Path = None):
        self.path = Path(path) if path else _default_settings_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return AppSettings.from_dict(data)

    def save(self, settings: AppSettings) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(settings.to_dict(), handle, indent=2)

    def add_recent_dir(self, settings: AppSettings, directory: str, limit: int = 8) -> AppSettings:
        directory = str(directory)
        existing = [entry for entry in settings.recent_blueprint_dirs if entry != directory]
        settings.recent_blueprint_dirs = [directory] + existing[: max(limit - 1, 0)]
        self.save(settings)
        return settings

    def add_recent_blueprint(self, settings: AppSettings, blueprint_name: str, limit: int = 20) -> AppSettings:
        blueprint_name = str(blueprint_name)
        existing = [entry for entry in settings.recent_blueprints if entry != blueprint_name]
        settings.recent_blueprints = [blueprint_name] + existing[: max(limit - 1, 0)]
        self.save(settings)
        return settings

