"""
Parse CubeBlocks definitions from a local Space Engineers install.

Caches definition metadata under AppData. Definition file changes invalidate
the cache, including changes that do not replace SpaceEngineers.exe.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple
import xml.etree.ElementTree as ET

import safe_xml
from resource_paths import user_data_dir
from se_assets.block_identity import normalize_type

CATALOG_SCHEMA = 3


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
    pcu: int = 0
    components: Dict[str, int] = field(default_factory=dict)
    dlc: Tuple[str, ...] = ()
    public: bool = True

    @property
    def key(self) -> str:
        return definition_key(self.type_id, self.subtype_id)

    @property
    def size(self) -> Tuple[int, int, int]:
        return (self.size_x, self.size_y, self.size_z)


def definition_key(type_id: str, subtype_id: str) -> str:
    return f"{normalize_type(type_id)}/{subtype_id}"


def _cache_path() -> Path:
    return user_data_dir() / "cube_catalog_cache.json"


class CubeBlockCatalog:
    """Subtype → definition index built from Content/Data/CubeBlocks."""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self.install: Optional[Path] = None
        self.definitions: Dict[str, BlockDefinition] = {}
        self.by_subtype: Dict[str, BlockDefinition] = {}
        self.exe_mtime: float = 0.0
        self.fingerprint: str = ""
        self.cache_path = Path(cache_path) if cache_path else _cache_path()

    def __len__(self) -> int:
        return len(self.definitions)

    def get(self, type_id: str, subtype_id: str) -> Optional[BlockDefinition]:
        hit = self.definitions.get(definition_key(type_id, subtype_id))
        if hit is not None:
            return hit
        return self.by_subtype.get(subtype_id)

    def get_exact(self, type_id: str, subtype_id: str) -> Optional[BlockDefinition]:
        """Use this for conversion; rendering's subtype fallback is not validation."""
        return self.definitions.get(definition_key(type_id, subtype_id))

    def load(self, install: Path, force: bool = False) -> "CubeBlockCatalog":
        root = Path(install)
        exe = root / "Bin64" / "SpaceEngineers.exe"
        try:
            mtime = exe.stat().st_mtime if exe.is_file() else 0.0
        except OSError:
            mtime = 0.0
        data_dir = root / "Content" / "Data"
        files = sorted(data_dir.rglob("*.sbc")) if data_dir.is_dir() else []
        digest = hashlib.sha256()
        for path in files:
            stat = path.stat()
            digest.update(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
        self.fingerprint = digest.hexdigest()
        if not force:
            try:
                if self._try_cache(root, mtime):
                    return self
            except (ValueError, TypeError, KeyError, AttributeError):
                pass  # Cache is disposable; rebuild from the installed definitions.
        self.install = root
        self.exe_mtime = mtime
        self.definitions = {}
        self.by_subtype = {}
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
        if (payload.get("schema") != CATALOG_SCHEMA
                or payload.get("fingerprint") != self.fingerprint
                or payload.get("install") != str(install)
                or abs(float(payload.get("exe_mtime", 0)) - mtime) > 0.5):
            return False
        defs: Dict[str, BlockDefinition] = {}
        by_subtype: Dict[str, BlockDefinition] = {}
        for raw in payload.get("definitions", []):
            definition = BlockDefinition(
                type_id=raw.get("type_id", "CubeBlock"),
                subtype_id=raw.get("subtype_id", ""),
                cube_size=raw.get("cube_size", "Large"),
                block_topology=raw.get("block_topology", "TriangleMesh"),
                cube_topology=infer_cube_topology(
                    raw.get("subtype_id", ""),
                    raw.get("cube_topology", "Box"),
                ),
                size_x=int(raw.get("size_x", 1)),
                size_y=int(raw.get("size_y", 1)),
                size_z=int(raw.get("size_z", 1)),
                model_path=raw.get("model_path", ""),
                model_offset=tuple(raw.get("model_offset", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
                pcu=int(raw.get("pcu", 0)),
                components=raw.get("components", {}),
                dlc=tuple(raw.get("dlc", [])),
                public=bool(raw.get("public", True)),
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
            "schema": CATALOG_SCHEMA,
            "fingerprint": self.fingerprint,
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
    """Each CubeBlocks parent once. `.//CubeBlocks` and `.//{*}CubeBlocks` are the same nodes."""
    seen = set()
    for element in root.iter():
        if safe_xml.local_tag(element.tag) != "CubeBlocks":
            continue
        key = id(element)
        if key in seen:
            continue
        seen.add(key)
        for child in element:
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
    size_el = node.find("Size")
    if size_el is None:
        size_el = node.find("{*}Size")
    if size_el is not None:
        sx = max(1, int(float(size_el.attrib.get("x", 1))))
        sy = max(1, int(float(size_el.attrib.get("y", 1))))
        sz = max(1, int(float(size_el.attrib.get("z", 1))))
    else:
        sx = sy = sz = 1
    offset_el = node.find("ModelOffset")
    if offset_el is None:
        offset_el = node.find("{*}ModelOffset")
    if offset_el is not None:
        offset = (
            float(offset_el.attrib.get("x", 0) or 0),
            float(offset_el.attrib.get("y", 0) or 0),
            float(offset_el.attrib.get("z", 0) or 0),
        )
    else:
        offset = (0.0, 0.0, 0.0)
    model = _text(node, "Model") or ""
    cube_def = node.find("CubeDefinition")
    if cube_def is None:
        cube_def = node.find("{*}CubeDefinition")
    explicit_topo = ""
    if cube_def is not None:
        explicit_topo = _text(cube_def, "CubeTopology") or ""
    if not explicit_topo:
        explicit_topo = _text(node, "CubeTopology") or ""
    components: Counter[str] = Counter()
    for item in node.findall("./{*}Components/{*}Component"):
        components[item.get("Subtype", "")] += int(item.get("Count", 0))
    return BlockDefinition(
        type_id=type_id,
        subtype_id=subtype,
        cube_size=_text(node, "CubeSize") or "Large",
        block_topology=_text(node, "BlockTopology") or "TriangleMesh",
        cube_topology=infer_cube_topology(subtype, explicit_topo),
        size_x=sx,
        size_y=sy,
        size_z=sz,
        model_path=model.replace("/", "\\"),
        model_offset=offset,
        pcu=int(_text(node, "PCU") or 0),
        components=dict(components),
        dlc=tuple(item.text.strip() for item in node.findall("./{*}DLC") + node.findall("./{*}DLCs/{*}DLC") if item.text),
        public=(_text(node, "Public") or "true").lower() != "false",
    )


def infer_cube_topology(subtype: str, explicit: str = "") -> str:
    """
    Official armor stores CubeTopology under CubeDefinition.

    Older catalog caches defaulted a missing tag to Box, which would
    cube-ify slopes under LOD. Infer from the subtype when needed.
    """
    named = (explicit or "").strip()
    if named and named != "Box":
        return named
    blob = (subtype or "").lower()
    rules = (
        ("slope2tip", "Slope2Tip"),
        ("slope2base", "Slope2Base"),
        ("corner2tip", "Corner2Tip"),
        ("corner2base", "Corner2Base"),
        ("invcorner2tip", "InvCorner2Tip"),
        ("invcorner2base", "InvCorner2Base"),
        ("slopedcornertip", "SlopedCornerTip"),
        ("slopedcornerbase", "SlopedCornerBase"),
        ("slopedcorner", "SlopedCorner"),
        ("roundinvcorner", "RoundInvCorner"),
        ("roundcorner", "RoundCorner"),
        ("roundslope", "RoundSlope"),
        ("roundedslope", "RoundedSlope"),
        ("rotatedslope", "RotatedSlope"),
        ("rotatedcorner", "RotatedCorner"),
        ("halfslopeinverted", "HalfSlopeInverted"),
        ("halfslopecorner", "HalfSlopeCorner"),
        ("halfslope", "HalfSlopeBox"),
        ("halfcorner", "HalfCorner"),
        ("invcorner", "InvCorner"),
        ("cornersquare", "CornerSquare"),
        ("corner", "Corner"),
        ("slope", "Slope"),
        ("halfbox", "HalfBox"),
    )
    for token, topology in rules:
        if token in blob:
            return topology
    return named or "Box"


def _text(element: ET.Element, tag: str) -> Optional[str]:
    child = element.find(tag)
    if child is None:
        child = element.find(f"{{*}}{tag}")
    if child is not None and child.text and child.text.strip():
        return child.text.strip()
    return None
