"""
Custom mapping profile loading, validation, and import/export.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mappings.registry import MappingCategory, MappingRegistry, MappingValidationError


PROFILE_EXTENSION = ".sebx-profile"


class ProfileValidationError(ValueError):
    """Raised when a profile JSON document is invalid."""


@dataclass
class MappingProfile:
    name: str
    author: str
    version: str
    description: str
    game_version: str
    categories: List[MappingCategory]
    source_path: Optional[Path] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "description": self.description,
            "game_version": self.game_version,
            "categories": [
                {
                    "name": c.name,
                    "description": c.description,
                    "grid_sizes": list(c.grid_sizes),
                    "pairs": [[source, target] for source, target in c.pairs.items()],
                }
                for c in self.categories
            ],
        }


class ProfileManager:
    """Manage profile discovery and profile->mapping registry integration."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: Dict[str, MappingProfile] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()

    @staticmethod
    def _validate_required(data: Dict, key: str, expected_type):
        if key not in data:
            raise ProfileValidationError(f"Missing required key '{key}'")
        if not isinstance(data[key], expected_type):
            raise ProfileValidationError(f"Key '{key}' must be {expected_type.__name__}")

    def validate_profile_json(self, data: Dict) -> None:
        self._validate_required(data, "name", str)
        self._validate_required(data, "author", str)
        self._validate_required(data, "version", str)
        self._validate_required(data, "description", str)
        self._validate_required(data, "game_version", str)
        self._validate_required(data, "categories", list)

        if not data["categories"]:
            raise ProfileValidationError("Profile must include at least one category")

        category_names = set()
        for raw_category in data["categories"]:
            if not isinstance(raw_category, dict):
                raise ProfileValidationError("Each profile category must be an object")
            self._validate_required(raw_category, "name", str)
            self._validate_required(raw_category, "pairs", list)

            name = raw_category["name"].strip()
            if not name:
                raise ProfileValidationError("Category name cannot be empty")
            lowered = name.lower()
            if lowered in category_names:
                raise ProfileValidationError(f"Duplicate category name in profile: {name}")
            category_names.add(lowered)

            pairs_dict: Dict[str, str] = {}
            for item in raw_category["pairs"]:
                if not isinstance(item, list) or len(item) != 2:
                    raise ProfileValidationError(
                        f"Category '{name}' pairs must be [source, target] lists"
                    )
                source, target = item
                if not isinstance(source, str) or not isinstance(target, str):
                    raise ProfileValidationError(
                        f"Category '{name}' pair values must be strings"
                    )
                source = source.strip()
                target = target.strip()
                if not source or not target:
                    raise ProfileValidationError(
                        f"Category '{name}' contains empty source/target values"
                    )
                if source in pairs_dict and pairs_dict[source] != target:
                    raise ProfileValidationError(
                        f"Category '{name}' has conflicting mapping for source '{source}'"
                    )
                pairs_dict[source] = target

            try:
                MappingRegistry.validate_pairs(pairs_dict)
            except MappingValidationError as exc:
                raise ProfileValidationError(
                    f"Category '{name}' mapping validation failed: {exc}"
                ) from exc

    def _category_from_json(self, profile_name: str, raw: Dict) -> MappingCategory:
        description = raw.get("description", f"{profile_name} category '{raw['name']}'")
        grid_sizes = tuple(raw.get("grid_sizes", ("Large", "Small")))
        pairs = {source: target for source, target in raw["pairs"]}
        return MappingCategory(
            name=f"profile:{self._normalize_name(profile_name)}:{self._normalize_name(raw['name'])}",
            description=description,
            pairs=pairs,
            grid_sizes=grid_sizes,
            source=f"profile:{profile_name}",
            enabled_by_default=False,
            tags=("profile",),
        )

    def parse_profile(self, data: Dict, source_path: Optional[Path] = None) -> MappingProfile:
        self.validate_profile_json(data)
        categories = [
            self._category_from_json(data["name"], raw)
            for raw in data["categories"]
        ]
        return MappingProfile(
            name=data["name"].strip(),
            author=data["author"].strip(),
            version=data["version"].strip(),
            description=data["description"].strip(),
            game_version=data["game_version"].strip(),
            categories=categories,
            source_path=source_path,
        )

    def load_profile_file(self, path: Path) -> MappingProfile:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        profile = self.parse_profile(data, source_path=Path(path))
        self._profiles[self._normalize_name(profile.name)] = profile
        return profile

    def load_all(self) -> List[MappingProfile]:
        loaded: List[MappingProfile] = []
        self._profiles.clear()
        for path in sorted(self.profile_dir.glob(f"*{PROFILE_EXTENSION}")):
            loaded.append(self.load_profile_file(path))
        for path in sorted(self.profile_dir.glob("*.json")):
            if path.name.lower().endswith(".schema.json"):
                continue
            try:
                loaded.append(self.load_profile_file(path))
            except ProfileValidationError:
                # Non-profile JSON files can coexist in the directory.
                continue
        return loaded

    def list_profiles(self) -> List[MappingProfile]:
        return [self._profiles[name] for name in sorted(self._profiles)]

    def get(self, name: str) -> MappingProfile:
        key = self._normalize_name(name)
        if key not in self._profiles:
            raise KeyError(f"Unknown profile: {name}")
        return self._profiles[key]

    def upsert_profile(self, profile: MappingProfile) -> Path:
        file_name = f"{profile.name.strip().replace(' ', '_')}{PROFILE_EXTENSION}"
        file_path = self.profile_dir / file_name
        self.save_profile(profile, file_path)
        self._profiles[self._normalize_name(profile.name)] = profile
        return file_path

    def save_profile(self, profile: MappingProfile, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(profile.to_dict(), handle, indent=2, sort_keys=False)

    def export_profile(self, name: str, destination: Path) -> Path:
        profile = self.get(name)
        destination = Path(destination)
        if destination.exists() and destination.is_dir():
            destination = destination / f"{profile.name.replace(' ', '_')}{PROFILE_EXTENSION}"
        elif not destination.suffix:
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination / f"{profile.name.replace(' ', '_')}{PROFILE_EXTENSION}"
        self.save_profile(profile, destination)
        return destination

    def import_profile(self, source: str) -> Tuple[MappingProfile, Path]:
        if source.startswith("http://") or source.startswith("https://"):
            with urllib.request.urlopen(source, timeout=10) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
            profile = self.parse_profile(data)
            saved_path = self.upsert_profile(profile)
            return profile, saved_path

        path = Path(source)
        profile = self.load_profile_file(path)
        saved_path = self.upsert_profile(profile)
        return profile, saved_path

    def duplicate_profile(self, source_name: str, new_name: str) -> MappingProfile:
        src = self.get(source_name)
        duplicated = MappingProfile(
            name=new_name,
            author=src.author,
            version=src.version,
            description=src.description,
            game_version=src.game_version,
            categories=[
                MappingCategory(
                    name=f"profile:{self._normalize_name(new_name)}:{c.name.split(':')[-1]}",
                    description=c.description,
                    pairs=dict(c.pairs),
                    grid_sizes=tuple(c.grid_sizes),
                    source=f"profile:{new_name}",
                    enabled_by_default=False,
                    tags=c.tags,
                )
                for c in src.categories
            ],
        )
        self.upsert_profile(duplicated)
        return duplicated

    def register_profile_categories(self, registry: MappingRegistry) -> int:
        count = 0
        for profile in self.list_profiles():
            for category in profile.categories:
                if registry.exists(category.name):
                    registry.register(category, overwrite=True)
                else:
                    registry.register(category)
                count += 1
        return count

    def discord_share_text(self, name: str) -> str:
        profile = self.get(name)
        payload = json.dumps(profile.to_dict(), indent=2)
        return (
            f"**{profile.name}** by {profile.author} (v{profile.version})\n"
            f"{profile.description}\n\n```json\n{payload}\n```"
        )

    @staticmethod
    def list_known_block_ids(registry: MappingRegistry) -> List[str]:
        ids: set[str] = set()
        for category in registry.list_categories():
            ids.update(category.pairs.keys())
            ids.update(category.pairs.values())
        return sorted(ids)
