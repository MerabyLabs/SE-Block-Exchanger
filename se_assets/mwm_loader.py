"""
Minimal Space Engineers .mwm reader.

MWM is Keen's tagged binary model package. This loader understands the
index + Vertices / TexCoords0 / MeshParts layout used by vanilla cube
models. Failures return None so callers can fall back to a box.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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


def load_mwm(path: Path) -> Optional[MwmMesh]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 16:
        return None
    buf = memoryview(data)
    try:
        section, offset = _read_string(buf, 0)
        if not section:
            return None
        _flag, offset = _read_u32(buf, offset)
        version_s, offset = _read_string(buf, offset)
        if not version_s.startswith("Version:"):
            return None
        version = int(version_s.split(":", 1)[1])
        count, offset = _read_u32(buf, offset)
        index: Dict[str, int] = {}
        for _ in range(count):
            tag, offset = _read_string(buf, offset)
            loc, offset = _read_u32(buf, offset)
            index[tag] = loc
    except (struct.error, ValueError, IndexError):
        return None

    if "Vertices" not in index:
        return None
    try:
        positions = _load_vertices(buf, index["Vertices"])
        uvs = _load_uvs(buf, index.get("TexCoords0"))
        indices, materials = _load_parts(buf, index.get("MeshParts"), version)
    except (struct.error, ValueError, IndexError):
        return None
    if not positions or not indices:
        return None
    if len(uvs) != len(positions):
        uvs = [(0.0, 0.0)] * len(positions)
    return MwmMesh(positions=positions, uvs=uvs, indices=indices, materials=materials)


def _load_vertices(buf: memoryview, loc: int) -> List[Tuple[float, float, float]]:
    _section, offset = _read_string(buf, loc)
    count, offset = _read_u32(buf, offset)
    out: List[Tuple[float, float, float]] = []
    for _ in range(count):
        x, offset = _read_hfloat(buf, offset)
        y, offset = _read_hfloat(buf, offset)
        z, offset = _read_hfloat(buf, offset)
        _w, offset = _read_hfloat(buf, offset)
        out.append((x, y, z))
    return out


def _load_uvs(buf: memoryview, loc: Optional[int]) -> List[Tuple[float, float]]:
    if loc is None:
        return []
    _section, offset = _read_string(buf, loc)
    count, offset = _read_u32(buf, offset)
    out: List[Tuple[float, float]] = []
    for _ in range(count):
        u, offset = _read_hfloat(buf, offset)
        v, offset = _read_hfloat(buf, offset)
        out.append((u, v))
    return out


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
    for _ in range(n_parts):
        _hash, offset = _read_u32(buf, offset)
        if version < 1052001:
            _technique, offset = _read_u32(buf, offset)
        count, offset = _read_u32(buf, offset)
        for _i in range(count):
            value, offset = _read_u32(buf, offset)
            indices.append(value)
        has_mat = bool(buf[offset])
        offset += 1
        if has_mat:
            material, offset = _load_material(buf, offset)
            materials.append(material)
    return indices, materials


def _load_material(buf: memoryview, offset: int) -> Tuple[MwmMaterial, int]:
    name, offset = _read_string(buf, offset)
    n_params, offset = _read_u32(buf, offset)
    textures: Dict[str, str] = {}
    for _ in range(n_params):
        key, offset = _read_string(buf, offset)
        value, offset = _read_string(buf, offset)
        textures[key] = value
    _gloss, offset = _read_f32(buf, offset)
    offset += 12  # diffuse
    offset += 12  # specular
    _technique, offset = _read_string(buf, offset)
    return MwmMaterial(name=name, textures=textures), offset
