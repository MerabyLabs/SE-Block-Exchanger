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
from se_render.topology import MeshData, flatten_indexed_mesh, simplify_mesh, topology_mesh


class MeshLibrary:
    def __init__(self, install: Optional[Path] = None) -> None:
        self.install = Path(install) if install else None
        self._meshes: Dict[str, MeshData] = {}
        self._mwm_flat: Dict[Tuple[str, str], Optional[MeshData]] = {}

    def set_install(self, install: Optional[Path]) -> None:
        self.install = Path(install) if install else None
        self._meshes.clear()
        self._mwm_flat.clear()

    def cache_key(
        self,
        definition: Optional[BlockDefinition],
        subtype: str = "",
        size: Tuple[int, int, int] = (1, 1, 1),
        grid_size: str = "Large",
        lod: bool = False,
        skip_mwm: bool = False,
    ) -> str:
        is_cube = definition is not None and definition.block_topology == "Cube"
        if definition is not None:
            key = f"def:{definition.key}:{definition.cube_topology}:{definition.size}:{definition.cube_size}"
        else:
            key = f"box:{subtype}:{size}:{grid_size}"
        if skip_mwm and not is_cube:
            return f"skipmwm:{key}"
        if lod and not is_cube:
            return f"lod:{key}"
        return key

    def has_mesh(
        self,
        definition: Optional[BlockDefinition],
        subtype: str = "",
        size: Tuple[int, int, int] = (1, 1, 1),
        grid_size: str = "Large",
        lod: bool = False,
        skip_mwm: bool = False,
    ) -> bool:
        return self.cache_key(definition, subtype, size, grid_size, lod, skip_mwm) in self._meshes

    def mesh_for(
        self,
        definition: Optional[BlockDefinition],
        subtype: str = "",
        size: Tuple[int, int, int] = (1, 1, 1),
        grid_size: str = "Large",
        lod: bool = False,
        prefer_box: bool = False,
        skip_mwm: bool = False,
        cancel=None,
    ) -> MeshData:
        """
        Resolve a block mesh. `lod` may simplify functional MWM.

        Official Cube topologies (slopes/corners) are never replaced with
        a box. `prefer_box` is a legacy alias for `lod` and does not
        cube-ify armor.
        """
        lod = bool(lod or prefer_box)
        skip_mwm = bool(skip_mwm)
        if cancel is not None and cancel():
            return topology_mesh("Box")
        if definition is not None:
            size = definition.size
            grid_size = definition.cube_size or grid_size
        key = self.cache_key(definition, subtype, size, grid_size, lod, skip_mwm)
        cached = self._meshes.get(key)
        if cached is not None:
            return cached
        is_cube = definition is not None and definition.block_topology == "Cube"

        cell = 2.5 if str(grid_size).lower() != "small" else 0.5
        mesh: Optional[MeshData] = None
        from_mwm = False
        if is_cube and definition is not None:
            mesh = topology_mesh(definition.cube_topology)
        if (
            mesh is None
            and not skip_mwm
            and definition is not None
            and definition.model_path
            and self.install
        ):
            mesh = self._from_mwm(
                definition.model_path,
                quality="low" if lod else "high",
                cancel=cancel,
            )
            from_mwm = mesh is not None
            if mesh is not None:
                mesh = simplify_mesh(mesh, max_triangles=96 if lod else 320)
        if mesh is None:
            if cancel is not None and cancel():
                return topology_mesh("Box")
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
                face_axes=mesh.face_axes,
            )
        self._meshes[key] = prepared
        return prepared

    def _from_mwm(self, relative: str, quality: str = "high", cancel=None) -> Optional[MeshData]:
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
        if cancel is not None and cancel():
            return None
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        cache_key = (resolved.lower(), quality)
        if cache_key in self._mwm_flat:
            return self._mwm_flat[cache_key]
        loaded = load_mwm(path, quality=quality, cancel=cancel)
        if loaded is None or not loaded.positions or not loaded.indices:
            self._mwm_flat[cache_key] = None
            return None
        positions = np.asarray(loaded.positions, dtype=np.float32)
        indices = np.asarray(loaded.indices, dtype=np.uint32)
        # Flat-shaded unique corners so MWM faces read as planes, not a blob.
        mesh = flatten_indexed_mesh(positions, indices)
        self._mwm_flat[cache_key] = mesh
        return mesh
