"""
Generate unit-cell meshes for Keen CubeTopology values.

Coordinates are in the 0–1 occupancy cell, Y-up. Multi-cell blocks are
scaled by the definition Size later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np


@dataclass
class MeshData:
    positions: np.ndarray  # (N, 3) float32
    normals: np.ndarray  # (N, 3) float32
    uvs: np.ndarray  # (N, 2) float32
    indices: np.ndarray  # (M,) uint32

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])


def _tri(positions: Sequence[Tuple[float, float, float]], indices: Sequence[int]) -> MeshData:
    pos = np.asarray(positions, dtype=np.float32)
    idx = np.asarray(indices, dtype=np.uint32)
    # Expand to unique-per-corner so each triangle can carry a flat normal.
    out_pos: List[Tuple[float, float, float]] = []
    out_nrm: List[Tuple[float, float, float]] = []
    out_uv: List[Tuple[float, float]] = []
    out_idx: List[int] = []
    for i in range(0, len(idx), 3):
        a, b, c = pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]]
        n = np.cross(b - a, c - a)
        length = np.linalg.norm(n)
        if length < 1e-8:
            n = np.array((0.0, 1.0, 0.0), dtype=np.float32)
        else:
            n = n / length
        base = len(out_pos)
        for vertex, uv in ((a, (0.0, 0.0)), (b, (1.0, 0.0)), (c, (0.5, 1.0))):
            out_pos.append(tuple(float(v) for v in vertex))
            out_nrm.append((float(n[0]), float(n[1]), float(n[2])))
            out_uv.append(uv)
        out_idx.extend((base, base + 1, base + 2))
    return MeshData(
        positions=np.asarray(out_pos, dtype=np.float32),
        normals=np.asarray(out_nrm, dtype=np.float32),
        uvs=np.asarray(out_uv, dtype=np.float32),
        indices=np.asarray(out_idx, dtype=np.uint32),
    )


def box_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),  # z=0 (forward / -Z face toward 0)
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
    ]
    # Faces: -Z, +Z, -Y, +Y, -X, +X
    idx = [
        0, 1, 2, 0, 2, 3,
        5, 4, 7, 5, 7, 6,
        4, 5, 1, 4, 1, 0,
        3, 2, 6, 3, 6, 7,
        4, 0, 3, 4, 3, 7,
        1, 5, 6, 1, 6, 2,
    ]
    return _tri(p, idx)


def slope_mesh() -> MeshData:
    # Ramp rising from z=1 toward z=0 along +Y? Keen Slope: full base on bottom,
    # diagonal from bottom-forward to top-back. Common: keep bottom, drop +Y/+Z edge.
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 1, 0), (1, 1, 0),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,  # bottom
        0, 4, 5, 0, 5, 1,  # back (z=0)
        3, 2, 5, 3, 5, 4,  # slope
        0, 3, 4,          # left
        1, 5, 2,          # right
    ]
    return _tri(p, idx)


def corner_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 1, 0),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        0, 4, 1,
        0, 3, 4,
        1, 4, 2,
        3, 2, 4,
    ]
    return _tri(p, idx)


def inv_corner_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 1, 0), (1, 1, 0), (0, 1, 1),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        0, 4, 5, 0, 5, 1,
        0, 3, 6, 0, 6, 4,
        4, 6, 5,
        1, 5, 2,
        3, 2, 5, 3, 5, 6,
    ]
    return _tri(p, idx)


def half_box_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0.5, 0), (0, 0.5, 0),
        (0, 0, 1), (1, 0, 1), (1, 0.5, 1), (0, 0.5, 1),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        5, 4, 7, 5, 7, 6,
        4, 5, 1, 4, 1, 0,
        3, 2, 6, 3, 6, 7,
        4, 0, 3, 4, 3, 7,
        1, 5, 6, 1, 6, 2,
    ]
    return _tri(p, idx)


def slope2_base_mesh() -> MeshData:
    # Two-cell slope base: full 1x1x1 with a shallow ramp on top (y from 0 to 0.5).
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 0.5, 0), (1, 0.5, 0),
        (0, 0, 1), (1, 0, 1),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        0, 4, 5, 0, 5, 1,
        3, 2, 5, 3, 5, 4,
        0, 3, 4,
        1, 5, 2,
    ]
    return _tri(p, idx)


def slope2_tip_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 1, 0), (1, 1, 0),
        (0, 0.5, 1), (1, 0.5, 1),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        0, 4, 5, 0, 5, 1,
        3, 2, 7, 3, 7, 6,
        4, 6, 7, 4, 7, 5,
        0, 3, 6, 0, 6, 4,
        1, 5, 7, 1, 7, 2,
    ]
    return _tri(p, idx)


def corner_square_mesh() -> MeshData:
    p = [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1),
        (0, 1, 0), (1, 1, 0), (0, 1, 1),
    ]
    idx = [
        0, 1, 2, 0, 2, 3,
        0, 4, 5, 0, 5, 1,
        0, 3, 6, 0, 6, 4,
        4, 6, 5,
        5, 6, 2,
        6, 3, 2,
    ]
    return _tri(p, idx)


_GENERATORS = {
    "Box": box_mesh,
    "StandaloneBox": box_mesh,
    "Slope": slope_mesh,
    "Corner": corner_mesh,
    "InvCorner": inv_corner_mesh,
    "HalfBox": half_box_mesh,
    "Slope2Base": slope2_base_mesh,
    "Slope2Tip": slope2_tip_mesh,
    "CornerSquare": corner_square_mesh,
    "RoundSlope": slope_mesh,
    "RoundedSlope": slope_mesh,
    "RoundCorner": corner_mesh,
    "RoundInvCorner": inv_corner_mesh,
    "RotatedSlope": slope_mesh,
    "RotatedCorner": corner_mesh,
    "HalfSlopeBox": slope_mesh,
    "HalfSlopeInverted": inv_corner_mesh,
    "HalfSlopeCorner": corner_mesh,
    "HalfCorner": corner_mesh,
    "Corner2Base": slope2_base_mesh,
    "Corner2Tip": slope2_tip_mesh,
    "InvCorner2Base": inv_corner_mesh,
    "InvCorner2Tip": corner_mesh,
    "SlopedCorner": corner_mesh,
    "SlopedCornerBase": slope2_base_mesh,
    "SlopedCornerTip": corner_mesh,
}


_CACHE: Dict[str, MeshData] = {}


def topology_mesh(name: str) -> MeshData:
    key = name or "Box"
    if key in _CACHE:
        return _CACHE[key]
    generator = _GENERATORS.get(key, box_mesh)
    mesh = generator()
    _CACHE[key] = mesh
    return mesh


def known_topologies() -> Tuple[str, ...]:
    return tuple(sorted(_GENERATORS))
