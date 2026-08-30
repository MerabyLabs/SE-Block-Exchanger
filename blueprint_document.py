"""
One parsed blueprint shared by scan, inspect, analytics, preview, and convert.

Selecting a ship should parse bp.sbc at most once. Scene, voxels, hierarchy,
and dry-run counts all read the same records instead of walking CubeGrids again.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

import xml.etree.ElementTree as ET

import safe_xml
from safe_xml import FileStamp  # re-exported for callers / tests
from se_armor_replacer import ArmorBlockReplacer
from se_render.scene_graph import PreviewScene, extract_scene_from_root, voxels_from_scene
from subgrid_engine.hierarchy_parser import MultiGridStructure, SubgridHierarchyParser


class CancelledError(Exception):
    """Raised when a worker should drop a stale scan/inspect job."""


class JobToken:
    """Monotonic cancel token. begin() invalidates every previous generation."""

    def __init__(self) -> None:
        self._generation = 0
        self._lock = threading.Lock()

    def begin(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def cancel(self) -> int:
        return self.begin()

    def is_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    def raise_if_stale(self, generation: int) -> None:
        if not self.is_current(generation):
            raise CancelledError()


class JobHub:
    """One cancel surface for inspect, folder scan, and SE catalog."""

    def __init__(self) -> None:
        self.inspect = JobToken()
        self.scan = JobToken()
        self.catalog = JobToken()

    def cancel_stale(self) -> None:
        self.inspect.cancel()
        self.scan.cancel()
        self.catalog.cancel()

    def cancel_catalog(self) -> None:
        """File → Clear must drop only the SE catalog, not folder scan/inspect."""
        self.catalog.cancel()


def catalog_completion_allowed(token: JobToken, generation: int, *, cleared: bool) -> bool:
    """File → Clear must reject an in-flight catalog even if the worker finishes."""
    return (not cleared) and token.is_current(generation)


def inspect_result_applies(
    token: JobToken,
    generation: int,
    selected_path: Optional[Path],
    result_path: Optional[Path],
) -> bool:
    """Drop inspect success/error callbacks that belong to a previous selection."""
    if not token.is_current(generation):
        return False
    if selected_path is None or result_path is None:
        return False
    return Path(selected_path) == Path(result_path)


def blueprint_file(path: Path) -> Path:
    path = Path(path)
    if path.is_dir():
        return path / "bp.sbc"
    return path


@dataclass
class BlueprintDocument:
    """Parsed ship: one XML read, one scene extract, derived voxels + hierarchy."""

    stamp: FileStamp
    scene: PreviewScene
    structure: MultiGridStructure
    voxels: List[dict]
    subtype_counts: Dict[str, int]
    grid_size: str
    display_name: str
    block_count: int
    light_armor_count: int
    heavy_armor_count: int
    thruster_forwards: Dict[str, int] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return Path(self.stamp.path)

    @classmethod
    def from_root(
        cls,
        root: ET.Element,
        *,
        display_name: str,
        stamp: Optional[FileStamp] = None,
    ) -> "BlueprintDocument":
        scene = extract_scene_from_root(root)
        structure = SubgridHierarchyParser.from_scene(scene)
        voxels = voxels_from_scene(scene)
        subtype_counts: Dict[str, int] = Counter()
        thruster_forwards: Dict[str, int] = Counter()
        light = 0
        heavy = 0
        light_ids = ArmorBlockReplacer.LIGHT_TO_HEAVY
        heavy_ids = ArmorBlockReplacer.HEAVY_TO_LIGHT
        for block in scene.blocks:
            if block.subtype:
                subtype_counts[block.subtype] += 1
            if block.subtype in light_ids:
                light += 1
            if block.subtype in heavy_ids:
                heavy += 1
            if block.subtype and "thrust" in block.subtype.lower() and block.forward:
                thruster_forwards[block.forward] += 1
        grid_size = "Unknown"
        if scene.grids:
            main = next(
                (g for g in scene.grids if g.entity_id and g.entity_id == scene.main_grid_entity_id),
                None,
            )
            if main is None:
                main = next((g for g in scene.grids if g.name == scene.main_grid_name), scene.grids[0])
            grid_size = main.grid_size or "Unknown"
        return cls(
            stamp=stamp or FileStamp("", 0, 0),
            scene=scene,
            structure=structure,
            voxels=voxels,
            subtype_counts=dict(subtype_counts),
            grid_size=grid_size,
            display_name=display_name,
            block_count=len(scene.blocks),
            light_armor_count=light,
            heavy_armor_count=heavy,
            thruster_forwards=dict(thruster_forwards),
        )

    @classmethod
    def load(cls, path: Path, display_name: Optional[str] = None) -> "BlueprintDocument":
        bp_file = blueprint_file(path)
        stamp = FileStamp.from_path(bp_file)
        tree = safe_xml.parse(bp_file)
        name = display_name or bp_file.parent.name
        return cls.from_root(tree.getroot(), display_name=name, stamp=stamp)


class BlueprintDocumentCache:
    """LRU of recently selected ships. Hit only when path + mtime + size match."""

    def __init__(self, max_entries: int = 4) -> None:
        self.max_entries = max(1, int(max_entries))
        self._lock = threading.Lock()
        self._docs: Dict[str, BlueprintDocument] = {}
        self._order: List[str] = []

    def get(self, path: Path) -> Optional[BlueprintDocument]:
        bp_file = blueprint_file(path)
        try:
            stamp = FileStamp.from_path(bp_file)
        except OSError:
            return None
        key = str(bp_file)
        with self._lock:
            doc = self._docs.get(key)
            if doc is None or doc.stamp != stamp:
                return None
            if key in self._order:
                self._order.remove(key)
                self._order.append(key)
            return doc

    def put(self, doc: BlueprintDocument) -> BlueprintDocument:
        key = doc.stamp.path
        with self._lock:
            self._docs[key] = doc
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            while len(self._order) > self.max_entries:
                old = self._order.pop(0)
                self._docs.pop(old, None)
        return doc

    def get_or_load(
        self,
        path: Path,
        token: Optional[JobToken] = None,
        generation: int = 0,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> BlueprintDocument:
        hit = self.get(path)
        if hit is not None:
            return hit
        if token is not None:
            token.raise_if_stale(generation)
        if cancel is not None and cancel():
            raise CancelledError()
        doc = BlueprintDocument.load(path)
        if token is not None:
            token.raise_if_stale(generation)
        if cancel is not None and cancel():
            raise CancelledError()
        return self.put(doc)

    def invalidate(self, path: Optional[Path] = None) -> None:
        with self._lock:
            if path is None:
                self._docs.clear()
                self._order.clear()
                return
            key = str(blueprint_file(path))
            self._docs.pop(key, None)
            if key in self._order:
                self._order.remove(key)


def dry_run_from_counts(
    subtype_counts: Mapping[str, int],
    mapping: Mapping[str, str],
) -> Tuple[Dict[str, int], Dict[str, int], str, int]:
    """Preview conversion from already-counted subtypes. No XML walk."""
    before: Dict[str, int] = {}
    after: Dict[str, int] = {}
    pair_counts: Dict[str, int] = {}
    changed = 0
    for subtype, count in subtype_counts.items():
        n = int(count)
        if n <= 0:
            continue
        target = mapping.get(subtype)
        if not target or target == subtype:
            continue
        before[subtype] = before.get(subtype, 0) + n
        after[target] = after.get(target, 0) + n
        key = f"{subtype} -> {target}"
        pair_counts[key] = pair_counts.get(key, 0) + n
        changed += n
    if changed == 0:
        return before, after, "No changes would be made.", 0
    lines = [f"Dry-run report: {changed} block(s) would be changed:", ""]
    for change, count in sorted(pair_counts.items()):
        lines.append(f"  {change}  (x{count})")
    return before, after, "\n".join(lines), changed
