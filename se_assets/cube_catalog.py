"""
Parse CubeBlocks definitions from a local Space Engineers install.

Caches a JSON index under the user AppData folder. The cache is invalidated
when SpaceEngineers.exe's mtime changes. No Keen files are copied.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple
import xml.etree.ElementTree as ET

import safe_xml
from resource_paths import user_data_dir


@dataclass(frozen=True)
class BlockDefinition:
    type_id: str
    subtype_id: str
    cube_size: str
    block_topology: str
    cube_topology: str
    size_x: int
    size_y: int
    size_z: int
    model_path: str
    model_offset: Tuple[float, float, float]

    @property
    def key(self) -> str:
        return definition_key(self.type_id, self.subtype_id)

    @property
    def size(self) -> Tuple[int, int, int]:
        return (self.size_x, self.size_y, self.size_z)


def definition_key(type_id: str, subtype_id: str) -> str:
    return f"{type_id}/{subtype_id}"


def _cache_path() -> Path:
    return user_data_dir() / "cube_catalog_cache.json"


class CubeBlockCatalog:
    """Subtype → definition index built from Content/Data/CubeBlocks."""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self.install: Optional[Path] = None
        self.definitions: Dict[str, BlockDefinition] = {}
        self.by_subtype: Dict[str, BlockDefinition] = {}
        self.exe_mtime: float = 0.0
        self.cache_path = Path(cache_path) if cache_path else _cache_path()

    def __len__(self) -> int:
        return len(self.definitions)

    def get(self, type_id: str, subtype_id: str) -> Optional[BlockDefinition]:
        hit = self.definitions.get(definition_key(type_id, subtype_id))
        if hit is not None:
            return hit
        return self.by_subtype.get(subtype_id)

    def load(self, install: Path, force: bool = False) -> "CubeBlockCatalog":
        root = Path(install)
        exe = root / "Bin64" / "SpaceEngineers.exe"
        mtime = exe.stat().st_mtime if exe.is_file() else 0.0
        if not force and self._try_cache(root, mtime):
            return self
        self.install = root
        self.exe_mtime = mtime
        self.definitions = {}
        self.by_subtype = {}
        cube_dir = root / "Content" / "Data" / "CubeBlocks"
        files = []
        if cube_dir.is_dir():
            files.extend(sorted(cube_dir.glob("*.sbc")))
        data_dir = root / "Content" / "Data"
        if data_dir.is_dir():
            files.extend(sorted(data_dir.glob("CubeBlocks*.sbc")))
        seen = set()
        for path in files:
            key = str(path.resolve()).lower() if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            self._ingest_file(path)
        self._write_cache()
        return self

    def _try_cache(self, install: Path, mtime: float) -> bool:
        cache = self.cache_path
        if not cache.is_file():
            return False
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("install") != str(install) or abs(float(payload.get("exe_mtime", 0)) - mtime) > 0.5:
            return False
        defs: Dict[str, BlockDefinition] = {}
        by_subtype: Dict[str, BlockDefinition] = {}
        for raw in payload.get("definitions", []):
            definition = BlockDefinition(
                type_id=raw.get("type_id", "CubeBlock"),
                subtype_id=raw.get("subtype_id", ""),
                cube_size=raw.get("cube_size", "Large"),
                block_topology=raw.get("block_topology", "TriangleMesh"),
                cube_topology=raw.get("cube_topology", "Box"),
                size_x=int(raw.get("size_x", 1)),
                size_y=int(raw.get("size_y", 1)),
                size_z=int(raw.get("size_z", 1)),
                model_path=raw.get("model_path", ""),
                model_offset=tuple(raw.get("model_offset", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
            )
            defs[definition.key] = definition
            if definition.subtype_id and definition.subtype_id not in by_subtype:
                by_subtype[definition.subtype_id] = definition
        self.install = install
        self.exe_mtime = mtime
        self.definitions = defs
        self.by_subtype = by_subtype
        return True

    def _write_cache(self) -> None:
        payload = {
            "install": str(self.install) if self.install else "",
            "exe_mtime": self.exe_mtime,
            "definitions": [
                {
                    **asdict(item),
                    "model_offset": list(item.model_offset),
                }
                for item in self.definitions.values()
            ],
        }
        path = self.cache_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def _ingest_file(self, path: Path) -> None:
        try:
            tree = safe_xml.parse(path)
        except Exception:
            return
        root = tree.getroot()
        for definition in _iter_definitions(root):
            parsed = _parse_definition(definition)
            if parsed is None:
                continue
            self.definitions[parsed.key] = parsed
            if parsed.subtype_id and parsed.subtype_id not in self.by_subtype:
                self.by_subtype[parsed.subtype_id] = parsed


def _iter_definitions(root: ET.Element) -> Iterator[ET.Element]:
    for cubes in root.findall(".//CubeBlocks"):
        for child in list(cubes):
            yield child
    for cubes in root.findall(".//{*}CubeBlocks"):
        for child in list(cubes):
            yield child


def _parse_definition(node: ET.Element) -> Optional[BlockDefinition]:
    ident = node.find("Id")
    if ident is None:
        ident = node.find("{*}Id")
    if ident is None:
        return None
    type_id = _text(ident, "TypeId") or "CubeBlock"
    if type_id.startswith("MyObjectBuilder_"):
        type_id = type_id[len("MyObjectBuilder_") :]
    subtype = _text(ident, "SubtypeId") or ""
    if not subtype:
        return None
    size_el = node.find("Size")
    if size_el is None:
        size_el = node.find("{*}Size")
    if size_el is not None:
        sx = max(1, int(float(size_el.attrib.get("x", 1))))
        sy = max(1, int(float(size_el.attrib.get("y", 1))))
        sz = max(1, int(float(size_el.attrib.get("z", 1))))
    else:
        sx = sy = sz = 1
    offset_el = node.find("ModelOffset") or node.find("{*}ModelOffset")
    if offset_el is not None:
        offset = (
            float(offset_el.attrib.get("x", 0) or 0),
            float(offset_el.attrib.get("y", 0) or 0),
            float(offset_el.attrib.get("z", 0) or 0),
        )
    else:
        offset = (0.0, 0.0, 0.0)
    model = _text(node, "Model") or ""
    return BlockDefinition(
        type_id=type_id,
        subtype_id=subtype,
        cube_size=_text(node, "CubeSize") or "Large",
        block_topology=_text(node, "BlockTopology") or "TriangleMesh",
        cube_topology=_text(node, "CubeTopology") or "Box",
        size_x=sx,
        size_y=sy,
        size_z=sz,
        model_path=model.replace("/", "\\"),
        model_offset=offset,
    )


def _text(element: ET.Element, tag: str) -> Optional[str]:
    child = element.find(tag)
    if child is None:
        child = element.find(f"{{*}}{tag}")
    if child is not None and child.text and child.text.strip():
        return child.text.strip()
    return None
