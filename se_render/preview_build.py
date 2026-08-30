"""
CPU-side 3D preview assembly: occupancy culling, explode offsets, LOD.

Safe to run on a worker thread. No OpenGL calls live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.dissection import (
    DISSECT_DECKS,
    DISSECT_PEEL,
    DISSECT_RADIAL,
    block_world_center,
    dissect_max_offsets,
    explode_max_offsets,
    explode_offset,
    explode_offset_for_mode,
    grid_centroids,
    pick_identity,
    selection_caption,
    selection_meta,
)
from se_render.camera import aabb_center_radius
from se_render.occupancy import (
    BlockOccupancy,
    OccupancyMap,
    block_shell_layer,
    build_occupancy,
    occupancy_shell_layers,
    occupied_cells,
    definition_size,
    plan_blocks,
    relax_culling,
    should_relax_culling,
)
from se_render.hsv import hsv_offset_to_rgb
from se_render.orientation import cell_size_meters, mul_mat4, translation_mat4
from se_render.preview_style import (
    EXTREME_BLOCK_THRESHOLD,
    HUGE_SHIP_BLOCK_THRESHOLD,
    PREVIEW_INSTANCE_CAP,
    apply_albedo_tint,
    block_material,
    inspect_category,
    inspect_category_code,
    is_armor_block,
)
from se_render.scene_graph import BlockInstance, PreviewScene
from se_render.topology import MeshData, cull_mesh_faces

STAGE_SHELL = "shell"
STAGE_MESHES = "meshes"
STAGE_FULL = "full"


class BuildGeneration:
    """Monotonic token so ship-change / isolate / clear can ignore stale jobs."""

    def __init__(self) -> None:
        self.generation = 0

    def begin(self) -> int:
        self.generation += 1
        return self.generation

    def cancel(self) -> int:
        return self.begin()

    def is_current(self, generation: int) -> bool:
        return generation == self.generation


@dataclass(slots=True)
class PickRecord:
    """
    GPU pick hit. instance_id is the PreviewScene.blocks index (shader id).

    A later in-preview editor should key blocks with pick_identity() —
    grid + Min + entity_id — not the rebuild-sensitive instance_id.
    Offsets are instance attributes; do not remesh to move a cube.
    """

    instance_id: int
    grid_name: str
    subtype: str
    center: Tuple[float, float, float]
    aabb_min: Tuple[float, float, float]
    aabb_max: Tuple[float, float, float]
    explode_offset: Tuple[float, float, float]
    type_id: str = ""
    entity_id: str = ""
    grid_entity_id: str = ""
    local_min: Tuple[int, int, int] = (0, 0, 0)
    is_armor: bool = True
    explode_peel: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    explode_decks: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    explode_radial: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    shell_layer: int = 0
    category: str = "armor"
    category_code: int = 0

    def offset_for_mode(self, mode: str) -> Tuple[float, float, float]:
        return explode_offset_for_mode(self, mode)

    def identity(self) -> Tuple[str, Tuple[int, int, int], str]:
        return pick_identity(self)

    def caption(self) -> str:
        return selection_caption(self)

    def meta(self) -> dict:
        return selection_meta(self)


@dataclass
class CpuBatch:
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    indices: np.ndarray
    models: np.ndarray
    colors: np.ndarray
    params: np.ndarray
    explode: np.ndarray
    instance_ids: np.ndarray
    grid_names: List[str]
    accents: np.ndarray
    kind: str = "armor"
    grid_entity_ids: List[str] = field(default_factory=list)
    # Three precomputed 100% offsets. Shader picks the mode; slider is u_explode.
    explode_peel: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float32))
    explode_decks: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float32))
    explode_radial: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float32))
    inspect: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float32))


@dataclass
class PreviewCpuScene:
    assembled: List[CpuBatch] = field(default_factory=list)
    exploded: List[CpuBatch] = field(default_factory=list)
    assembled_lod: List[CpuBatch] = field(default_factory=list)
    exploded_lod: List[CpuBatch] = field(default_factory=list)
    picks: List[PickRecord] = field(default_factory=list)
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 10.0
    block_count: int = 0
    huge: bool = False
    generation: int = 0
    aabb_min: Tuple[float, float, float] = (-1.0, -1.0, -1.0)
    aabb_max: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    stage: str = STAGE_FULL
    simplified: bool = False
    shown_count: int = 0
    occupied: OccupancyMap = field(default_factory=dict)
    plans: List[BlockOccupancy] = field(default_factory=list)
    shell_layers: List[int] = field(default_factory=list)
    source_blocks: List[BlockInstance] = field(default_factory=list)
    dissect_modes: List[str] = field(default_factory=list)
    offset_peel: Optional[np.ndarray] = None
    offset_decks: Optional[np.ndarray] = None
    offset_radial: Optional[np.ndarray] = None
    has_functional_mwm: bool = False
    keep_indices: Optional[List[int]] = None


def _aabb_from_mesh(mesh: MeshData, model: Sequence[Sequence[float]]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    if mesh.vertex_count == 0:
        t = (model[0][3], model[1][3], model[2][3])
        return t, t
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    # Sample a few corners via the mesh AABB in local space, then transform.
    local_min = mesh.positions.min(axis=0)
    local_max = mesh.positions.max(axis=0)
    corners = (
        (local_min[0], local_min[1], local_min[2]),
        (local_max[0], local_min[1], local_min[2]),
        (local_min[0], local_max[1], local_min[2]),
        (local_min[0], local_min[1], local_max[2]),
        (local_max[0], local_max[1], local_min[2]),
        (local_max[0], local_min[1], local_max[2]),
        (local_min[0], local_max[1], local_max[2]),
        (local_max[0], local_max[1], local_max[2]),
    )
    for x, y, z in corners:
        wx = model[0][0] * x + model[0][1] * y + model[0][2] * z + model[0][3]
        wy = model[1][0] * x + model[1][1] * y + model[1][2] * z + model[1][3]
        wz = model[2][0] * x + model[2][1] * y + model[2][2] * z + model[2][3]
        mins[0] = min(mins[0], wx)
        mins[1] = min(mins[1], wy)
        mins[2] = min(mins[2], wz)
        maxs[0] = max(maxs[0], wx)
        maxs[1] = max(maxs[1], wy)
        maxs[2] = max(maxs[2], wz)
    return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])


def _instance_model(block: BlockInstance, size: Tuple[int, int, int]) -> list:
    sx, sy, sz = size
    cell = cell_size_meters(block.grid_size)
    offset = translation_mat4((
        (sx - 1) * 0.5 * cell,
        (sy - 1) * 0.5 * cell,
        (sz - 1) * 0.5 * cell,
    ))
    return mul_mat4(block.world_matrix, offset)


def _cheap_aabb(
    block: BlockInstance,
    size: Tuple[int, int, int],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    cell = cell_size_meters(block.grid_size)
    cx, cy, cz = block_world_center(block)
    hx = max(1, int(size[0])) * cell * 0.5
    hy = max(1, int(size[1])) * cell * 0.5
    hz = max(1, int(size[2])) * cell * 0.5
    return (cx - hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz + hz)


def _zero_offsets(count: int) -> np.ndarray:
    return np.zeros((int(count), 3), dtype=np.float32)


def _as_offset_array(offsets: Optional[Sequence], count: int) -> np.ndarray:
    if offsets is None:
        return _zero_offsets(count)
    arr = np.asarray(offsets, dtype=np.float32)
    if arr.size == 0:
        return _zero_offsets(count)
    return arr.reshape(-1, 3)


def _needs_mwm(definition) -> bool:
    return (
        definition is not None
        and definition.block_topology != "Cube"
        and bool(getattr(definition, "model_path", "") or "")
    )


def _scene_has_mwm(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
) -> bool:
    if catalog is None:
        return False
    seen = set()
    for block in blocks:
        key = (block.type_id, block.subtype)
        if key in seen:
            continue
        seen.add(key)
        if _needs_mwm(catalog.get(block.type_id, block.subtype)):
            return True
    return False


def _flatten_model(model: Sequence[Sequence[float]]) -> Tuple[float, ...]:
    return (
        model[0][0], model[1][0], model[2][0], model[3][0],
        model[0][1], model[1][1], model[2][1], model[3][1],
        model[0][2], model[1][2], model[2][2], model[3][2],
        model[0][3], model[1][3], model[2][3], model[3][3],
    )


def _assign_shell_layers(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
    occupied: OccupancyMap,
    layer_by_grid: Dict[str, Dict],
) -> List[int]:
    layers: List[int] = []
    defn_cache: Dict[Tuple[str, str], object] = {}
    for block in blocks:
        grid_layers = layer_by_grid.get(block.grid_entity_id, {})
        if catalog is None:
            definition = None
        else:
            key = (block.type_id, block.subtype)
            definition = defn_cache.get(key)
            if key not in defn_cache:
                definition = catalog.get(block.type_id, block.subtype)
                defn_cache[key] = definition
        size = definition_size(definition) if definition is not None else (1, 1, 1)
        if size == (1, 1, 1):
            layers.append(int(grid_layers.get(block.local_min, 0)))
        else:
            cells = occupied_cells(block.local_min, size, block.forward, block.up)
            layers.append(block_shell_layer(cells, grid_layers))
    return layers


@dataclass
class _InstanceColumns:
    models: np.ndarray
    colors: np.ndarray
    params: np.ndarray
    accents: np.ndarray
    inspect: np.ndarray
    kinds: np.ndarray
    has_functional_mwm: bool


def _build_instance_columns(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
    shell_layers: Sequence[int],
    indices: Optional[Sequence[int]] = None,
) -> _InstanceColumns:
    n = len(blocks)
    models = np.zeros((n, 16), dtype=np.float32)
    colors = np.zeros((n, 3), dtype=np.float32)
    params = np.zeros((n, 3), dtype=np.float32)
    accents = np.zeros((n, 3), dtype=np.float32)
    inspect = np.zeros((n, 3), dtype=np.float32)
    kinds = np.zeros((n,), dtype=np.uint8)
    style_map: Dict[Tuple[str, str], object] = {}
    tint_map: Dict[Tuple, Tuple[float, float, float]] = {}
    defn_cache: Dict[Tuple[str, str], object] = {}
    size_cache: Dict[Tuple[str, str], Tuple[int, int, int]] = {}
    has_mwm = False
    walk = indices if indices is not None else range(n)
    for i in walk:
        block = blocks[i]
        skey = (block.type_id, block.subtype)
        style = style_map.get(skey)
        if style is None:
            style = block_material(block.type_id, block.subtype)
            style_map[skey] = style
        if skey in defn_cache:
            definition = defn_cache[skey]
            size = size_cache[skey]
        elif catalog is None:
            definition = None
            size = (1, 1, 1)
            defn_cache[skey] = None
            size_cache[skey] = size
        else:
            definition = catalog.get(block.type_id, block.subtype)
            size = definition_size(definition)
            defn_cache[skey] = definition
            size_cache[skey] = size
            if _needs_mwm(definition):
                has_mwm = True
        m = block.world_matrix
        if size == (1, 1, 1):
            models[i] = _flatten_model(m)
        else:
            models[i] = _flatten_model(_instance_model(block, size))
        rgb = block.color_rgb
        if rgb is None:
            rgb = hsv_offset_to_rgb(0.0, 0.0, 0.0)
        tkey = (rgb[0], rgb[1], rgb[2], style.is_armor, style.tint_mix, style.category)
        tinted = tint_map.get(tkey)
        if tinted is None:
            tinted = apply_albedo_tint(rgb, style)
            tint_map[tkey] = tinted
        colors[i] = tinted
        params[i] = (style.edge_strength, style.jitter, style.spec)
        accents[i] = (style.metal, style.rim, 1.0 if style.is_armor else 0.0)
        kinds[i] = 0 if style.is_armor else 1
        inspect[i, 0] = float(shell_layers[i]) if i < len(shell_layers) else 0.0
        inspect[i, 1] = float(inspect_category_code(block.type_id, block.subtype))
    return _InstanceColumns(models, colors, params, accents, inspect, kinds, has_mwm)


def _offset_row(arr: np.ndarray, index: int) -> Tuple[float, float, float]:
    if arr is None or getattr(arr, "size", 0) == 0 or index >= arr.shape[0]:
        return (0.0, 0.0, 0.0)
    row = arr[index]
    return (float(row[0]), float(row[1]), float(row[2]))


def _collect_batches(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
    meshes: MeshLibrary,
    *,
    explode: bool,
    lod: bool,
    offsets_peel: Sequence,
    offsets_decks: Sequence,
    offsets_radial: Sequence,
    shell_layers: Optional[Sequence[int]] = None,
    plans: Optional[Sequence[BlockOccupancy]] = None,
    skip_mwm: bool = False,
    cheap_picks: bool = True,
    keep_indices: Optional[Sequence[int]] = None,
    columns: Optional[_InstanceColumns] = None,
) -> Tuple[List[CpuBatch], List[PickRecord]]:
    groups: Dict[Tuple[int, int, int], List[int]] = {}
    mesh_for_key: Dict[Tuple[int, int, int], MeshData] = {}
    used_plans = plans if plans is not None else plan_blocks(blocks, catalog)
    walk = keep_indices if keep_indices is not None else range(len(blocks))
    cols = columns or _build_instance_columns(blocks, catalog, shell_layers or [])
    peel = _as_offset_array(offsets_peel, len(blocks))
    decks = _as_offset_array(offsets_decks, len(blocks))
    radial = _as_offset_array(offsets_radial, len(blocks))
    defn_cache: Dict[Tuple[str, str], object] = {}

    for i in walk:
        block = blocks[i]
        plan = used_plans[i]
        if plan.fully_enclosed and not explode:
            continue
        skey = (block.type_id, block.subtype)
        if catalog is None:
            definition = None
        elif skey in defn_cache:
            definition = defn_cache[skey]
        else:
            definition = catalog.get(block.type_id, block.subtype)
            defn_cache[skey] = definition
        size = definition_size(definition)
        mesh = meshes.mesh_for(
            definition, block.subtype, size, block.grid_size, lod=lod, skip_mwm=skip_mwm
        )
        cull_mask = 0 if explode else (plan.cull_mask if plan.topology_cullable else 0)
        kind = int(cols.kinds[i])
        key = (kind, id(mesh), cull_mask)
        if key not in mesh_for_key:
            culled = cull_mesh_faces(mesh, cull_mask) if cull_mask else mesh
            if culled.vertex_count == 0 and mesh.vertex_count > 0:
                culled = mesh
            mesh_for_key[key] = culled
        groups.setdefault(key, []).append(i)

    batches: List[CpuBatch] = []
    picks: List[PickRecord] = []
    for key in sorted(groups.keys()):
        indices = groups[key]
        mesh = mesh_for_key[key]
        if mesh.vertex_count == 0 or mesh.indices.size == 0:
            continue
        uvs = mesh.uvs
        if uvs is None or len(uvs) != mesh.vertex_count:
            uvs = np.zeros((mesh.vertex_count, 2), dtype=np.float32)
        idx = np.asarray(indices, dtype=np.int32)
        models = np.ascontiguousarray(cols.models[idx], dtype=np.float32)
        colors = np.ascontiguousarray(cols.colors[idx], dtype=np.float32)
        params = np.ascontiguousarray(cols.params[idx], dtype=np.float32)
        accents = np.ascontiguousarray(cols.accents[idx], dtype=np.float32)
        inspect_arr = np.ascontiguousarray(cols.inspect[idx], dtype=np.float32)
        peel_arr = np.ascontiguousarray(peel[idx], dtype=np.float32)
        decks_arr = np.ascontiguousarray(decks[idx], dtype=np.float32)
        radial_arr = np.ascontiguousarray(radial[idx], dtype=np.float32)
        explode_arr = peel_arr
        instance_ids = idx.astype(np.float32, copy=False)
        grid_names = [blocks[i].grid_name for i in indices]
        grid_entity_ids = [blocks[i].grid_entity_id for i in indices]
        kind_name = "armor" if key[0] == 0 else "functional"
        if not lod:
            for slot, block_index in enumerate(indices):
                block = blocks[block_index]
                definition = defn_cache.get((block.type_id, block.subtype))
                if catalog is not None and definition is None:
                    definition = catalog.get(block.type_id, block.subtype)
                size = definition_size(definition)
                aabb_min, aabb_max = _cheap_aabb(block, size)
                layer = int(shell_layers[block_index]) if shell_layers is not None else 0
                picks.append(
                    PickRecord(
                        instance_id=block_index,
                        grid_name=block.grid_name,
                        subtype=block.subtype,
                        center=block_world_center(block),
                        aabb_min=aabb_min,
                        aabb_max=aabb_max,
                        explode_offset=_offset_row(peel, block_index),
                        type_id=block.type_id,
                        entity_id=block.entity_id,
                        grid_entity_id=block.grid_entity_id,
                        local_min=block.local_min,
                        is_armor=is_armor_block(block.type_id, block.subtype),
                        explode_peel=_offset_row(peel, block_index),
                        explode_decks=_offset_row(decks, block_index),
                        explode_radial=_offset_row(radial, block_index),
                        shell_layer=layer,
                        category=inspect_category(block.type_id, block.subtype),
                        category_code=inspect_category_code(block.type_id, block.subtype),
                    )
                )
        batches.append(
            CpuBatch(
                positions=np.ascontiguousarray(mesh.positions, dtype=np.float32),
                normals=np.ascontiguousarray(mesh.normals, dtype=np.float32),
                uvs=np.ascontiguousarray(uvs, dtype=np.float32),
                indices=np.ascontiguousarray(mesh.indices, dtype=np.uint32),
                models=models,
                colors=colors,
                params=params,
                explode=explode_arr,
                instance_ids=instance_ids,
                grid_names=grid_names,
                grid_entity_ids=grid_entity_ids,
                accents=accents,
                kind=kind_name,
                explode_peel=peel_arr,
                explode_decks=decks_arr,
                explode_radial=radial_arr,
                inspect=inspect_arr,
            )
        )
    return batches, picks


def _aabb_from_picks(
    picks: Sequence[PickRecord],
    center: Tuple[float, float, float],
    radius: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    if not picks:
        pad = max(4.0, float(radius))
        return (
            (center[0] - pad, center[1] - pad, center[2] - pad),
            (center[0] + pad, center[1] + pad, center[2] + pad),
        )
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for rec in picks:
        for i in range(3):
            mins[i] = min(mins[i], rec.aabb_min[i])
            maxs[i] = max(maxs[i], rec.aabb_max[i])
    return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])


def scene_bounds(blocks: Sequence[BlockInstance]) -> Tuple[Tuple[float, float, float], float]:
    if not blocks:
        return (0.0, 0.0, 0.0), 10.0
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for block in blocks:
        cx, cy, cz = block_world_center(block)
        half = cell_size_meters(block.grid_size) * 0.5
        mins[0] = min(mins[0], cx - half)
        mins[1] = min(mins[1], cy - half)
        mins[2] = min(mins[2], cz - half)
        maxs[0] = max(maxs[0], cx + half)
        maxs[1] = max(maxs[1], cy + half)
        maxs[2] = max(maxs[2], cz + half)
    return aabb_center_radius(mins, maxs)


def _select_preview_indices(
    blocks: Sequence[BlockInstance],
    plans: Sequence[BlockOccupancy],
    shell_layers: Sequence[int],
    *,
    explode: bool,
    cap: int,
) -> Tuple[Optional[List[int]], bool]:
    """Keep a representative subset when instance count would blow GPU/memory."""
    eligible: List[int] = []
    for i, plan in enumerate(plans):
        if plan.fully_enclosed and not explode:
            continue
        eligible.append(i)
    if len(eligible) <= cap:
        return None, False
    functional: List[int] = []
    shell_armor: List[int] = []
    inner_armor: List[int] = []
    for i in eligible:
        block = blocks[i]
        if not is_armor_block(block.type_id, block.subtype):
            functional.append(i)
        elif int(shell_layers[i]) <= 0:
            shell_armor.append(i)
        else:
            inner_armor.append(i)
    keep = list(functional) + list(shell_armor)
    leftover = cap - len(keep)
    if leftover > 0 and inner_armor:
        step = max(1, (len(inner_armor) + leftover - 1) // leftover)
        keep.extend(inner_armor[::step][:leftover])
    elif leftover < 0:
        keep = keep[:cap]
    return keep, True


def _visible_plan_count(plans: Sequence[BlockOccupancy]) -> int:
    return sum(1 for plan in plans if not plan.fully_enclosed)


def _empty_cpu(
    blocks: Sequence[BlockInstance],
    center: Tuple[float, float, float],
    radius: float,
    huge: bool,
    generation: int,
    stage_key: str,
) -> PreviewCpuScene:
    return PreviewCpuScene(
        center=center,
        radius=radius,
        block_count=len(blocks),
        huge=huge,
        generation=generation,
        stage=stage_key,
        source_blocks=list(blocks),
    )


def build_preview_cpu(
    scene: PreviewScene,
    catalog: Optional[CubeBlockCatalog] = None,
    meshes: Optional[MeshLibrary] = None,
    generation: int = 0,
    stage: str = STAGE_FULL,
    cancel: Optional[BuildGeneration] = None,
    prior: Optional[PreviewCpuScene] = None,
) -> PreviewCpuScene:
    """Assemble GPU-ready arrays. Catalog/MWM I/O belongs here, not on orbit."""
    blocks = list(scene.blocks)
    library = meshes or MeshLibrary()
    center, radius = scene_bounds(blocks)
    huge = len(blocks) > HUGE_SHIP_BLOCK_THRESHOLD
    stage_key = (stage or STAGE_FULL).strip().lower()
    if stage_key not in (STAGE_SHELL, STAGE_MESHES, STAGE_FULL):
        stage_key = STAGE_FULL
    if cancel is not None and not cancel.is_current(generation):
        return _empty_cpu(blocks, center, radius, huge, generation, stage_key)

    reuse = (
        prior is not None
        and prior.source_blocks is not None
        and len(prior.source_blocks) == len(blocks)
        and prior.plans
        and prior.occupied is not None
    )
    if reuse:
        occupied = prior.occupied
        plans = list(prior.plans)
        shell_layers = list(prior.shell_layers)
        offset_peel = prior.offset_peel
        offset_decks = prior.offset_decks
        offset_radial = prior.offset_radial
        dissect_modes = list(prior.dissect_modes)
    else:
        occupied = build_occupancy(blocks, catalog) if blocks else {}
        plans = plan_blocks(blocks, catalog, occupied=occupied)
        if cancel is not None and not cancel.is_current(generation):
            return _empty_cpu(blocks, center, radius, huge, generation, stage_key)
        layer_by_grid = {gid: occupancy_shell_layers(cells) for gid, cells in occupied.items()}
        shell_layers = _assign_shell_layers(blocks, catalog, occupied, layer_by_grid)
        offset_peel = offset_decks = offset_radial = None
        dissect_modes = []

    zeros = _zero_offsets(len(blocks))
    peel = offset_peel if offset_peel is not None else zeros
    decks = offset_decks if offset_decks is not None else zeros
    radial = offset_radial if offset_radial is not None else zeros

    skip_mwm = stage_key == STAGE_SHELL
    cap = PREVIEW_INSTANCE_CAP
    if len(blocks) >= EXTREME_BLOCK_THRESHOLD and stage_key == STAGE_SHELL:
        cap = min(cap, PREVIEW_INSTANCE_CAP)

    shown_est = _visible_plan_count(plans)
    if should_relax_culling(len(blocks), shown_est):
        plans = relax_culling(plans, 1)
        shown_est = _visible_plan_count(plans)
        if should_relax_culling(len(blocks), shown_est):
            plans = relax_culling(plans, 2)

    keep, simplified = _select_preview_indices(
        blocks, plans, shell_layers, explode=False, cap=cap
    )
    column_idx: Optional[List[int]] = None
    if stage_key == STAGE_SHELL:
        if keep is not None:
            column_idx = list(keep)
        else:
            column_idx = [i for i, plan in enumerate(plans) if not plan.fully_enclosed]
    columns = _build_instance_columns(blocks, catalog, shell_layers, indices=column_idx)
    has_mwm = columns.has_functional_mwm or _scene_has_mwm(blocks, catalog)
    if cancel is not None and not cancel.is_current(generation):
        return _empty_cpu(blocks, center, radius, huge, generation, stage_key)

    assembled, picks = _collect_batches(
        blocks, catalog, library, explode=False, lod=False,
        offsets_peel=peel, offsets_decks=decks, offsets_radial=radial,
        shell_layers=shell_layers, plans=plans, skip_mwm=skip_mwm,
        cheap_picks=True, keep_indices=keep if keep is not None else column_idx,
        columns=columns,
    )

    exploded: List[CpuBatch] = []
    exploded_picks: List[PickRecord] = []
    if stage_key == STAGE_FULL:
        exploded, exploded_picks = _collect_batches(
            blocks, catalog, library, explode=True, lod=False,
            offsets_peel=peel, offsets_decks=decks, offsets_radial=radial,
            shell_layers=shell_layers, plans=plans, skip_mwm=False,
            cheap_picks=True, keep_indices=None, columns=columns,
        )
    elif reuse and prior is not None and prior.exploded:
        exploded = prior.exploded
        exploded_picks = [rec for rec in prior.picks]

    used_picks = exploded_picks or picks
    aabb_min, aabb_max = _aabb_from_picks(used_picks, center, radius)
    center, radius = aabb_center_radius(aabb_min, aabb_max)
    shown = instance_count(assembled)
    if shown < len(blocks) and keep is not None:
        simplified = True
    if len(blocks) >= EXTREME_BLOCK_THRESHOLD and stage_key == STAGE_SHELL:
        simplified = True
    return PreviewCpuScene(
        assembled=assembled,
        exploded=exploded,
        assembled_lod=assembled,
        exploded_lod=exploded,
        picks=used_picks,
        center=center,
        radius=radius,
        block_count=len(blocks),
        huge=huge,
        generation=generation,
        aabb_min=aabb_min,
        aabb_max=aabb_max,
        stage=stage_key,
        simplified=simplified,
        shown_count=shown,
        occupied=occupied,
        plans=plans,
        shell_layers=shell_layers,
        source_blocks=blocks,
        dissect_modes=dissect_modes,
        offset_peel=offset_peel,
        offset_decks=offset_decks,
        offset_radial=offset_radial,
        has_functional_mwm=has_mwm,
        keep_indices=list(keep) if keep is not None else None,
    )


def _write_offsets_into_batches(
    batches: Sequence[CpuBatch],
    mode: str,
    offsets: np.ndarray,
) -> None:
    if not batches:
        return
    off = np.ascontiguousarray(offsets, dtype=np.float32).reshape(-1, 3)
    for batch in batches:
        ids = np.asarray(batch.instance_ids, dtype=np.int64)
        if ids.size == 0:
            continue
        selected = off[ids]
        if mode == DISSECT_DECKS:
            batch.explode_decks = selected
        elif mode == DISSECT_RADIAL:
            batch.explode_radial = selected
        else:
            batch.explode_peel = selected
            batch.explode = selected


def apply_dissect_mode(
    cpu: PreviewCpuScene,
    mode: str,
    catalog: Optional[CubeBlockCatalog] = None,
) -> PreviewCpuScene:
    """Compute one dissect mode and write it into existing batches. No remesh."""
    key = (mode or DISSECT_PEEL).strip().lower()
    if key in cpu.dissect_modes:
        return cpu
    blocks = cpu.source_blocks
    if not blocks:
        return cpu
    offsets = np.asarray(
        dissect_max_offsets(blocks, key, catalog, occupied=cpu.occupied),
        dtype=np.float32,
    ).reshape(-1, 3)
    if key == DISSECT_DECKS:
        cpu.offset_decks = offsets
    elif key == DISSECT_RADIAL:
        cpu.offset_radial = offsets
    else:
        cpu.offset_peel = offsets
    _write_offsets_into_batches(cpu.assembled, key, offsets)
    _write_offsets_into_batches(cpu.exploded, key, offsets)
    _write_offsets_into_batches(cpu.assembled_lod, key, offsets)
    _write_offsets_into_batches(cpu.exploded_lod, key, offsets)
    for rec in cpu.picks:
        row = offsets[rec.instance_id] if 0 <= rec.instance_id < len(offsets) else (0.0, 0.0, 0.0)
        triple = (float(row[0]), float(row[1]), float(row[2]))
        if key == DISSECT_DECKS:
            rec.explode_decks = triple
        elif key == DISSECT_RADIAL:
            rec.explode_radial = triple
        else:
            rec.explode_peel = triple
            rec.explode_offset = triple
    if key not in cpu.dissect_modes:
        cpu.dissect_modes.append(key)
    return cpu


def ensure_exploded_batches(
    cpu: PreviewCpuScene,
    catalog: Optional[CubeBlockCatalog] = None,
    meshes: Optional[MeshLibrary] = None,
) -> PreviewCpuScene:
    """Add the interior instance set once, when Dissect first needs it."""
    if cpu.exploded:
        return cpu
    blocks = cpu.source_blocks
    if not blocks:
        return cpu
    library = meshes or MeshLibrary()
    zeros = _zero_offsets(len(blocks))
    peel = cpu.offset_peel if cpu.offset_peel is not None else zeros
    decks = cpu.offset_decks if cpu.offset_decks is not None else zeros
    radial = cpu.offset_radial if cpu.offset_radial is not None else zeros
    columns = _build_instance_columns(blocks, catalog, cpu.shell_layers)
    exploded, picks = _collect_batches(
        blocks, catalog, library, explode=True, lod=False,
        offsets_peel=peel, offsets_decks=decks, offsets_radial=radial,
        shell_layers=cpu.shell_layers, plans=cpu.plans, skip_mwm=False,
        cheap_picks=True, keep_indices=None, columns=columns,
    )
    cpu.exploded = exploded
    cpu.exploded_lod = exploded
    if picks:
        cpu.picks = picks
    return cpu


def pending_mwm_definitions(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
    library: MeshLibrary,
) -> List:
    seen = set()
    out = []
    if catalog is None:
        return out
    for block in blocks:
        definition = catalog.get(block.type_id, block.subtype)
        if not _needs_mwm(definition):
            continue
        key = definition.key
        if key in seen:
            continue
        seen.add(key)
        if library.has_mesh(definition, block.subtype, definition.size, block.grid_size, skip_mwm=False):
            continue
        out.append(definition)
    return out


def _slice_batch(batch: CpuBatch, keep: Sequence[int]) -> CpuBatch:
    idx = np.asarray(keep, dtype=np.int32)
    eids = list(getattr(batch, "grid_entity_ids", None) or [])
    inspect = getattr(batch, "inspect", None)
    if inspect is not None and getattr(inspect, "size", 0):
        inspect_arr = _slice_offsets(inspect, batch.explode, idx)
    else:
        inspect_arr = np.zeros((len(keep), 3), dtype=np.float32)
    return CpuBatch(
        positions=batch.positions,
        normals=batch.normals,
        uvs=batch.uvs,
        indices=batch.indices,
        models=batch.models[idx],
        colors=batch.colors[idx],
        params=batch.params[idx],
        explode=batch.explode[idx],
        instance_ids=batch.instance_ids[idx],
        grid_names=[batch.grid_names[i] for i in keep],
        grid_entity_ids=[eids[i] if i < len(eids) else "" for i in keep],
        accents=batch.accents[idx],
        kind=batch.kind,
        explode_peel=_slice_offsets(batch.explode_peel, batch.explode, idx),
        explode_decks=_slice_offsets(batch.explode_decks, batch.explode, idx),
        explode_radial=_slice_offsets(batch.explode_radial, batch.explode, idx),
        inspect=inspect_arr,
    )


def filter_batch(
    batch: CpuBatch,
    grid_name: Optional[str] = None,
    grid_entity_id: Optional[str] = None,
) -> Optional[CpuBatch]:
    if grid_entity_id:
        eids = getattr(batch, "grid_entity_ids", None) or []
        if eids:
            keep = [i for i, eid in enumerate(eids) if eid == grid_entity_id]
        elif grid_name:
            keep = [i for i, name in enumerate(batch.grid_names) if name == grid_name]
        else:
            return None
    elif grid_name:
        keep = [i for i, name in enumerate(batch.grid_names) if name == grid_name]
    else:
        return batch
    if not keep:
        return None
    if len(keep) == len(batch.instance_ids):
        return batch
    return _slice_batch(batch, keep)


def _slice_offsets(primary: np.ndarray, fallback: np.ndarray, idx: np.ndarray) -> np.ndarray:
    src = primary if primary is not None and getattr(primary, "size", 0) else fallback
    return src[idx]


def filter_batches(
    batches: Sequence[CpuBatch],
    grid_name: Optional[str] = None,
    grid_entity_id: Optional[str] = None,
) -> List[CpuBatch]:
    if not grid_name and not grid_entity_id:
        return list(batches)
    out: List[CpuBatch] = []
    for batch in batches:
        filtered = filter_batch(batch, grid_name, grid_entity_id)
        if filtered is not None:
            out.append(filtered)
    return out


def should_alias_lod_sets(full: Sequence[CpuBatch], lod: Sequence[CpuBatch]) -> bool:
    """True when LOD is the same batch list — do not upload it twice."""
    if lod is full:
        return True
    if not full and not lod:
        return True
    if len(lod) != len(full):
        return False
    return all(a is b for a, b in zip(lod, full))


def split_upload_chunks(batches: Sequence[CpuBatch], chunk: int) -> List[List[CpuBatch]]:
    size = max(1, int(chunk))
    return [list(batches[i:i + size]) for i in range(0, len(batches), size)]


def _merge_refined_batches(
    old: Sequence[CpuBatch],
    new: Sequence[CpuBatch],
    drop_ids: set,
) -> List[CpuBatch]:
    kept: List[CpuBatch] = []
    for batch in old:
        ids = [int(round(float(i))) for i in batch.instance_ids]
        keep = [j for j, iid in enumerate(ids) if iid not in drop_ids]
        if not keep:
            continue
        if len(keep) == len(ids):
            kept.append(batch)
        else:
            kept.append(_slice_batch(batch, keep))
    kept.extend(new)
    return kept


def refine_mwm_cpu(
    cpu: PreviewCpuScene,
    catalog: Optional[CubeBlockCatalog],
    library: MeshLibrary,
    definitions: Sequence,
) -> PreviewCpuScene:
    """
    Remesh only instances whose MWM just arrived. Reuses occupancy, plans, picks.
    """
    if cpu is None or not definitions or not cpu.source_blocks:
        return cpu
    keys = {getattr(item, "key", None) for item in definitions}
    keys.discard(None)
    if not keys:
        return cpu
    blocks = cpu.source_blocks
    affected = []
    for i, block in enumerate(blocks):
        definition = catalog.get(block.type_id, block.subtype) if catalog is not None else None
        if definition is not None and definition.key in keys:
            affected.append(i)
    if not affected:
        return cpu
    columns = _build_instance_columns(blocks, catalog, cpu.shell_layers, indices=affected)
    zeros = _zero_offsets(len(blocks))
    peel = cpu.offset_peel if cpu.offset_peel is not None else zeros
    decks = cpu.offset_decks if cpu.offset_decks is not None else zeros
    radial = cpu.offset_radial if cpu.offset_radial is not None else zeros
    new_assembled, new_picks = _collect_batches(
        blocks, catalog, library, explode=False, lod=False,
        offsets_peel=peel, offsets_decks=decks, offsets_radial=radial,
        shell_layers=cpu.shell_layers, plans=cpu.plans, skip_mwm=False,
        cheap_picks=True, keep_indices=affected, columns=columns,
    )
    drop = set(affected)
    cpu.assembled = _merge_refined_batches(cpu.assembled, new_assembled, drop)
    cpu.assembled_lod = cpu.assembled
    if cpu.exploded:
        new_exploded, _ = _collect_batches(
            blocks, catalog, library, explode=True, lod=False,
            offsets_peel=peel, offsets_decks=decks, offsets_radial=radial,
            shell_layers=cpu.shell_layers, plans=cpu.plans, skip_mwm=False,
            cheap_picks=True, keep_indices=affected, columns=columns,
        )
        cpu.exploded = _merge_refined_batches(cpu.exploded, new_exploded, drop)
        cpu.exploded_lod = cpu.exploded
    if new_picks and cpu.picks:
        pick_map = {p.instance_id: p for p in new_picks}
        cpu.picks = [pick_map.get(p.instance_id, p) for p in cpu.picks]
    elif new_picks:
        cpu.picks = new_picks
    cpu.has_functional_mwm = True
    cpu.shown_count = instance_count(cpu.assembled)
    return cpu


def triangle_count(batches: Iterable[CpuBatch]) -> int:
    total = 0
    for batch in batches:
        total += int(batch.indices.size // 3) * int(batch.models.shape[0])
    return total


def instance_count(batches: Iterable[CpuBatch]) -> int:
    return sum(int(batch.models.shape[0]) for batch in batches)


__all__ = [
    "BuildGeneration",
    "CpuBatch",
    "PickRecord",
    "PreviewCpuScene",
    "STAGE_FULL",
    "STAGE_MESHES",
    "STAGE_SHELL",
    "apply_dissect_mode",
    "build_preview_cpu",
    "ensure_exploded_batches",
    "explode_max_offsets",
    "explode_offset",
    "explode_offset_for_mode",
    "filter_batches",
    "grid_centroids",
    "instance_count",
    "pending_mwm_definitions",
    "pick_identity",
    "refine_mwm_cpu",
    "should_alias_lod_sets",
    "split_upload_chunks",
    "selection_caption",
    "selection_meta",
    "triangle_count",
]
