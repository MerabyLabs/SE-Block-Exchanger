"""
Per-grid occupancy and conservative interior-face culling.

A face is culled only when every surface cell on that axis-aligned side
has an occupied neighbor. Slope hypotenuses stay visible. Functional /
MWM meshes are never face-culled; fully enclosed cubes can be skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog
from se_render.orientation import orientation_matrix
from se_render.scene_graph import BlockInstance
from se_render.topology import (
    FACE_ALL,
    FACE_NEG_X,
    FACE_NEG_Y,
    FACE_NEG_Z,
    FACE_POS_X,
    FACE_POS_Y,
    FACE_POS_Z,
)


Cell = Tuple[int, int, int]
OccupancyMap = Dict[str, Set[Cell]]

# Flood only when the padded AABB is compact. Sparse ships (two blocks at
# opposite corners of a huge Min span) must never allocate nx*ny*nz empty cells.
FLOOD_VOLUME_CAP = 80_000

# Dense numpy occupancy for neighbor / onion work. 200³ hangars stay sparse.
DENSE_VOLUME_CAP = 300_000

_PACK_OFFSET = np.int64(1 << 20)
_MISSING = object()

_FACE_BITS_XYZ = np.array(
    (FACE_NEG_X, FACE_POS_X, FACE_NEG_Y, FACE_POS_Y, FACE_NEG_Z, FACE_POS_Z),
    dtype=np.int32,
)
_UNIT_DIRS = np.array(
    ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)),
    dtype=np.int32,
)

# Face bits used when counting remaining exterior faces after culling.
_FACE_BITS = (
    FACE_NEG_X,
    FACE_POS_X,
    FACE_NEG_Y,
    FACE_POS_Y,
    FACE_NEG_Z,
    FACE_POS_Z,
)

# If occupancy would hide almost the whole grid, fall back instead of
# leaving a handful of triangles on a navy canvas.
MIN_VISIBLE_INSTANCE_RATIO = 0.05
MIN_VISIBLE_INSTANCE_BLOCKS = 100
_FACE_LOCAL_DIR = {
    FACE_NEG_X: (-1, 0, 0),
    FACE_POS_X: (1, 0, 0),
    FACE_NEG_Y: (0, -1, 0),
    FACE_POS_Y: (0, 1, 0),
    FACE_NEG_Z: (0, 0, -1),
    FACE_POS_Z: (0, 0, 1),
}

_SIX_DIRS = (
    (-1, 0, 0),
    (1, 0, 0),
    (0, -1, 0),
    (0, 1, 0),
    (0, 0, -1),
    (0, 0, 1),
)


@dataclass(frozen=True)
class BlockOccupancy:
    cells: Tuple[Cell, ...]
    cull_mask: int
    fully_enclosed: bool
    topology_cullable: bool


def definition_size(definition: Optional[BlockDefinition]) -> Tuple[int, int, int]:
    if definition is None:
        return (1, 1, 1)
    return definition.size


def is_topology_cube(definition: Optional[BlockDefinition]) -> bool:
    return definition is not None and definition.block_topology == "Cube"


def is_solid_box(definition: Optional[BlockDefinition]) -> bool:
    """True only for full occupancy cubes. Slopes/corners must not be skipped."""
    if definition is None or definition.block_topology != "Cube":
        return False
    topo = (definition.cube_topology or "Box").replace(" ", "")
    return topo in ("Box", "StandaloneBox")


def occupied_cells(
    min_xyz: Sequence[int],
    size: Sequence[int],
    forward: str = "Forward",
    up: str = "Up",
) -> Tuple[Cell, ...]:
    """Grid cells covered by a block, with Min as the occupancy AABB origin."""
    sx, sy, sz = (max(1, int(size[0])), max(1, int(size[1])), max(1, int(size[2])))
    mx, my, mz = int(min_xyz[0]), int(min_xyz[1]), int(min_xyz[2])
    if sx == sy == sz == 1:
        return ((mx, my, mz),)

    right, up_v, backward = orientation_matrix(forward, up)
    raw: List[Cell] = []
    for i in range(sx):
        for j in range(sy):
            for k in range(sz):
                raw.append(
                    (
                        int(round(i * right[0] + j * up_v[0] + k * backward[0])),
                        int(round(i * right[1] + j * up_v[1] + k * backward[1])),
                        int(round(i * right[2] + j * up_v[2] + k * backward[2])),
                    )
                )
    ox = min(c[0] for c in raw)
    oy = min(c[1] for c in raw)
    oz = min(c[2] for c in raw)
    return tuple((mx + c[0] - ox, my + c[1] - oy, mz + c[2] - oz) for c in raw)


def build_occupancy(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    cancel=None,
) -> OccupancyMap:
    """Occupied cells keyed by grid entity id so subgrids never cull each other."""
    occupied: OccupancyMap = {}
    defn_cache: Dict[Tuple[str, str], Optional[BlockDefinition]] = {}
    for i, block in enumerate(blocks):
        if cancel is not None and (i & 255) == 0 and cancel():
            return {}
        key = (block.type_id, block.subtype)
        if catalog is None:
            definition = None
        elif key in defn_cache:
            definition = defn_cache[key]
        else:
            definition = catalog.get(block.type_id, block.subtype)
            defn_cache[key] = definition
        size = definition_size(definition)
        if size == (1, 1, 1):
            cells = (block.local_min,)
        else:
            cells = occupied_cells(block.local_min, size, block.forward, block.up)
        bucket = occupied.setdefault(block.grid_entity_id, set())
        bucket.update(cells)
    return occupied


def occupancy_padded_volume(occupied: Set[Cell]) -> int:
    """Cell count of the padded AABB. Does not allocate that volume."""
    if not occupied:
        return 0
    xs = [c[0] for c in occupied]
    ys = [c[1] for c in occupied]
    zs = [c[2] for c in occupied]
    return (
        (max(xs) - min(xs) + 3)
        * (max(ys) - min(ys) + 3)
        * (max(zs) - min(zs) + 3)
    )


def occupancy_shell_layers(occupied: Set[Cell], cancel=None) -> Dict[Cell, int]:
    """
    Onion layers from the outside of the occupied set.

    Layer 0 is any occupied cell with a 6-neighbor not in the remaining
    solid. Hiding layer 0 on a solid 3×3×3 leaves only the center cube.

    Compact AABBs use a numpy volume. Sparse ships (two blocks at opposite
    corners of a huge Min span) stay on the set walk and never allocate
    nx*ny*nz empty cells.
    """
    if not occupied:
        return {}
    if occupancy_padded_volume(occupied) <= DENSE_VOLUME_CAP:
        return _shell_layers_dense(occupied, cancel=cancel)
    return _shell_layers_sparse(occupied, cancel=cancel)


def _shell_layers_sparse(occupied: Set[Cell], cancel=None) -> Dict[Cell, int]:
    remaining = set(occupied)
    layers: Dict[Cell, int] = {}
    layer = 0
    while remaining:
        if cancel is not None and cancel():
            return layers
        shell = {
            cell
            for cell in remaining
            if any(
                (cell[0] + dx, cell[1] + dy, cell[2] + dz) not in remaining
                for dx, dy, dz in _SIX_DIRS
            )
        }
        if not shell:
            for cell in remaining:
                layers[cell] = layer
            break
        for cell in shell:
            layers[cell] = layer
        remaining -= shell
        layer += 1
    return layers


def _shell_layers_dense(occupied: Set[Cell], cancel=None) -> Dict[Cell, int]:
    pts = np.array(list(occupied), dtype=np.int32)
    amin = pts.min(axis=0) - 1
    amax = pts.max(axis=0) + 1
    shape = (int(amax[0] - amin[0] + 1), int(amax[1] - amin[1] + 1), int(amax[2] - amin[2] + 1))
    remaining = np.zeros(shape, dtype=np.uint8)
    loc = pts - amin
    remaining[loc[:, 0], loc[:, 1], loc[:, 2]] = 1
    layer_of = np.zeros(shape, dtype=np.int16)
    layer = 0
    while True:
        if cancel is not None and cancel():
            break
        nsum = np.zeros(shape, dtype=np.uint8)
        nsum[1:, :, :] += remaining[:-1, :, :]
        nsum[:-1, :, :] += remaining[1:, :, :]
        nsum[:, 1:, :] += remaining[:, :-1, :]
        nsum[:, :-1, :] += remaining[:, 1:, :]
        nsum[:, :, 1:] += remaining[:, :, :-1]
        nsum[:, :, :-1] += remaining[:, :, 1:]
        shell = remaining.astype(bool) & (nsum < 6)
        if not np.any(shell):
            leftover = remaining.astype(bool)
            if np.any(leftover):
                layer_of[leftover] = layer
            break
        layer_of[shell] = layer
        remaining[shell] = 0
        layer += 1
        if layer > 1024:
            break
    out: Dict[Cell, int] = {}
    for i in range(pts.shape[0]):
        out[(int(pts[i, 0]), int(pts[i, 1]), int(pts[i, 2]))] = int(layer_of[loc[i, 0], loc[i, 1], loc[i, 2]])
    return out


def _flood_exterior(occupied: Set[Cell], volume_cap: int = FLOOD_VOLUME_CAP) -> Optional[Set[Cell]]:
    """
    Empty cells reachable from the padded AABB boundary.

    Returns None when the AABB is too sparse/large so callers treat every
    empty neighbor as outside instead of allocating nx*ny*nz cells.
    """
    if not occupied:
        return set()
    xs = [c[0] for c in occupied]
    ys = [c[1] for c in occupied]
    zs = [c[2] for c in occupied]
    amin = (min(xs) - 1, min(ys) - 1, min(zs) - 1)
    amax = (max(xs) + 1, max(ys) + 1, max(zs) + 1)
    volume = (amax[0] - amin[0] + 1) * (amax[1] - amin[1] + 1) * (amax[2] - amin[2] + 1)
    if volume > volume_cap:
        return None

    def inbound(cell: Cell) -> bool:
        return (
            amin[0] <= cell[0] <= amax[0]
            and amin[1] <= cell[1] <= amax[1]
            and amin[2] <= cell[2] <= amax[2]
        )

    exterior: Set[Cell] = set()
    queue: List[Cell] = []

    def seed(cell: Cell) -> None:
        if cell in occupied or cell in exterior:
            return
        exterior.add(cell)
        queue.append(cell)

    for x in range(amin[0], amax[0] + 1):
        for y in range(amin[1], amax[1] + 1):
            seed((x, y, amin[2]))
            seed((x, y, amax[2]))
    for x in range(amin[0], amax[0] + 1):
        for z in range(amin[2], amax[2] + 1):
            seed((x, amin[1], z))
            seed((x, amax[1], z))
    for y in range(amin[1], amax[1] + 1):
        for z in range(amin[2], amax[2] + 1):
            seed((amin[0], y, z))
            seed((amax[0], y, z))

    while queue:
        x, y, z = queue.pop()
        for dx, dy, dz in _SIX_DIRS:
            nxt = (x + dx, y + dy, z + dz)
            if not inbound(nxt) or nxt in occupied or nxt in exterior:
                continue
            exterior.add(nxt)
            queue.append(nxt)
    return exterior


def block_shell_layer(
    cells: Sequence[Cell],
    layers: Dict[Cell, int],
) -> int:
    if not cells:
        return 0
    return min(layers.get(cell, 0) for cell in cells)


def is_fully_enclosed(occupied: Set[Cell], cells: Sequence[Cell]) -> bool:
    for x, y, z in cells:
        for dx, dy, dz in _SIX_DIRS:
            if (x + dx, y + dy, z + dz) not in occupied:
                return False
    return bool(cells)


def face_fully_occluded(occupied: Set[Cell], cells: Sequence[Cell], grid_dir: Sequence[int]) -> bool:
    """True only when every surface cell in `grid_dir` has an occupied neighbor."""
    if not cells:
        return False
    own = set(cells)
    dx, dy, dz = int(grid_dir[0]), int(grid_dir[1]), int(grid_dir[2])
    saw_surface = False
    for x, y, z in cells:
        nx, ny, nz = x + dx, y + dy, z + dz
        if (nx, ny, nz) in own:
            continue
        saw_surface = True
        if (nx, ny, nz) not in occupied:
            return False
    return saw_surface


_LOCAL_GRID_CACHE: Dict[Tuple[str, str, int, int, int], Tuple[int, int, int]] = {}


def _local_to_grid_dir(forward: str, up: str, local: Sequence[int]) -> Tuple[int, int, int]:
    key = (forward or "Forward", up or "Up", int(local[0]), int(local[1]), int(local[2]))
    cached = _LOCAL_GRID_CACHE.get(key)
    if cached is not None:
        return cached
    right, up_v, backward = orientation_matrix(forward, up)
    lx, ly, lz = local
    result = (
        int(round(lx * right[0] + ly * up_v[0] + lz * backward[0])),
        int(round(lx * right[1] + ly * up_v[1] + lz * backward[1])),
        int(round(lx * right[2] + ly * up_v[2] + lz * backward[2])),
    )
    _LOCAL_GRID_CACHE[key] = result
    return result


def _is_identity_orient(forward: str, up: str) -> bool:
    if forward == "Forward" and up == "Up":
        return True
    return (forward or "Forward").strip().lower() == "forward" and (up or "Up").strip().lower() == "up"


def _pack_xyz(xyz: np.ndarray) -> np.ndarray:
    x = xyz[:, 0].astype(np.int64) + _PACK_OFFSET
    y = xyz[:, 1].astype(np.int64) + _PACK_OFFSET
    z = xyz[:, 2].astype(np.int64) + _PACK_OFFSET
    return (x << 42) | (y << 21) | z


class _NeighborIndex:
    """Per-grid neighbor queries. Dense volume when the AABB is compact."""

    def __init__(self, occupied: Set[Cell]) -> None:
        self.occupied = occupied
        self._vol: Optional[np.ndarray] = None
        self._amin: Optional[np.ndarray] = None
        self._packed: Optional[np.ndarray] = None
        if occupied and occupancy_padded_volume(occupied) <= DENSE_VOLUME_CAP:
            pts = np.array(list(occupied), dtype=np.int32)
            amin = pts.min(axis=0) - 1
            amax = pts.max(axis=0) + 1
            shape = (
                int(amax[0] - amin[0] + 1),
                int(amax[1] - amin[1] + 1),
                int(amax[2] - amin[2] + 1),
            )
            vol = np.zeros(shape, dtype=np.bool_)
            loc = pts - amin
            vol[loc[:, 0], loc[:, 1], loc[:, 2]] = True
            self._vol = vol
            self._amin = amin
        elif occupied:
            pts = np.array(list(occupied), dtype=np.int32)
            packed = np.unique(_pack_xyz(pts))
            self._packed = packed

    def query_unit(self, mins: np.ndarray, dirs: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """mins (M,3) → cull_mask (M,), six-neighbor enclosed (M,)."""
        use_dirs = _UNIT_DIRS if dirs is None else dirs
        n = int(mins.shape[0])
        hit = np.zeros((n, 6), dtype=np.bool_)
        if self._vol is not None and self._amin is not None:
            vol = self._vol
            origin = self._amin
            x = mins[:, 0] - int(origin[0])
            y = mins[:, 1] - int(origin[1])
            z = mins[:, 2] - int(origin[2])
            nx, ny, nz = vol.shape
            for axis, (dx, dy, dz) in enumerate(use_dirs):
                xi = x + int(dx)
                yi = y + int(dy)
                zi = z + int(dz)
                valid = (xi >= 0) & (xi < nx) & (yi >= 0) & (yi < ny) & (zi >= 0) & (zi < nz)
                if np.any(valid):
                    hit[valid, axis] = vol[xi[valid], yi[valid], zi[valid]]
        elif self._packed is not None:
            neigh = mins[:, None, :] + use_dirs[None, :, :]
            packed = _pack_xyz(neigh.reshape(-1, 3))
            keys = self._packed
            idx = np.searchsorted(keys, packed)
            idx = np.minimum(idx, len(keys) - 1)
            hit = (keys[idx] == packed).reshape(n, 6)
        else:
            return np.zeros(n, dtype=np.int32), np.zeros(n, dtype=np.bool_)
        mask = (hit * _FACE_BITS_XYZ).sum(axis=1).astype(np.int32)
        return mask, hit.all(axis=1)


def occupied_exterior_face_count(occupied: Set[Cell]) -> int:
    """6-neighbor faces of occupied cells that look into empty space."""
    n = 0
    for x, y, z in occupied:
        for dx, dy, dz in _SIX_DIRS:
            if (x + dx, y + dy, z + dz) not in occupied:
                n += 1
    return n


def plan_visible_face_count(plans: Sequence[BlockOccupancy]) -> int:
    """Axis-aligned faces that occupancy left in place (not fully enclosed)."""
    n = 0
    for plan in plans:
        if plan.fully_enclosed:
            continue
        if not plan.topology_cullable:
            n += 6
            continue
        for bit in _FACE_BITS:
            if not (plan.cull_mask & bit):
                n += 1
    return n


def should_relax_culling(block_count: int, shown: int) -> bool:
    n = int(block_count)
    if n <= MIN_VISIBLE_INSTANCE_BLOCKS:
        return False
    return int(shown) < MIN_VISIBLE_INSTANCE_RATIO * n


def relax_culling(
    plans: Sequence[BlockOccupancy],
    level: int,
) -> List[BlockOccupancy]:
    """
    level 1: keep every block (no fully-enclosed skip), retain face masks.
    level 2: no face masks either — last resort so a hull cannot vanish.
    """
    out: List[BlockOccupancy] = []
    for plan in plans:
        if level >= 2:
            out.append(
                BlockOccupancy(
                    cells=plan.cells,
                    cull_mask=0,
                    fully_enclosed=False,
                    topology_cullable=plan.topology_cullable,
                )
            )
        elif level >= 1:
            mask = 0 if plan.fully_enclosed else plan.cull_mask
            out.append(
                BlockOccupancy(
                    cells=plan.cells,
                    cull_mask=mask,
                    fully_enclosed=False,
                    topology_cullable=plan.topology_cullable,
                )
            )
        else:
            out.append(plan)
    return out


def instance_cull_mask(
    occupied: Set[Cell],
    cells: Sequence[Cell],
    forward: str = "Forward",
    up: str = "Up",
) -> int:
    """Bits matching MeshData.face_axes for faces fully hidden by neighbors."""
    mask = 0
    for bit, local in _FACE_LOCAL_DIR.items():
        grid_dir = _local_to_grid_dir(forward, up, local)
        if face_fully_occluded(occupied, cells, grid_dir):
            mask |= bit
    return mask


def plan_block(
    block: BlockInstance,
    occupied: OccupancyMap,
    catalog: Optional[CubeBlockCatalog] = None,
) -> BlockOccupancy:
    definition = catalog.get(block.type_id, block.subtype) if catalog else None
    cells = occupied_cells(block.local_min, definition_size(definition), block.forward, block.up)
    grid_cells = occupied.get(block.grid_entity_id, set())
    topology = is_topology_cube(definition)
    solid = is_solid_box(definition)
    # Only solid boxes can vanish when surrounded. A slope with six
    # occupied neighbors can still show its hypotenuse into a gap.
    enclosed = solid and is_fully_enclosed(grid_cells, cells)
    mask = instance_cull_mask(grid_cells, cells, block.forward, block.up) if topology else 0
    if enclosed:
        mask = FACE_ALL
    return BlockOccupancy(
        cells=cells,
        cull_mask=mask,
        fully_enclosed=enclosed,
        topology_cullable=topology,
    )


def plan_blocks(
    blocks: Iterable[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
    cancel=None,
) -> List[BlockOccupancy]:
    block_list = list(blocks)
    occ = occupied if occupied is not None else build_occupancy(block_list, catalog, cancel=cancel)
    n = len(block_list)
    if n == 0:
        return []
    if cancel is not None and cancel():
        return []
    defn_cache: Dict[Tuple[str, str], Optional[BlockDefinition]] = {}

    def definition_of(block: BlockInstance) -> Optional[BlockDefinition]:
        if catalog is None:
            return None
        key = (block.type_id, block.subtype)
        hit = defn_cache.get(key, _MISSING)
        if hit is _MISSING:
            hit = catalog.get(block.type_id, block.subtype)
            defn_cache[key] = hit
        return hit

    indexes = {gid: _NeighborIndex(cells) for gid, cells in occ.items()}
    plans: List[Optional[BlockOccupancy]] = [None] * n
    by_grid: Dict[str, List[int]] = {}
    rest: List[int] = []
    for i, block in enumerate(block_list):
        if cancel is not None and (i & 255) == 0 and cancel():
            return []
        definition = definition_of(block)
        size = definition_size(definition)
        if size == (1, 1, 1) and is_topology_cube(definition):
            by_grid.setdefault(block.grid_entity_id, []).append(i)
        else:
            rest.append(i)

    for gid, indices in by_grid.items():
        if cancel is not None and cancel():
            return []
        index = indexes.get(gid) or _NeighborIndex(set())
        identity: List[int] = []
        oriented: List[int] = []
        for i in indices:
            if _is_identity_orient(block_list[i].forward, block_list[i].up):
                identity.append(i)
            else:
                oriented.append(i)
        if identity:
            mins = np.array([block_list[i].local_min for i in identity], dtype=np.int32)
            mask, enclosed = index.query_unit(mins)
            for k, i in enumerate(identity):
                definition = definition_of(block_list[i])
                solid = is_solid_box(definition)
                enc = bool(enclosed[k]) and solid
                plans[i] = BlockOccupancy(
                    cells=(block_list[i].local_min,),
                    cull_mask=FACE_ALL if enc else int(mask[k]),
                    fully_enclosed=enc,
                    topology_cullable=True,
                )
        for i in oriented:
            block = block_list[i]
            dirs = np.array(
                [_local_to_grid_dir(block.forward, block.up, _FACE_LOCAL_DIR[bit]) for bit in _FACE_BITS],
                dtype=np.int32,
            )
            mins = np.array([block.local_min], dtype=np.int32)
            mask, enclosed = index.query_unit(mins, dirs)
            definition = definition_of(block)
            solid = is_solid_box(definition)
            enc = bool(enclosed[0]) and solid
            plans[i] = BlockOccupancy(
                cells=(block.local_min,),
                cull_mask=FACE_ALL if enc else int(mask[0]),
                fully_enclosed=enc,
                topology_cullable=True,
            )

    for n_rest, i in enumerate(rest):
        if cancel is not None and (n_rest & 255) == 0 and cancel():
            return []
        plans[i] = plan_block(block_list[i], occ, catalog)

    return [p if p is not None else plan_block(block_list[i], occ, catalog) for i, p in enumerate(plans)]
