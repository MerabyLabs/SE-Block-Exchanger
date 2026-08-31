"""
Generate unit-cell meshes for Keen CubeTopology values.

Coordinates are in the 0–1 occupancy cell, Y-up. Multi-cell blocks are
scaled by the definition Size later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np


# Shrink unit-cell meshes toward the cell center so adjacent same-color
# armor shows a dark seam and does not z-fight on shared faces. Slightly
# larger than a hairline so huge hulls keep a depth gap after projection.
_CELL_INSET = 0.020

# Axis-aligned unit-cell faces. Used for occupancy culling. Diagonals stay 0.
FACE_NONE = 0
FACE_NEG_X = 1
FACE_POS_X = 2
FACE_NEG_Y = 4
FACE_POS_Y = 8
FACE_NEG_Z = 16
FACE_POS_Z = 32
FACE_ALL = 63

_FACE_PLANES = (
    (FACE_NEG_X, 0, 0.0),
    (FACE_POS_X, 0, 1.0),
    (FACE_NEG_Y, 1, 0.0),
    (FACE_POS_Y, 1, 1.0),
    (FACE_NEG_Z, 2, 0.0),
    (FACE_POS_Z, 2, 1.0),
)


@dataclass
class MeshData:
    positions: np.ndarray  # (N, 3) float32
    normals: np.ndarray  # (N, 3) float32
    uvs: np.ndarray  # (N, 2) float32 — per-face 0–1, used for crease darkening
    indices: np.ndarray  # (M,) uint32
    face_axes: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.uint8))

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.size // 3)


def face_uvs_for_triangle(
    a: Sequence[float],
    b: Sequence[float],
    c: Sequence[float],
    normal: Sequence[float],
) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    """
    Project a triangle onto its plane and normalize to the 2D AABB.

    Two triangles of a unit quad both span 0–1, so cube-face edges darken
    and the shared diagonal does not become a hard UV seam.
    """
    n = np.asarray(normal, dtype=np.float32)
    up = np.array((0.0, 1.0, 0.0), dtype=np.float32)
    if abs(float(n[1])) > 0.9:
        up = np.array((1.0, 0.0, 0.0), dtype=np.float32)
    tangent = np.cross(up, n)
    tlen = float(np.linalg.norm(tangent))
    if tlen < 1e-8:
        tangent = np.array((1.0, 0.0, 0.0), dtype=np.float32)
    else:
        tangent = tangent / tlen
    bitangent = np.cross(n, tangent)
    pts = np.asarray((a, b, c), dtype=np.float32)
    u = pts @ tangent
    v = pts @ bitangent
    umin, umax = float(u.min()), float(u.max())
    vmin, vmax = float(v.min()), float(v.max())
    du = umax - umin if umax - umin > 1e-8 else 1.0
    dv = vmax - vmin if vmax - vmin > 1e-8 else 1.0
    return (
        ((float(u[0]) - umin) / du, (float(v[0]) - vmin) / dv),
        ((float(u[1]) - umin) / du, (float(v[1]) - vmin) / dv),
        ((float(u[2]) - umin) / du, (float(v[2]) - vmin) / dv),
    )


def _face_uvs_batch(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    normals: np.ndarray,
) -> np.ndarray:
    """Vectorized face_uvs_for_triangle. Returns (T, 3, 2)."""
    n = normals
    up = np.zeros_like(n)
    up[:, 1] = 1.0
    up[np.abs(n[:, 1]) > 0.9] = (1.0, 0.0, 0.0)
    tangent = np.cross(up, n)
    tlen = np.linalg.norm(tangent, axis=1, keepdims=True)
    fallback = tlen[:, 0] < 1e-8
    tangent = tangent / np.maximum(tlen, 1e-20)
    tangent[fallback] = (1.0, 0.0, 0.0)
    bitangent = np.cross(n, tangent)
    pts = np.stack((a, b, c), axis=1)
    u = np.einsum("tij,tj->ti", pts, tangent)
    v = np.einsum("tij,tj->ti", pts, bitangent)
    umin = u.min(axis=1, keepdims=True)
    umax = u.max(axis=1, keepdims=True)
    vmin = v.min(axis=1, keepdims=True)
    vmax = v.max(axis=1, keepdims=True)
    du = umax - umin
    dv = vmax - vmin
    du = np.where(du > 1e-8, du, 1.0)
    dv = np.where(dv > 1e-8, dv, 1.0)
    return np.stack(((u - umin) / du, (v - vmin) / dv), axis=2)


def _triangle_face_bits_batch(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    epsilon: float = 0.02,
) -> np.ndarray:
    """Vectorized triangle_face_bit. First matching plane wins."""
    pts = np.stack((a, b, c), axis=1)
    bits = np.zeros(a.shape[0], dtype=np.uint8)
    unset = np.ones(a.shape[0], dtype=bool)
    for bit, axis, value in _FACE_PLANES:
        on_plane = np.all(np.abs(pts[:, :, axis] - value) <= epsilon, axis=1)
        take = unset & on_plane
        if np.any(take):
            bits[take] = bit
            unset &= ~take
        if not np.any(unset):
            break
    return bits


def flatten_indexed_mesh(positions: np.ndarray, indices: np.ndarray) -> MeshData:
    """Expand indexed triangles to unique corners with flat normals and face UVs."""
    pos = np.asarray(positions, dtype=np.float32)
    raw = np.asarray(indices, dtype=np.uint32).reshape(-1)
    usable = raw.size - (raw.size % 3)
    if usable < 3 or pos.size == 0:
        empty = np.zeros((0, 3), dtype=np.float32)
        return MeshData(
            positions=empty,
            normals=empty,
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            face_axes=np.zeros((0,), dtype=np.uint8),
        )
    idx = raw[:usable].reshape((-1, 3))
    a = pos[idx[:, 0]]
    b = pos[idx[:, 1]]
    c = pos[idx[:, 2]]
    n = np.cross(b - a, c - a)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    degenerate = length[:, 0] < 1e-8
    n = n / np.maximum(length, 1e-20)
    n[degenerate] = (0.0, 1.0, 0.0)
    uvs = _face_uvs_batch(a, b, c, n)
    n_tri = int(idx.shape[0])
    return MeshData(
        positions=np.ascontiguousarray(np.stack((a, b, c), axis=1).reshape(-1, 3), dtype=np.float32),
        normals=np.ascontiguousarray(np.repeat(n.astype(np.float32, copy=False), 3, axis=0)),
        uvs=np.ascontiguousarray(uvs.reshape(-1, 2), dtype=np.float32),
        indices=np.arange(n_tri * 3, dtype=np.uint32),
        face_axes=np.ascontiguousarray(_triangle_face_bits_batch(a, b, c)),
    )


def _tri(positions: Sequence[Tuple[float, float, float]], indices: Sequence[int]) -> MeshData:
    mesh = flatten_indexed_mesh(
        np.asarray(positions, dtype=np.float32),
        np.asarray(indices, dtype=np.uint32),
    )
    if mesh.vertex_count == 0:
        return mesh
    inset = (mesh.positions - 0.5) * (1.0 - _CELL_INSET) + 0.5
    return MeshData(
        positions=inset.astype(np.float32),
        normals=mesh.normals,
        uvs=mesh.uvs,
        indices=mesh.indices,
        face_axes=mesh.face_axes,
    )


def triangle_face_bit(
    a: Sequence[float],
    b: Sequence[float],
    c: Sequence[float],
    epsilon: float = 0.02,
) -> int:
    """
    Tag a unit-cell triangle with the axis-aligned face it sits on.

    Slope hypotenuses and any triangle that is not fully on a cell wall
    return FACE_NONE so occupancy culling stays conservative.
    """
    pts = (a, b, c)
    for bit, axis, value in _FACE_PLANES:
        if all(abs(float(p[axis]) - value) <= epsilon for p in pts):
            return bit
    return FACE_NONE


def cull_mesh_faces(mesh: MeshData, mask: int) -> MeshData:
    """Drop triangles whose unit-cell face is fully occluded (mask bits)."""
    if not mask or mesh.vertex_count == 0 or mesh.indices.size < 3:
        return mesh
    axes = mesh.face_axes
    triangle_count = mesh.triangle_count
    if axes is None or axes.size != triangle_count:
        return mesh
    keep = [i for i, axis in enumerate(axes.tolist()) if not (int(axis) & int(mask))]
    if len(keep) == triangle_count:
        return mesh
    if not keep:
        empty = np.zeros((0, 3), dtype=np.float32)
        return MeshData(
            positions=empty,
            normals=empty,
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            face_axes=np.zeros((0,), dtype=np.uint8),
        )
    pos: List[Tuple[float, float, float]] = []
    nrm: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    idx: List[int] = []
    out_axes: List[int] = []
    raw = mesh.indices.reshape((-1, 3))
    for out_i, tri in enumerate(keep):
        a, b, c = (int(v) for v in raw[tri])
        base = out_i * 3
        for src in (a, b, c):
            p = mesh.positions[src]
            n = mesh.normals[src]
            uv = mesh.uvs[src] if mesh.uvs is not None and src < len(mesh.uvs) else (0.0, 0.0)
            pos.append((float(p[0]), float(p[1]), float(p[2])))
            nrm.append((float(n[0]), float(n[1]), float(n[2])))
            uvs.append((float(uv[0]), float(uv[1])))
        idx.extend((base, base + 1, base + 2))
        out_axes.append(int(axes[tri]))
    return MeshData(
        positions=np.asarray(pos, dtype=np.float32),
        normals=np.asarray(nrm, dtype=np.float32),
        uvs=np.asarray(uvs, dtype=np.float32),
        indices=np.asarray(idx, dtype=np.uint32),
        face_axes=np.asarray(out_axes, dtype=np.uint8),
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


def simplify_mesh(mesh: MeshData, max_triangles: int = 96) -> MeshData:
    """
    Keep the largest triangles so functional MWM stays a readable
    silhouette while orbiting. Idle/mouse-up uses the full mesh.
    """
    count = mesh.triangle_count
    limit = max(4, int(max_triangles))
    if count <= limit or mesh.indices.size < 3 or mesh.vertex_count == 0:
        return mesh
    raw = mesh.indices.reshape((-1, 3))
    a = mesh.positions[raw[:, 0]]
    b = mesh.positions[raw[:, 1]]
    c = mesh.positions[raw[:, 2]]
    areas = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    keep = np.argpartition(-areas, limit - 1)[:limit]
    keep = np.sort(keep)
    pos: List[Tuple[float, float, float]] = []
    nrm: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    idx: List[int] = []
    out_axes: List[int] = []
    axes = mesh.face_axes
    for out_i, tri in enumerate(keep.tolist()):
        ia, ib, ic = (int(v) for v in raw[tri])
        base = out_i * 3
        for src in (ia, ib, ic):
            p = mesh.positions[src]
            n = mesh.normals[src]
            uv = mesh.uvs[src] if mesh.uvs is not None and src < len(mesh.uvs) else (0.0, 0.0)
            pos.append((float(p[0]), float(p[1]), float(p[2])))
            nrm.append((float(n[0]), float(n[1]), float(n[2])))
            uvs.append((float(uv[0]), float(uv[1])))
        idx.extend((base, base + 1, base + 2))
        if axes is not None and axes.size == count:
            out_axes.append(int(axes[tri]))
        else:
            out_axes.append(FACE_NONE)
    return MeshData(
        positions=np.asarray(pos, dtype=np.float32),
        normals=np.asarray(nrm, dtype=np.float32),
        uvs=np.asarray(uvs, dtype=np.float32),
        indices=np.asarray(idx, dtype=np.uint32),
        face_axes=np.asarray(out_axes, dtype=np.uint8),
    )
