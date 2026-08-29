"""
Resolve a render mesh for a block: CubeTopology, then MWM, then a sized box.

Derived GPU-ready arrays stay in memory. Optional PNG cache under AppData
is only used for decoded DDS color-mask previews, never next to the game.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from se_assets.cube_catalog import BlockDefinition
from se_assets.mwm_loader import load_mwm
from se_render.topology import MeshData, topology_mesh


class MeshLibrary:
    def __init__(self, install: Optional[Path] = None) -> None:
        self.install = Path(install) if install else None
        self._meshes: Dict[str, MeshData] = {}

    def set_install(self, install: Optional[Path]) -> None:
        self.install = Path(install) if install else None
        self._meshes.clear()

    def mesh_for(
        self,
        definition: Optional[BlockDefinition],
        subtype: str = "",
        size: Tuple[int, int, int] = (1, 1, 1),
        grid_size: str = "Large",
    ) -> MeshData:
        if definition is not None:
            key = f"def:{definition.key}:{definition.cube_topology}:{definition.size}:{definition.cube_size}"
            size = definition.size
            grid_size = definition.cube_size or grid_size
        else:
            key = f"box:{subtype}:{size}:{grid_size}"
        cached = self._meshes.get(key)
        if cached is not None:
            return cached

        cell = 2.5 if str(grid_size).lower() != "small" else 0.5
        mesh: Optional[MeshData] = None
        from_mwm = False
        if definition is not None and definition.block_topology == "Cube":
            mesh = topology_mesh(definition.cube_topology)
        if mesh is None and definition is not None and definition.model_path and self.install:
            mesh = self._from_mwm(definition.model_path)
            from_mwm = mesh is not None
        if mesh is None:
            mesh = topology_mesh("Box")
            from_mwm = False

        sx, sy, sz = size
        if from_mwm:
            # MWM is already in meters with origin at the block center.
            prepared = mesh
        else:
            scale = np.array((sx * cell, sy * cell, sz * cell), dtype=np.float32)
            half = scale * 0.5
            prepared = MeshData(
                positions=mesh.positions * scale - half,
                normals=mesh.normals,
                uvs=mesh.uvs,
                indices=mesh.indices,
            )
        self._meshes[key] = prepared
        return prepared

    def _from_mwm(self, relative: str) -> Optional[MeshData]:
        if self.install is None:
            return None
        rel = relative.replace("\\", "/")
        if not rel.lower().endswith(".mwm"):
            rel = rel + ".mwm"
        path = self.install / "Content" / rel
        if not path.is_file():
            path = self.install / "Content" / "Models" / Path(rel).name
        if not path.is_file():
            return None
        loaded = load_mwm(path)
        if loaded is None or not loaded.positions or not loaded.indices:
            return None
        positions = np.asarray(loaded.positions, dtype=np.float32)
        uvs = np.asarray(loaded.uvs, dtype=np.float32) if loaded.uvs else np.zeros((len(loaded.positions), 2), dtype=np.float32)
        indices = np.asarray(loaded.indices, dtype=np.uint32)
        normals = _compute_normals(positions, indices)
        return MeshData(positions=positions, normals=normals, uvs=uvs, indices=indices)


def _compute_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(positions)
    if len(indices) < 3:
        normals[:, 1] = 1.0
        return normals
    tris = indices.reshape((-1, 3)) if indices.size % 3 == 0 else indices[: indices.size - (indices.size % 3)].reshape((-1, 3))
    for a, b, c in tris:
        n = np.cross(positions[b] - positions[a], positions[c] - positions[a])
        normals[a] += n
        normals[b] += n
        normals[c] += n
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths < 1e-8] = 1.0
    return (normals / lengths).astype(np.float32)
