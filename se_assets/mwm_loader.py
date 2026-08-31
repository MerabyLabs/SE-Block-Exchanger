"""
Minimal Space Engineers .mwm reader.

Vanilla cube models are often a container: GeometryDataAsset + LOD
paths, with vertices living in Gyroscope_LOD0.mwm (etc.). Older files
embed Vertices / MeshParts in the same package. Failures return None
so callers can fall back to a box.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class MwmMaterial:
    name: str
    textures: Dict[str, str] = field(default_factory=dict)


@dataclass
class MwmMesh:
    positions: List[Tuple[float, float, float]]
    uvs: List[Tuple[float, float]]
    indices: List[int]
    materials: List[MwmMaterial] = field(default_factory=list)


def _read_u8(buf: memoryview, offset: int) -> Tuple[int, int]:
    return buf[offset], offset + 1


def _read_u32(buf: memoryview, offset: int) -> Tuple[int, int]:
    return struct.unpack_from("<I", buf, offset)[0], offset + 4


def _read_f32(buf: memoryview, offset: int) -> Tuple[float, int]:
    return struct.unpack_from("<f", buf, offset)[0], offset + 4


def _read_string(buf: memoryview, offset: int) -> Tuple[str, int]:
    n = buf[offset]
    offset += 1
    raw = bytes(buf[offset : offset + n])
    offset += n
    try:
        return raw.decode("ascii", errors="replace"), offset
    except Exception:
        return raw.decode("latin-1", errors="replace"), offset


def _read_string_nt(buf: memoryview, offset: int) -> Tuple[str, int]:
    """Length-prefixed string with an optional trailing NUL (LOD paths)."""
    text, offset = _read_string(buf, offset)
    if offset < len(buf) and buf[offset] == 0:
        offset += 1
    return text, offset


def _f16_to_f32(value: int) -> float:
    sign = (value >> 15) & 1
    exp = (value >> 10) & 0x1F
    frac = value & 0x3FF
    if exp == 0:
        if frac == 0:
            return -0.0 if sign else 0.0
        while not (frac & 0x400):
            frac <<= 1
            exp -= 1
        exp += 1
        frac &= ~0x400
    elif exp == 31:
        return float("-inf") if sign else float("inf")
    exp = exp + (127 - 15)
    bits = (sign << 31) | (exp << 23) | (frac << 13)
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def _read_hfloat(buf: memoryview, offset: int) -> Tuple[float, int]:
    raw = struct.unpack_from("<H", buf, offset)[0]
    return _f16_to_f32(raw), offset + 2


def _parse_index(buf: memoryview) -> Tuple[int, Dict[str, int]]:
    section, offset = _read_string(buf, 0)
    if not section:
        raise ValueError("empty mwm section")
    _flag, offset = _read_u32(buf, offset)
    version_s, offset = _read_string(buf, offset)
    if not version_s.startswith("Version:"):
        raise ValueError("missing mwm version")
    version = int(version_s.split(":", 1)[1])
    count, offset = _read_u32(buf, offset)
    if count > 256:
        raise ValueError("implausible mwm index")
    index: Dict[str, int] = {}
    for _ in range(count):
        tag, offset = _read_string(buf, offset)
        loc, offset = _read_u32(buf, offset)
        index[tag] = loc
    return version, index


def _read_geometry_asset(buf: memoryview, loc: int) -> Optional[str]:
    _section, offset = _read_string(buf, loc)
    path, _offset = _read_string(buf, offset)
    return path or None


def _read_lod_paths(buf: memoryview, loc: int) -> List[str]:
    _section, offset = _read_string(buf, loc)
    count, offset = _read_u32(buf, offset)
    paths: List[str] = []
    for _ in range(min(count, 16)):
        _distance, offset = _read_f32(buf, offset)
        path, offset = _read_string_nt(buf, offset)
        if path and ("/" in path or "\\" in path or path.lower().endswith(".mwm")):
            paths.append(path)
    return paths


def _resolve_ref(from_file: Path, relative: str) -> Optional[Path]:
    rel = relative.replace("\\", "/").strip()
    if not rel:
        return None
    if not rel.lower().endswith(".mwm"):
        rel = rel + ".mwm"
    name = Path(rel).name
    candidates = [from_file.parent / name]
    for parent in from_file.parents:
        if parent.name.lower() == "content":
            candidates.append(parent / rel)
            break
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def load_mwm(path: Path, *, quality: str = "high", _depth: int = 0, cancel=None) -> Optional[MwmMesh]:
    """
    Load a Keen MWM. `quality` is "high" (mid official LOD / embedded)
    or "low" (last official LOD) for interactive preview.
    """
    if cancel is not None and cancel():
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if cancel is not None and cancel():
        return None
    if len(data) < 16:
        return None
    buf = memoryview(data)
    try:
        version, index = _parse_index(buf)
    except (struct.error, ValueError, IndexError):
        return None

    if "Vertices" in index and "MeshParts" in index:
        try:
            positions = _load_vertices(buf, index["Vertices"], cancel=cancel)
            if cancel is not None and cancel():
                return None
            uvs = _load_uvs(buf, index.get("TexCoords0"))
            indices, materials = _load_parts(buf, index.get("MeshParts"), version)
        except (struct.error, ValueError, IndexError):
            return None
        if not positions or not indices:
            return None
        usable = [i for i in indices if 0 <= int(i) < len(positions)]
        usable = usable[: len(usable) - (len(usable) % 3)]
        if not usable:
            return None
        if len(uvs) != len(positions):
            uvs = [(0.0, 0.0)] * len(positions)
        return MwmMesh(positions=positions, uvs=uvs, indices=usable, materials=materials)

    if _depth >= 3:
        return None
    lod_paths: List[str] = []
    if "LODs" in index:
        try:
            lod_paths = _read_lod_paths(buf, index["LODs"])
        except (struct.error, ValueError, IndexError):
            lod_paths = []
    geo: Optional[str] = None
    if "GeometryDataAsset" in index:
        try:
            geo = _read_geometry_asset(buf, index["GeometryDataAsset"])
        except (struct.error, ValueError, IndexError):
            geo = None

    candidates: List[str] = []
    if quality == "low":
        candidates.extend(reversed(lod_paths))
        if geo:
            candidates.append(geo)
    else:
        if len(lod_paths) >= 2:
            candidates.append(lod_paths[1])
        candidates.extend(lod_paths)
        if geo:
            candidates.append(geo)
    source = Path(path)
    for rel in candidates:
        if cancel is not None and cancel():
            return None
        resolved = _resolve_ref(source, rel)
        if resolved is None:
            continue
        if quality == "high" and resolved.stem.lower().endswith("_lod0"):
            mid = resolved.with_name(resolved.stem[:-1] + "2" + resolved.suffix)
            if mid.is_file():
                resolved = mid
        loaded = load_mwm(resolved, quality="high", _depth=_depth + 1, cancel=cancel)
        if loaded is not None:
            return loaded
    return None


def _load_vertices(buf: memoryview, loc: int, cancel=None) -> List[Tuple[float, float, float]]:
    _section, offset = _read_string(buf, loc)
    count, offset = _read_u32(buf, offset)
    if count > 2_000_000:
        raise ValueError("implausible vertex count")
    if cancel is not None and cancel():
        return []
    nbytes = count * 8
    if offset + nbytes > len(buf):
        raise ValueError("truncated vertices")
    raw = np.frombuffer(bytes(buf[offset:offset + nbytes]), dtype="<f2")
    xyz = raw.reshape(count, 4)[:, :3].astype(np.float32, copy=False)
    return [(float(row[0]), float(row[1]), float(row[2])) for row in xyz]


def _load_uvs(buf: memoryview, loc: Optional[int]) -> List[Tuple[float, float]]:
    if loc is None:
        return []
    _section, offset = _read_string(buf, loc)
    count, offset = _read_u32(buf, offset)
    nbytes = count * 4
    if offset + nbytes > len(buf):
        return []
    raw = np.frombuffer(bytes(buf[offset:offset + nbytes]), dtype="<f2")
    uv = raw.reshape(count, 2).astype(np.float32, copy=False)
    return [(float(row[0]), float(row[1])) for row in uv]


def _load_parts(
    buf: memoryview,
    loc: Optional[int],
    version: int,
) -> Tuple[List[int], List[MwmMaterial]]:
    if loc is None:
        return [], []
    _section, offset = _read_string(buf, loc)
    n_parts, offset = _read_u32(buf, offset)
    indices: List[int] = []
    materials: List[MwmMaterial] = []
    for _ in range(min(n_parts, 64)):
        _hash, offset = _read_u32(buf, offset)
        if version < 1052001:
            _technique, offset = _read_u32(buf, offset)
        count, offset = _read_u32(buf, offset)
        if count > 2_000_000:
            break
        if count:
            end = offset + count * 4
            if end > len(buf):
                break
            indices.extend(
                int(v) for v in np.frombuffer(bytes(buf[offset:end]), dtype="<u4")
            )
            offset = end
        has_mat = bool(buf[offset])
        offset += 1
        if has_mat:
            try:
                material, offset = _load_material(buf, offset, version)
                materials.append(material)
            except (struct.error, ValueError, IndexError):
                break
    return indices, materials


def _load_material(buf: memoryview, offset: int, version: int) -> Tuple[MwmMaterial, int]:
    name, offset = _read_string(buf, offset)
    n_params, offset = _read_u32(buf, offset)
    if n_params > 64:
        raise ValueError("implausible material params")
    textures: Dict[str, str] = {}
    for _ in range(n_params):
        key, offset = _read_string(buf, offset)
        value, offset = _read_string(buf, offset)
        textures[key] = value
    # 01157001+ dropped diffuse/specular vec3s: gloss + technique only.
    _gloss, offset = _read_f32(buf, offset)
    if version < 1150000:
        offset += 12  # diffuse
        offset += 12  # specular
    _technique, offset = _read_string(buf, offset)
    return MwmMaterial(name=name, textures=textures), offset
