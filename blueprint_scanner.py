"""
Blueprint Scanner Module
Scans Space Engineers blueprint directories and extracts metadata.
"""

import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import safe_xml
from mappings import MappingRegistry, build_registry
from se_armor_replacer import ArmorBlockReplacer


@dataclass
class BlueprintInfo:
    """Information about a Space Engineers blueprint."""

    name: str
    path: Path
    display_name: str
    grid_size: str  # 'Large' or 'Small'
    block_count: int
    light_armor_count: int
    heavy_armor_count: int
    has_bp_file: bool
    subtype_counts: Dict[str, int] = field(default_factory=dict)
    category_counts: Dict[str, int] = field(default_factory=dict)
    convertible_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "display_name": self.display_name,
            "grid_size": self.grid_size,
            "block_count": self.block_count,
            "light_armor_count": self.light_armor_count,
            "heavy_armor_count": self.heavy_armor_count,
            "has_bp_file": self.has_bp_file,
            "subtype_counts": self.subtype_counts,
            "category_counts": self.category_counts,
            "convertible_counts": self.convertible_counts,
        }


class BlueprintScanner:
    """Scans and manages Space Engineers blueprints."""

    LIGHT_ARMOR_BLOCKS = set(ArmorBlockReplacer.LIGHT_TO_HEAVY.keys())
    HEAVY_ARMOR_BLOCKS = set(ArmorBlockReplacer.LIGHT_TO_HEAVY.values())

    def __init__(
        self,
        registry: Optional[MappingRegistry] = None,
        enabled_categories: Optional[Sequence[str]] = None,
        reverse: bool = False,
    ):
        self.registry = registry if registry else build_registry(include_builtin=True)
        self.enabled_categories = (
            [category.name for category in self.registry.list_categories()]
            if enabled_categories is None
            else list(enabled_categories)
        )
        self.reverse = reverse
        self.blueprints_cache: List[BlueprintInfo] = []
        self._rebuild_mapping()

    def _rebuild_mapping(self) -> None:
        self._mapping = self.registry.build_mapping(
            reverse=self.reverse,
            enabled_categories=self.enabled_categories,
        )

    def set_enabled_categories(self, enabled_categories: Sequence[str]) -> None:
        self.enabled_categories = list(enabled_categories)
        self._rebuild_mapping()

    def set_reverse(self, reverse: bool) -> None:
        self.reverse = bool(reverse)
        self._rebuild_mapping()

    def get_default_blueprint_path(self) -> Path:
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise RuntimeError("Could not find APPDATA directory")
        return Path(appdata) / "SpaceEngineers" / "Blueprints" / "local"

    def get_workshop_blueprint_path(self) -> Path:
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise RuntimeError("Could not find APPDATA directory")
        return Path(appdata) / "SpaceEngineers" / "Blueprints" / "workshop"

    def scan_blueprints(self, blueprint_dir: Optional[Path] = None) -> List[BlueprintInfo]:
        if blueprint_dir is None:
            blueprint_dir = self.get_default_blueprint_path()
        blueprint_dir = Path(blueprint_dir)
        if not blueprint_dir.exists():
            raise FileNotFoundError(f"Blueprint directory not found: {blueprint_dir}")

        blueprints: List[BlueprintInfo] = []
        for item in blueprint_dir.iterdir():
            if not item.is_dir():
                continue
            bp_file = item / "bp.sbc"
            if not bp_file.exists():
                continue
            try:
                blueprints.append(self._parse_blueprint(item, bp_file))
            except Exception as exc:
                print(f"Warning: Could not parse {item.name}: {exc}")
        self.blueprints_cache = blueprints
        return blueprints

    def parse_folder(self, folder_path: Path) -> BlueprintInfo:
        folder_path = Path(folder_path)
        bp_file = folder_path / "bp.sbc"
        if not bp_file.exists():
            raise FileNotFoundError(f"No bp.sbc found in: {folder_path}")
        return self._parse_blueprint(folder_path, bp_file)

    def _parse_blueprint(self, folder_path: Path, bp_file: Path) -> BlueprintInfo:
        tree = safe_xml.parse(bp_file)
        root = tree.getroot()

        display_name = folder_path.name
        grid_size = "Unknown"
        grid_size_elem = root.find(".//CubeGrid/GridSizeEnum")
        if grid_size_elem is not None and grid_size_elem.text:
            grid_size = grid_size_elem.text.strip()

        blocks = root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
        subtype_counter: Dict[str, int] = Counter()
        category_counter: Dict[str, int] = defaultdict(int)
        convertible_counter: Dict[str, int] = defaultdict(int)

        light_armor_count = 0
        heavy_armor_count = 0
        # O(1) membership: sources and targets, not a linear scan of .values().
        category_members = [
            (category.name, set(category.pairs) | set(category.pairs.values()))
            for category in self.registry.list_categories()
        ]

        for block in blocks:
            subtype = self._extract_subtype(block)
            if not subtype:
                continue

            subtype_counter[subtype] += 1
            if subtype in self.LIGHT_ARMOR_BLOCKS:
                light_armor_count += 1
            if subtype in self.HEAVY_ARMOR_BLOCKS:
                heavy_armor_count += 1

            for category_name, members in category_members:
                if subtype in members:
                    category_counter[category_name] += 1

            if subtype in self._mapping:
                target = self._mapping[subtype]
                convertible_counter[f"{subtype}->{target}"] += 1

        return BlueprintInfo(
            name=folder_path.name,
            path=folder_path,
            display_name=display_name,
            grid_size=grid_size,
            block_count=len(blocks),
            light_armor_count=light_armor_count,
            heavy_armor_count=heavy_armor_count,
            has_bp_file=True,
            subtype_counts=dict(sorted(subtype_counter.items())),
            category_counts=dict(sorted(category_counter.items())),
            convertible_counts=dict(sorted(convertible_counter.items())),
        )

    @staticmethod
    def _extract_subtype(block: ET.Element) -> Optional[str]:
        subtype_name = block.find("SubtypeName")
        if subtype_name is not None and subtype_name.text:
            return subtype_name.text.strip()
        subtype_id = block.find("SubtypeId")
        if subtype_id is not None and subtype_id.text:
            return subtype_id.text.strip()
        return None

    def get_blueprint_by_name(self, name: str) -> Optional[BlueprintInfo]:
        for bp in self.blueprints_cache:
            if bp.name == name:
                return bp
        return None

    def filter_blueprints(
        self,
        search_term: str = "",
        min_light_armor: int = 0,
    ) -> List[BlueprintInfo]:
        filtered = []
        search_lower = search_term.lower()
        for bp in self.blueprints_cache:
            if bp.light_armor_count < min_light_armor:
                continue
            if search_term and search_lower not in bp.name.lower() and search_lower not in bp.display_name.lower():
                continue
            filtered.append(bp)
        return filtered

