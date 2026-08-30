"""
Blueprint Scanner Module
Scans Space Engineers blueprint directories and extracts metadata.
"""

import json
import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

import safe_xml
from safe_xml import FileStamp
from mappings import MappingRegistry, build_registry
from resource_paths import user_data_dir
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
    thruster_forwards: Dict[str, int] = field(default_factory=dict)

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
            "thruster_forwards": self.thruster_forwards,
        }


@dataclass
class ScanRecord:
    """Per-file facts so category/mode changes rematerialize without re-parsing XML."""

    stamp: FileStamp
    display_name: str
    grid_size: str
    block_count: int
    light_armor_count: int
    heavy_armor_count: int
    subtype_counts: Dict[str, int]
    thruster_forwards: Dict[str, int] = field(default_factory=dict)

    def to_payload(self) -> dict:
        return {
            "path": self.stamp.path,
            "mtime_ns": self.stamp.mtime_ns,
            "size": self.stamp.size,
            "display_name": self.display_name,
            "grid_size": self.grid_size,
            "block_count": self.block_count,
            "light_armor_count": self.light_armor_count,
            "heavy_armor_count": self.heavy_armor_count,
            "subtype_counts": self.subtype_counts,
            "thruster_forwards": self.thruster_forwards,
        }

    @classmethod
    def from_payload(cls, data: dict) -> Optional["ScanRecord"]:
        try:
            stamp = FileStamp(
                str(data["path"]),
                int(data["mtime_ns"]),
                int(data["size"]),
            )
            return cls(
                stamp=stamp,
                display_name=str(data.get("display_name") or Path(stamp.path).parent.name),
                grid_size=str(data.get("grid_size") or "Unknown"),
                block_count=int(data.get("block_count") or 0),
                light_armor_count=int(data.get("light_armor_count") or 0),
                heavy_armor_count=int(data.get("heavy_armor_count") or 0),
                subtype_counts={str(k): int(v) for k, v in (data.get("subtype_counts") or {}).items()},
                thruster_forwards={str(k): int(v) for k, v in (data.get("thruster_forwards") or {}).items()},
            )
        except (KeyError, TypeError, ValueError):
            return None


class BlueprintScanner:
    """Scans and manages Space Engineers blueprints."""

    LIGHT_ARMOR_BLOCKS = set(ArmorBlockReplacer.LIGHT_TO_HEAVY.keys())
    HEAVY_ARMOR_BLOCKS = set(ArmorBlockReplacer.LIGHT_TO_HEAVY.values())

    def __init__(
        self,
        registry: Optional[MappingRegistry] = None,
        enabled_categories: Optional[Sequence[str]] = None,
        reverse: bool = False,
        persist_cache: Union[bool, Path] = True,
    ):
        self.registry = registry if registry else build_registry(include_builtin=True)
        if enabled_categories is None:
            # "All built-in" — skip endgame/profile categories that share sources.
            self.enabled_categories = [
                category.name
                for category in self.registry.list_categories()
                if category.source == "built-in"
            ]
        else:
            self.enabled_categories = list(enabled_categories)
        self.reverse = reverse
        self.blueprints_cache: List[BlueprintInfo] = []
        self._records: List[ScanRecord] = []
        self._meta: Dict[str, ScanRecord] = {}
        self._category_members_cache: Optional[List[Tuple[str, Set[str]]]] = None
        self._category_members_fingerprint: Optional[Tuple[Tuple[str, int, int], ...]] = None
        self._subtype_index_cache: Optional[Dict[str, Tuple[str, ...]]] = None
        self._subtype_index_fingerprint: Optional[Tuple[Tuple[str, int, int], ...]] = None
        if persist_cache is False:
            self._persist_path: Optional[Path] = None
        elif persist_cache is True:
            self._persist_path = user_data_dir() / "scan_meta_v1.json"
        else:
            self._persist_path = persist_cache
        self._load_persist()
        self._rebuild_mapping()

    def _rebuild_mapping(self) -> None:
        self._mapping = self.registry.build_mapping(
            reverse=self.reverse,
            enabled_categories=self.enabled_categories,
        )

    def _category_members(self) -> List[Tuple[str, Set[str]]]:
        """Per-category subtype sets, rebuilt only when the registry changes."""
        fingerprint = tuple(
            (category.name, id(category.pairs), len(category.pairs))
            for category in self.registry.list_categories()
        )
        if self._category_members_cache is None or self._category_members_fingerprint != fingerprint:
            self._category_members_cache = [
                (category.name, set(category.pairs) | set(category.pairs.values()))
                for category in self.registry.list_categories()
            ]
            self._category_members_fingerprint = fingerprint
        return self._category_members_cache

    def set_enabled_categories(self, enabled_categories: Sequence[str]) -> None:
        self.enabled_categories = list(enabled_categories)
        self._rebuild_mapping()

    def set_reverse(self, reverse: bool) -> None:
        self.reverse = bool(reverse)
        self._rebuild_mapping()

    def _registry_fingerprint(self) -> Tuple[Tuple[str, int, int], ...]:
        return tuple(
            (category.name, id(category.pairs), len(category.pairs))
            for category in self.registry.list_categories()
        )

    def _subtype_index(self) -> Dict[str, Tuple[str, ...]]:
        fingerprint = self._registry_fingerprint()
        if self._subtype_index_cache is None or self._subtype_index_fingerprint != fingerprint:
            index: Dict[str, List[str]] = {}
            for category in self.registry.list_categories():
                members = set(category.pairs) | set(category.pairs.values())
                for subtype in members:
                    index.setdefault(subtype, []).append(category.name)
            self._subtype_index_cache = {key: tuple(names) for key, names in index.items()}
            self._subtype_index_fingerprint = fingerprint
        return self._subtype_index_cache

    def _info_from_record(self, record: ScanRecord) -> BlueprintInfo:
        category_counter: Dict[str, int] = defaultdict(int)
        convertible_counter: Dict[str, int] = defaultdict(int)
        index = self._subtype_index()
        for subtype, count in record.subtype_counts.items():
            for category_name in index.get(subtype, ()):
                category_counter[category_name] += count
            target = self._mapping.get(subtype)
            if target:
                convertible_counter[f"{subtype}->{target}"] += count
        return BlueprintInfo(
            name=Path(record.stamp.path).parent.name,
            path=Path(record.stamp.path).parent,
            display_name=record.display_name,
            grid_size=record.grid_size,
            block_count=record.block_count,
            light_armor_count=record.light_armor_count,
            heavy_armor_count=record.heavy_armor_count,
            has_bp_file=True,
            subtype_counts=dict(record.subtype_counts),
            category_counts=dict(sorted(category_counter.items())),
            convertible_counts=dict(sorted(convertible_counter.items())),
            thruster_forwards=dict(record.thruster_forwards),
        )

    def remap_cached(self) -> List[BlueprintInfo]:
        """Rebuild BlueprintInfo from cached ScanRecords using the current mapping."""
        infos = [self._info_from_record(record) for record in self._records]
        self.blueprints_cache = infos
        return infos

    def _load_persist(self) -> None:
        path = self._persist_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, dict):
            return
        for raw in files.values():
            if not isinstance(raw, dict):
                continue
            record = ScanRecord.from_payload(raw)
            if record is not None:
                self._meta[record.stamp.path] = record

    def _save_persist(self) -> None:
        path = self._persist_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            files = {key: record.to_payload() for key, record in self._meta.items()}
            path.write_text(json.dumps({"version": 1, "files": files}, separators=(",", ":")), encoding="utf-8")
        except OSError:
            return

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

    def scan_blueprints(
        self,
        blueprint_dir: Optional[Path] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> List[BlueprintInfo]:
        if blueprint_dir is None:
            blueprint_dir = self.get_default_blueprint_path()
        blueprint_dir = Path(blueprint_dir)
        if not blueprint_dir.exists():
            raise FileNotFoundError(f"Blueprint directory not found: {blueprint_dir}")

        records: List[ScanRecord] = []
        parsed_any = False
        for item in blueprint_dir.iterdir():
            if cancel is not None and cancel():
                return self.blueprints_cache
            if not item.is_dir():
                continue
            bp_file = item / "bp.sbc"
            if not bp_file.exists():
                continue
            try:
                record, parsed = self._record_for(item, bp_file)
            except Exception as exc:
                print(f"Warning: Could not parse {item.name}: {exc}")
                continue
            records.append(record)
            parsed_any = parsed_any or parsed
        self._records = records
        if parsed_any:
            self._save_persist()
        blueprints = [self._info_from_record(record) for record in records]
        self.blueprints_cache = blueprints
        return blueprints

    def parse_folder(self, folder_path: Path) -> BlueprintInfo:
        folder_path = Path(folder_path)
        bp_file = folder_path / "bp.sbc"
        if not bp_file.exists():
            raise FileNotFoundError(f"No bp.sbc found in: {folder_path}")
        record, _parsed = self._record_for(folder_path, bp_file)
        return self._info_from_record(record)

    def _record_for(self, folder_path: Path, bp_file: Path) -> Tuple[ScanRecord, bool]:
        stamp = FileStamp.from_path(bp_file)
        cached = self._meta.get(stamp.path)
        if cached is not None and cached.stamp == stamp:
            return cached, False
        record = self._parse_to_record(folder_path, bp_file, stamp)
        self._meta[stamp.path] = record
        return record, True

    def _parse_blueprint(self, folder_path: Path, bp_file: Path) -> BlueprintInfo:
        record, _parsed = self._record_for(folder_path, bp_file)
        return self._info_from_record(record)

    def _parse_to_record(self, folder_path: Path, bp_file: Path, stamp: FileStamp) -> ScanRecord:
        tree = safe_xml.parse(bp_file)
        root = tree.getroot()
        grids = safe_xml.iter_cube_grids(root)
        grid_size = "Unknown"
        subtype_counter: Dict[str, int] = Counter()
        thruster_forwards: Dict[str, int] = Counter()
        light_armor_count = 0
        heavy_armor_count = 0
        block_count = 0

        def consume(block: ET.Element) -> None:
            nonlocal light_armor_count, heavy_armor_count, block_count
            block_count += 1
            subtype = self._extract_subtype(block)
            if not subtype:
                return
            subtype_counter[subtype] += 1
            if subtype in self.LIGHT_ARMOR_BLOCKS:
                light_armor_count += 1
            if subtype in self.HEAVY_ARMOR_BLOCKS:
                heavy_armor_count += 1
            lowered = subtype.lower()
            if "thrust" not in lowered:
                return
            kids = safe_xml.index_children(block)
            orient = kids.get("BlockOrientation")
            if orient is None:
                return
            forward = orient.attrib.get("Forward")
            if forward:
                thruster_forwards[forward] += 1

        if grids:
            for grid in grids:
                if grid_size == "Unknown":
                    kids = safe_xml.index_children(grid)
                    size_elem = kids.get("GridSizeEnum")
                    if size_elem is not None and size_elem.text and size_elem.text.strip():
                        grid_size = size_elem.text.strip()
                for block in safe_xml.iter_blocks_in_grid(grid):
                    consume(block)
        else:
            for block in root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock") or root.findall(
                ".//MyObjectBuilder_CubeBlock"
            ):
                consume(block)

        return ScanRecord(
            stamp=stamp,
            display_name=folder_path.name,
            grid_size=grid_size,
            block_count=block_count,
            light_armor_count=light_armor_count,
            heavy_armor_count=heavy_armor_count,
            subtype_counts=dict(subtype_counter),
            thruster_forwards=dict(thruster_forwards),
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

