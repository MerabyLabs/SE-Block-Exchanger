"""
Per-grid dissect offsets for the Subgrids 3D preview.

Peel (default): armor walks toward the nearest hull exit using local
occupancy, so a long ship's bow and stern open instead of cracking only
at the centroid. Functional blocks keep a low explode weight and share a
cluster offset so rooms stay readable.

Decks: layers along grid up (or the shortest AABB axis).
Radial: global outward from the grid centroid plus local opening
(hull-exit peel, principal-axis stations, and neighborhood separation)
so bow/stern clumps break apart instead of translating as rigid ends.

Offsets are world-space vectors at dissect = 100%. The shader scales them
by u_explode — changing the slider or mode must not rebuild meshes.
Functional blocks keep FUNCTIONAL_EXPLODE_WEIGHT so interiors stay readable.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from se_assets.cube_catalog import CubeBlockCatalog
from se_render.occupancy import OccupancyMap, build_occupancy, definition_size, occupied_cells
from se_render.orientation import (
    cell_size_meters,
    invert_rigid_mat4,
    mat3_to_mat4,
    mul_mat4,
    orientation_matrix,
    transform_dir,
)
from se_render.preview_style import is_armor_block
from se_render.scene_graph import BlockInstance


DISSECT_PEEL = "peel"
DISSECT_DECKS = "decks"
DISSECT_RADIAL = "radial"
DISSECT_MODES = (DISSECT_PEEL, DISSECT_DECKS, DISSECT_RADIAL)
DISSECT_MODE_INDEX = {DISSECT_PEEL: 0, DISSECT_DECKS: 1, DISSECT_RADIAL: 2}

# Armor opens the shell; interiors stay near true pose (0.1–0.25).
ARMOR_EXPLODE_WEIGHT = 1.0
FUNCTIONAL_EXPLODE_WEIGHT = 0.18

# At 100% peel, surface armor travels about this many cells — not a
# fraction of the ship's length, which would reintroduce mid-splits.
PEEL_CELL_TRAVEL = 4.0
DECK_CELL_GAP = 2.15
EXPLODE_RADIUS_FRACTION = 0.65
EXPLODE_CELL_PADDING = 3.0

# Radial mix: modest global expand (not ship-length scale) + local openers.
RADIAL_GLOBAL_CELLS = 1.85
RADIAL_GLOBAL_STRETCH = 0.28
RADIAL_PEEL_CELLS = 2.15
RADIAL_STATION_STRETCH = 1.05
RADIAL_NEIGHBOR_STRETCH = 1.45
RADIAL_NEIGHBOR_RADIUS = 2

_SIX = (
    (-1, 0, 0),
    (1, 0, 0),
    (0, -1, 0),
    (0, 1, 0),
    (0, 0, -1),
    (0, 0, 1),
)

Cell = Tuple[int, int, int]
Vec3 = Tuple[float, float, float]


def block_world_center(block: BlockInstance) -> Vec3:
    m = block.world_matrix
    return (float(m[0][3]), float(m[1][3]), float(m[2][3]))


def grid_centroids(blocks: Sequence[BlockInstance]) -> Dict[str, Vec3]:
    buckets: Dict[str, List[Vec3]] = {}
    for block in blocks:
        buckets.setdefault(block.grid_entity_id, []).append(block_world_center(block))
    out: Dict[str, Vec3] = {}
    for gid, points in buckets.items():
        n = float(len(points))
        out[gid] = (
            sum(p[0] for p in points) / n,
            sum(p[1] for p in points) / n,
            sum(p[2] for p in points) / n,
        )
    return out


def explode_scale_for_points(
    points: Sequence[Vec3],
    centroid: Vec3,
    cell: float,
) -> float:
    if not points:
        return max(2.5, cell * EXPLODE_CELL_PADDING)
    farthest = 0.0
    for x, y, z in points:
        dx, dy, dz = x - centroid[0], y - centroid[1], z - centroid[2]
        farthest = max(farthest, (dx * dx + dy * dy + dz * dz) ** 0.5)
    return farthest * EXPLODE_RADIUS_FRACTION + cell * EXPLODE_CELL_PADDING


def explode_offset(
    position: Sequence[float],
    centroid: Sequence[float],
    amount: float,
    scale: float,
    salt: int = 0,
) -> Vec3:
    """Outward vector from a grid centroid. `amount` is 0–1 (slider percent / 100)."""
    dx = float(position[0]) - float(centroid[0])
    dy = float(position[1]) - float(centroid[1])
    dz = float(position[2]) - float(centroid[2])
    length = (dx * dx + dy * dy + dz * dz) ** 0.5
    if length < 1e-6:
        dx = 0.35 if (salt * 1103515245 + 12345) & 1 else -0.35
        dy = 0.55
        dz = 0.15 if (salt * 214013 + 2531011) & 2 else -0.15
        length = (dx * dx + dy * dy + dz * dz) ** 0.5
    factor = (float(amount) * float(scale)) / length
    return (dx * factor, dy * factor, dz * factor)


def explode_max_offsets(blocks: Sequence[BlockInstance]) -> List[Vec3]:
    """Legacy centroid explode. Radial mode uses radial_max_offsets instead."""
    if not blocks:
        return []
    centroids = grid_centroids(blocks)
    points_by_grid: Dict[str, List[Vec3]] = {}
    cells: Dict[str, float] = {}
    for block in blocks:
        points_by_grid.setdefault(block.grid_entity_id, []).append(block_world_center(block))
        cells.setdefault(block.grid_entity_id, cell_size_meters(block.grid_size))
    scales = {
        gid: explode_scale_for_points(pts, centroids[gid], cells[gid])
        for gid, pts in points_by_grid.items()
    }
    offsets: List[Vec3] = []
    for block in blocks:
        pos = block_world_center(block)
        gid = block.grid_entity_id
        salt = abs(hash(block.entity_id or block.subtype or gid)) & 0xFFFF
        offsets.append(explode_offset(pos, centroids[gid], 1.0, scales[gid], salt=salt))
    return offsets


def dissect_max_offsets(
    blocks: Sequence[BlockInstance],
    mode: str = DISSECT_PEEL,
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
) -> List[Vec3]:
    key = (mode or DISSECT_PEEL).strip().lower()
    if key == DISSECT_DECKS:
        return deck_max_offsets(blocks, catalog, occupied=occupied)
    if key == DISSECT_RADIAL:
        return radial_max_offsets(blocks, catalog, occupied=occupied)
    return peel_max_offsets(blocks, catalog, occupied=occupied)


def dissect_offset_sets(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
) -> Tuple[List[Vec3], List[Vec3], List[Vec3]]:
    """Peel, decks, and radial at 100%. Occupancy is built once."""
    occupied = occupied if occupied is not None else (build_occupancy(blocks, catalog) if blocks else {})
    return (
        peel_max_offsets(blocks, catalog, occupied=occupied),
        deck_max_offsets(blocks, catalog, occupied=occupied),
        radial_max_offsets(blocks, catalog, occupied=occupied),
    )


def radial_max_offsets(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
) -> List[Vec3]:
    """
    Outward radial that still opens bow/stern clumps.

    Global: modest explode from the grid centroid (silhouette expands).
    Local: hull-exit peel + 1–5 stations on the long axis + neighborhood
    separation so adjacent end cells do not share one rigid offset.
    Per-grid. Functional weight 0.18; connected functional clusters share.
    """
    if not blocks:
        return []
    occ = occupied if occupied is not None else build_occupancy(blocks, catalog)
    peel_ctx = _grid_peel_context(blocks, occ)
    centroids = grid_centroids(blocks)
    by_grid: Dict[str, List[int]] = {}
    for i, block in enumerate(blocks):
        by_grid.setdefault(block.grid_entity_id, []).append(i)

    stations: Dict[str, List[Vec3]] = {}
    station_of: List[int] = [0] * len(blocks)
    cells_of: List[Tuple[Cell, ...]] = []
    positions: List[Vec3] = []
    for block in blocks:
        definition = catalog.get(block.type_id, block.subtype) if catalog else None
        cells_of.append(occupied_cells(
            block.local_min, definition_size(definition), block.forward, block.up
        ))
        positions.append(block_world_center(block))

    for gid, indices in by_grid.items():
        grid_cells = occ.get(gid) or {cell for i in indices for cell in cells_of[i]}
        axis, lo, hi, n_st = _radial_stations_for_cells(grid_cells)
        buckets: Dict[int, List[int]] = {s: [] for s in range(n_st)}
        for i in indices:
            coord = min(c[axis] for c in cells_of[i]) if cells_of[i] else int(blocks[i].local_min[axis])
            sid = _station_index(coord, lo, hi, n_st)
            station_of[i] = sid
            buckets[sid].append(i)
        origins: List[Vec3] = []
        for sid in range(n_st):
            members = buckets[sid]
            if members:
                n = float(len(members))
                origins.append((
                    sum(positions[i][0] for i in members) / n,
                    sum(positions[i][1] for i in members) / n,
                    sum(positions[i][2] for i in members) / n,
                ))
            else:
                origins.append(centroids[gid])
        stations[gid] = origins

    neighborhoods = _neighborhood_centroids(blocks, positions, cells_of, RADIAL_NEIGHBOR_RADIUS)

    armor_flags: List[bool] = []
    globals_off: List[Vec3] = []
    stretches: List[Vec3] = []
    peels: List[Vec3] = []
    stations_off: List[Vec3] = []
    neighs: List[Vec3] = []
    weights: List[float] = []
    for i, block in enumerate(blocks):
        gid = block.grid_entity_id
        ctx = peel_ctx[gid]
        pos = positions[i]
        center = centroids[gid]
        armor = is_armor_block(block.type_id, block.subtype)
        armor_flags.append(armor)
        weight = ARMOR_EXPLODE_WEIGHT if armor else FUNCTIONAL_EXPLODE_WEIGHT
        salt = abs(hash(block.entity_id or block.subtype or gid)) & 0xFFFF

        global_off = explode_offset(pos, center, 1.0, ctx.cell * RADIAL_GLOBAL_CELLS, salt=salt)
        stretch = (
            (pos[0] - center[0]) * RADIAL_GLOBAL_STRETCH,
            (pos[1] - center[1]) * RADIAL_GLOBAL_STRETCH,
            (pos[2] - center[2]) * RADIAL_GLOBAL_STRETCH,
        )
        direction = _peel_direction_grid(cells_of[i], ctx.occupied, ctx.exterior, ctx.com)
        world = _normalize(transform_dir(ctx.grid_world, direction))
        peel_travel = ctx.cell * RADIAL_PEEL_CELLS
        peel_off = (world[0] * peel_travel, world[1] * peel_travel, world[2] * peel_travel)

        station = stations[gid][station_of[i]]
        station_off = (
            (pos[0] - station[0]) * RADIAL_STATION_STRETCH,
            (pos[1] - station[1]) * RADIAL_STATION_STRETCH,
            (pos[2] - station[2]) * RADIAL_STATION_STRETCH,
        )
        neigh = neighborhoods[i]
        neigh_off = (
            (pos[0] - neigh[0]) * RADIAL_NEIGHBOR_STRETCH,
            (pos[1] - neigh[1]) * RADIAL_NEIGHBOR_STRETCH,
            (pos[2] - neigh[2]) * RADIAL_NEIGHBOR_STRETCH,
        )
        globals_off.append(global_off)
        stretches.append(stretch)
        peels.append(peel_off)
        stations_off.append(station_off)
        neighs.append(neigh_off)
        weights.append(weight)
    combined = radial_combine_offsets(
        globals_off, stretches, peels, stations_off, neighs, weights
    )
    raw = [(float(row[0]), float(row[1]), float(row[2])) for row in combined]
    return _share_functional_clusters(blocks, catalog, armor_flags, raw)


def radial_combine_offsets(
    global_off: Sequence,
    stretch: Sequence,
    peel_off: Sequence,
    station_off: Sequence,
    neigh_off: Sequence,
    weight: Sequence,
) -> np.ndarray:
    """Vectorized Radial sum. Must match the Python add within 1e-6."""
    g = np.asarray(global_off, dtype=np.float64).reshape(-1, 3)
    s = np.asarray(stretch, dtype=np.float64).reshape(-1, 3)
    p = np.asarray(peel_off, dtype=np.float64).reshape(-1, 3)
    st = np.asarray(station_off, dtype=np.float64).reshape(-1, 3)
    n = np.asarray(neigh_off, dtype=np.float64).reshape(-1, 3)
    w = np.asarray(weight, dtype=np.float64).reshape(-1, 1)
    return (g + s + p + st + n) * w


def peel_max_offsets(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
) -> List[Vec3]:
    """
    Local hull-exit peel. End cells of a 1×1×N stick move along the long
    axis; a bow cluster peels locally instead of translating as one clump.
    """
    if not blocks:
        return []
    occ = occupied if occupied is not None else build_occupancy(blocks, catalog)
    grids = _grid_peel_context(blocks, occ)
    raw: List[Vec3] = []
    armor_flags: List[bool] = []
    for block in blocks:
        ctx = grids[block.grid_entity_id]
        cells = occupied_cells(block.local_min, definition_size(
            catalog.get(block.type_id, block.subtype) if catalog else None
        ), block.forward, block.up)
        armor = is_armor_block(block.type_id, block.subtype)
        armor_flags.append(armor)
        direction = _peel_direction_grid(cells, ctx.occupied, ctx.exterior, ctx.com)
        world = transform_dir(ctx.grid_world, direction)
        world = _normalize(world)
        weight = ARMOR_EXPLODE_WEIGHT if armor else FUNCTIONAL_EXPLODE_WEIGHT
        travel = ctx.cell * PEEL_CELL_TRAVEL * weight
        raw.append((world[0] * travel, world[1] * travel, world[2] * travel))
    return _share_functional_clusters(blocks, catalog, armor_flags, raw)


def deck_max_offsets(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog] = None,
    occupied: Optional[OccupancyMap] = None,
) -> List[Vec3]:
    """Separate planar decks. Same layer → same offset; one dominant axis."""
    if not blocks:
        return []
    occ = occupied if occupied is not None else build_occupancy(blocks, catalog)
    by_grid: Dict[str, List[int]] = {}
    for i, block in enumerate(blocks):
        by_grid.setdefault(block.grid_entity_id, []).append(i)
    offsets: List[Vec3] = [(0.0, 0.0, 0.0)] * len(blocks)
    for gid, indices in by_grid.items():
        axis, lo, hi, world_axis, cell = _deck_axis_for_grid(blocks, indices, catalog, occ)
        mid = (lo + hi) * 0.5
        wx, wy, wz = _normalize(world_axis)
        gap = cell * DECK_CELL_GAP
        for i in indices:
            layer = float(_block_axis_coord(blocks[i], catalog, axis))
            delta = (layer - mid) * gap
            offsets[i] = (wx * delta, wy * delta, wz * delta)
    return offsets


def pick_identity(record) -> Tuple[str, Tuple[int, int, int], str]:
    """
    Stable editor key: grid entity id + Min + block entity id.

    GPU instance_id is the PreviewScene.blocks index and can change when
    the scene is rebuilt. This key is what a later in-preview editor
    should use to find the same cube. Does not write blueprint XML.
    """
    gid = str(getattr(record, "grid_entity_id", "") or "")
    local = getattr(record, "local_min", None)
    if local is None:
        local = (
            int(getattr(record, "min_x", 0)),
            int(getattr(record, "min_y", 0)),
            int(getattr(record, "min_z", 0)),
        )
    mn = (int(local[0]), int(local[1]), int(local[2]))
    eid = str(getattr(record, "entity_id", "") or "")
    return (gid, mn, eid)


def selection_caption(record) -> str:
    """Status/footer line: typeId/subtype and grid Min."""
    type_id = str(getattr(record, "type_id", "") or "CubeBlock")
    subtype = str(getattr(record, "subtype", "") or "")
    local = getattr(record, "local_min", (0, 0, 0))
    return f"{type_id}/{subtype}  ({int(local[0])}, {int(local[1])}, {int(local[2])})"


def selection_meta(record) -> dict:
    """Structured pick payload for a future edit tool. Read-only."""
    ident = pick_identity(record)
    local = getattr(record, "local_min", ident[1])
    return {
        "pick_id": ident,
        "instance_id": int(getattr(record, "instance_id", -1)),
        "grid_name": str(getattr(record, "grid_name", "") or ""),
        "grid_entity_id": ident[0],
        "entity_id": ident[2],
        "type_id": str(getattr(record, "type_id", "") or ""),
        "subtype": str(getattr(record, "subtype", "") or ""),
        "local_min": (int(local[0]), int(local[1]), int(local[2])),
        "is_armor": bool(getattr(record, "is_armor", False)),
    }


def explode_offset_for_mode(record, mode: str = DISSECT_PEEL) -> Vec3:
    key = (mode or DISSECT_PEEL).strip().lower()
    if key == DISSECT_DECKS:
        return tuple(getattr(record, "explode_decks", getattr(record, "explode_offset", (0.0, 0.0, 0.0))))
    if key == DISSECT_RADIAL:
        return tuple(getattr(record, "explode_radial", getattr(record, "explode_offset", (0.0, 0.0, 0.0))))
    return tuple(getattr(record, "explode_peel", getattr(record, "explode_offset", (0.0, 0.0, 0.0))))


def _radial_station_count(span: int) -> int:
    if span < 4:
        return 1
    if span < 10:
        return 3
    return 5


def _radial_stations_for_cells(cells: Iterable[Cell]) -> Tuple[int, int, int, int]:
    pts = list(cells)
    if not pts:
        return 0, 0, 0, 1
    mins = [min(c[i] for c in pts) for i in range(3)]
    maxs = [max(c[i] for c in pts) for i in range(3)]
    extents = [maxs[i] - mins[i] for i in range(3)]
    axis = max(range(3), key=lambda i: (extents[i], -i))
    lo, hi = mins[axis], maxs[axis]
    return axis, lo, hi, _radial_station_count(hi - lo)


def _station_index(coord: int, lo: int, hi: int, count: int) -> int:
    if count <= 1 or hi <= lo:
        return 0
    t = (float(coord) - float(lo)) / float(hi - lo)
    return min(count - 1, max(0, int(t * count)))


def _neighborhood_centroids(
    blocks: Sequence[BlockInstance],
    positions: Sequence[Vec3],
    cells_of: Sequence[Sequence[Cell]],
    radius: int,
) -> List[Vec3]:
    """Per-grid Chebyshev neighborhood COM. Ends of a stick shift off-axis from their inward neighbor."""
    owners: Dict[str, Dict[Cell, List[int]]] = {}
    for i, block in enumerate(blocks):
        bucket = owners.setdefault(block.grid_entity_id, {})
        for cell in cells_of[i]:
            bucket.setdefault(cell, []).append(i)
    out: List[Vec3] = [positions[i] for i in range(len(blocks))]
    for i, block in enumerate(blocks):
        cells = cells_of[i]
        if not cells:
            continue
        grid_owners = owners[block.grid_entity_id]
        seen: Set[int] = set()
        acc = [0.0, 0.0, 0.0]
        for x, y, z in cells:
            for ox in range(-radius, radius + 1):
                for oy in range(-radius, radius + 1):
                    for oz in range(-radius, radius + 1):
                        for j in grid_owners.get((x + ox, y + oy, z + oz), ()):
                            if j in seen:
                                continue
                            seen.add(j)
                            acc[0] += positions[j][0]
                            acc[1] += positions[j][1]
                            acc[2] += positions[j][2]
        if seen:
            n = float(len(seen))
            out[i] = (acc[0] / n, acc[1] / n, acc[2] / n)
    return out


def _normalize(v: Sequence[float]) -> Vec3:
    length = (float(v[0]) ** 2 + float(v[1]) ** 2 + float(v[2]) ** 2) ** 0.5
    if length < 1e-8:
        return (0.0, 0.0, 0.0)
    return (float(v[0]) / length, float(v[1]) / length, float(v[2]) / length)


class _GridPeel:
    __slots__ = ("occupied", "exterior", "com", "grid_world", "cell")

    def __init__(self, occupied, exterior, com, grid_world, cell):
        self.occupied = occupied
        self.exterior = exterior
        self.com = com
        self.grid_world = grid_world
        self.cell = cell


def _grid_peel_context(
    blocks: Sequence[BlockInstance],
    occupied: OccupancyMap,
) -> Dict[str, _GridPeel]:
    first: Dict[str, BlockInstance] = {}
    for block in blocks:
        first.setdefault(block.grid_entity_id, block)
    out: Dict[str, _GridPeel] = {}
    for gid, block in first.items():
        cells = occupied.get(gid, set())
        com = _cell_com(cells)
        out[gid] = _GridPeel(
            occupied=cells,
            exterior=_mark_exterior(cells),
            com=com,
            grid_world=_grid_world_matrix(block),
            cell=cell_size_meters(block.grid_size),
        )
    return out


def _cell_com(cells: Iterable[Cell]) -> Vec3:
    pts = list(cells)
    if not pts:
        return (0.0, 0.0, 0.0)
    n = float(len(pts))
    return (
        sum(c[0] for c in pts) / n,
        sum(c[1] for c in pts) / n,
        sum(c[2] for c in pts) / n,
    )


def _grid_world_matrix(block: BlockInstance) -> list:
    """Recover the grid pose so peel/deck axes stay in grid space, not block-local."""
    cell = cell_size_meters(block.grid_size)
    mx, my, mz = block.local_min
    center = ((mx + 0.5) * cell, (my + 0.5) * cell, (mz + 0.5) * cell)
    local = mat3_to_mat4(orientation_matrix(block.forward, block.up), center)
    return mul_mat4(block.world_matrix, invert_rigid_mat4(local))


def _mark_exterior(occupied: Set[Cell], volume_cap: int = 80_000) -> Optional[Set[Cell]]:
    """Empty cells reachable from the occupancy AABB boundary. None = treat all empty as outside."""
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
    queue: deque = deque()

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
        x, y, z = queue.popleft()
        for dx, dy, dz in _SIX:
            nxt = (x + dx, y + dy, z + dz)
            if not inbound(nxt) or nxt in occupied or nxt in exterior:
                continue
            exterior.add(nxt)
            queue.append(nxt)
    return exterior


def _occupancy_gradient(cell: Cell, occupied: Set[Cell]) -> Vec3:
    gx = gy = gz = 0.0
    x, y, z = cell
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for oz in (-1, 0, 1):
                if ox == oy == oz == 0:
                    continue
                if (x + ox, y + oy, z + oz) in occupied:
                    gx += ox
                    gy += oy
                    gz += oz
    return (gx, gy, gz)


def _is_fully_surrounded(cell: Cell, occupied: Set[Cell]) -> bool:
    x, y, z = cell
    for dx, dy, dz in _SIX:
        if (x + dx, y + dy, z + dz) not in occupied:
            return False
    return True


def _ray_to_exterior(
    cell: Cell,
    direction: Cell,
    occupied: Set[Cell],
    exterior: Optional[Set[Cell]],
    limit: int = 48,
) -> Optional[int]:
    x, y, z = cell
    dx, dy, dz = direction
    for steps in range(1, limit + 1):
        x += dx
        y += dy
        z += dz
        nxt = (x, y, z)
        if nxt in occupied:
            continue
        if exterior is None or nxt in exterior:
            return steps
        return None
    return None


def _peel_direction_cell(
    cell: Cell,
    occupied: Set[Cell],
    exterior: Optional[Set[Cell]],
    com: Vec3,
) -> Vec3:
    gradient = _occupancy_gradient(cell, occupied)
    glen = (gradient[0] ** 2 + gradient[1] ** 2 + gradient[2] ** 2) ** 0.5
    if glen >= 0.75:
        return _normalize((-gradient[0], -gradient[1], -gradient[2]))
    if _is_fully_surrounded(cell, occupied):
        return (0.0, 0.0, 0.0)

    exits: List[Tuple[int, Cell]] = []
    min_dist = 99
    for step in _SIX:
        dist = _ray_to_exterior(cell, step, occupied, exterior)
        if dist is None:
            continue
        exits.append((dist, step))
        min_dist = min(min_dist, dist)
    acc = [0.0, 0.0, 0.0]
    for dist, step in exits:
        if dist > min_dist:
            continue
        acc[0] += step[0]
        acc[1] += step[1]
        acc[2] += step[2]
    if (acc[0] ** 2 + acc[1] ** 2 + acc[2] ** 2) ** 0.5 > 0.2:
        return _normalize(acc)

    away = (cell[0] - com[0], cell[1] - com[1], cell[2] - com[2])
    return _normalize(away)


def _peel_direction_grid(
    cells: Sequence[Cell],
    occupied: Set[Cell],
    exterior: Optional[Set[Cell]],
    com: Vec3,
) -> Vec3:
    if not cells:
        return (0.0, 0.0, 0.0)
    acc = [0.0, 0.0, 0.0]
    used = 0
    for cell in cells:
        direction = _peel_direction_cell(cell, occupied, exterior, com)
        if direction[0] == direction[1] == direction[2] == 0.0:
            continue
        acc[0] += direction[0]
        acc[1] += direction[1]
        acc[2] += direction[2]
        used += 1
    if used == 0:
        return (0.0, 0.0, 0.0)
    return _normalize(acc)


def _share_functional_clusters(
    blocks: Sequence[BlockInstance],
    catalog: Optional[CubeBlockCatalog],
    armor_flags: Sequence[bool],
    offsets: Sequence[Vec3],
) -> List[Vec3]:
    """Connected functional blocks share one offset so a conveyor run stays a run."""
    result = list(offsets)
    owners: Dict[Cell, List[int]] = {}
    cells_of: List[Tuple[Cell, ...]] = []
    for i, block in enumerate(blocks):
        definition = catalog.get(block.type_id, block.subtype) if catalog else None
        cells = occupied_cells(block.local_min, definition_size(definition), block.forward, block.up)
        cells_of.append(cells)
        if armor_flags[i]:
            continue
        for cell in cells:
            owners.setdefault(cell, []).append(i)

    parent = list(range(len(blocks)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, block in enumerate(blocks):
        if armor_flags[i]:
            continue
        for cell in cells_of[i]:
            x, y, z = cell
            for dx, dy, dz in _SIX:
                for other in owners.get((x + dx, y + dy, z + dz), ()):
                    if other != i:
                        union(i, other)

    clusters: Dict[int, List[int]] = {}
    for i, block in enumerate(blocks):
        if armor_flags[i]:
            continue
        clusters.setdefault(find(i), []).append(i)
    for members in clusters.values():
        if len(members) < 2:
            continue
        n = float(len(members))
        avg = (
            sum(result[i][0] for i in members) / n,
            sum(result[i][1] for i in members) / n,
            sum(result[i][2] for i in members) / n,
        )
        for i in members:
            result[i] = avg
    return result


def _block_axis_coord(block: BlockInstance, catalog: Optional[CubeBlockCatalog], axis: int) -> int:
    definition = catalog.get(block.type_id, block.subtype) if catalog else None
    cells = occupied_cells(block.local_min, definition_size(definition), block.forward, block.up)
    if not cells:
        return int(block.local_min[axis])
    return min(cell[axis] for cell in cells)


def _deck_axis_for_grid(
    blocks: Sequence[BlockInstance],
    indices: Sequence[int],
    catalog: Optional[CubeBlockCatalog],
    occupied: OccupancyMap,
) -> Tuple[int, float, float, Vec3, float]:
    gid = blocks[indices[0]].grid_entity_id
    cells = occupied.get(gid) or {
        cell
        for i in indices
        for cell in occupied_cells(
            blocks[i].local_min,
            definition_size(catalog.get(blocks[i].type_id, blocks[i].subtype) if catalog else None),
            blocks[i].forward,
            blocks[i].up,
        )
    }
    if not cells:
        sample = blocks[indices[0]]
        return 1, 0.0, 0.0, transform_dir(_grid_world_matrix(sample), (0.0, 1.0, 0.0)), cell_size_meters(
            sample.grid_size
        )
    mins = [min(c[i] for c in cells) for i in range(3)]
    maxs = [max(c[i] for c in cells) for i in range(3)]
    extents = [maxs[i] - mins[i] for i in range(3)]
    # Prefer grid up so decks stay floors. Fall back to the shortest span
    # so a pancake still separates and a 1-layer ship does not invent Y.
    if extents[1] >= 1:
        axis = 1
    else:
        axis = min(range(3), key=lambda i: (extents[i], i))
    unit = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))[axis]
    sample = blocks[indices[0]]
    world = transform_dir(_grid_world_matrix(sample), unit)
    return axis, float(mins[axis]), float(maxs[axis]), world, cell_size_meters(sample.grid_size)


__all__ = [
    "ARMOR_EXPLODE_WEIGHT",
    "DECK_CELL_GAP",
    "DISSECT_DECKS",
    "DISSECT_MODE_INDEX",
    "DISSECT_MODES",
    "DISSECT_PEEL",
    "DISSECT_RADIAL",
    "FUNCTIONAL_EXPLODE_WEIGHT",
    "block_world_center",
    "deck_max_offsets",
    "dissect_max_offsets",
    "dissect_offset_sets",
    "explode_max_offsets",
    "explode_offset",
    "explode_offset_for_mode",
    "explode_scale_for_points",
    "grid_centroids",
    "peel_max_offsets",
    "pick_identity",
    "radial_combine_offsets",
    "radial_max_offsets",
    "selection_caption",
    "selection_meta",
]
