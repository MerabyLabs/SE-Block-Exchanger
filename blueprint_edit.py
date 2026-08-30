"""
In-memory preview edits and Save As for Space Engineers blueprints.

Mutates a copied bp.sbc (CubeBlocks delete / Min move). Never silently
overwrites the source folder under Blueprints/local.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ET

import safe_xml
from se_render.orientation import (
    cell_size_meters,
    invert_rigid_mat4,
    mat3_to_mat4,
    mul_mat4,
    orientation_matrix,
)
from se_render.scene_graph import BlockInstance, _blocks_in_grid, _iter_cube_grids, _text


Identity = Tuple[str, Tuple[int, int, int], str]


@dataclass
class GridEditSession:
    """Deletes, hides (inspect only), and 1-cell moves. Undo is one level."""

    source_path: Optional[Path] = None
    deleted: Set[Identity] = field(default_factory=set)
    hidden: Set[Identity] = field(default_factory=set)
    moves: Dict[Identity, Tuple[int, int, int]] = field(default_factory=dict)
    _undo: Optional[dict] = None

    def snapshot(self) -> dict:
        return {
            "deleted": set(self.deleted),
            "hidden": set(self.hidden),
            "moves": dict(self.moves),
        }

    def restore(self, snap: dict) -> None:
        self.deleted = set(snap.get("deleted") or ())
        self.hidden = set(snap.get("hidden") or ())
        self.moves = dict(snap.get("moves") or {})

    def _push_undo(self) -> None:
        self._undo = self.snapshot()

    def can_undo(self) -> bool:
        return self._undo is not None

    def undo(self) -> bool:
        if self._undo is None:
            return False
        self.restore(self._undo)
        self._undo = None
        return True

    def delete(self, ident: Identity) -> None:
        self._push_undo()
        self.deleted.add(ident)
        self.hidden.discard(ident)

    def hide(self, ident: Identity) -> None:
        self._push_undo()
        self.hidden.add(ident)

    def move(self, ident: Identity, current_min: Tuple[int, int, int], delta: Sequence[int]) -> Tuple[int, int, int]:
        self._push_undo()
        base = self.moves.get(ident, current_min)
        nxt = (int(base[0] + delta[0]), int(base[1] + delta[1]), int(base[2] + delta[2]))
        self.moves[ident] = nxt
        return nxt

    def is_removed(self, ident: Identity) -> bool:
        return ident in self.deleted

    def is_inspect_hidden(self, ident: Identity) -> bool:
        return ident in self.hidden or ident in self.deleted

    def min_for(self, ident: Identity, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
        return self.moves.get(ident, fallback)


def resolve_blueprint_dir(path: Path) -> Path:
    path = Path(path)
    if path.is_file() and path.name.lower() == "bp.sbc":
        return path.parent
    if path.is_dir() and (path / "bp.sbc").exists():
        return path
    raise FileNotFoundError(f"No blueprint folder / bp.sbc at {path}")


def unique_edited_dir(source_dir: Path) -> Path:
    parent = source_dir.parent
    base = source_dir.name
    candidate = parent / f"{base} (edited)"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        extra = parent / f"{base} (edited {n})"
        if not extra.exists():
            return extra
        n += 1


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a) == str(b)


def copy_blueprint_folder(source_dir: Path, dest_dir: Path) -> Path:
    """Copy the whole blueprint folder. Refuses to clobber dest or the source."""
    source_dir = resolve_blueprint_dir(source_dir)
    dest_dir = Path(dest_dir)
    if _same_path(source_dir, dest_dir):
        raise ValueError("Refusing to copy a blueprint onto itself. Use overwrite only with confirm.")
    if dest_dir.exists():
        raise FileExistsError(f"Destination already exists: {dest_dir}")
    shutil.copytree(source_dir, dest_dir)
    cache = dest_dir / "bp.sbcB5"
    if cache.exists():
        cache.unlink()
    return dest_dir / "bp.sbc"


def _min_from_element(block: ET.Element) -> Tuple[int, int, int]:
    min_elem = block.find("Min")
    if min_elem is None:
        min_elem = block.find("{*}Min")
    if min_elem is None:
        return (0, 0, 0)
    return (
        int(float(min_elem.attrib.get("x", 0))),
        int(float(min_elem.attrib.get("y", 0))),
        int(float(min_elem.attrib.get("z", 0))),
    )


def _entity_id(block: ET.Element) -> str:
    return (_text(block, "EntityId") or "").strip()


def _identity(grid_eid: str, block: ET.Element) -> Identity:
    return (str(grid_eid or ""), _min_from_element(block), _entity_id(block))


def _matches(ident: Identity, grid_eid: str, block: ET.Element) -> bool:
    gid, mn, eid = ident
    if gid and gid != str(grid_eid or ""):
        return False
    block_eid = _entity_id(block)
    if eid and block_eid:
        return eid == block_eid
    return mn == _min_from_element(block)


def _cube_blocks_parent(grid: ET.Element) -> ET.Element:
    parent = grid.find("CubeBlocks")
    if parent is None:
        parent = grid.find("{*}CubeBlocks")
    return parent if parent is not None else grid


def _index_cube_blocks(root: ET.Element) -> dict:
    """One O(N) pass: identity lookups for delete/move without scanning every ident."""
    by_eid: Dict[Tuple[str, str], Tuple[ET.Element, ET.Element]] = {}
    by_min: Dict[Tuple[str, Tuple[int, int, int]], Tuple[ET.Element, ET.Element]] = {}
    by_eid_any: Dict[str, List[Tuple[ET.Element, ET.Element, str]]] = {}
    by_min_any: Dict[Tuple[int, int, int], List[Tuple[ET.Element, ET.Element, str]]] = {}
    for grid in _iter_cube_grids(root):
        grid_eid = _text(grid, "EntityId") or ""
        parent = _cube_blocks_parent(grid)
        for block in _blocks_in_grid(grid):
            eid = _entity_id(block)
            mn = _min_from_element(block)
            if eid:
                if (grid_eid, eid) not in by_eid:
                    by_eid[(grid_eid, eid)] = (parent, block)
                by_eid_any.setdefault(eid, []).append((parent, block, grid_eid))
            if (grid_eid, mn) not in by_min:
                by_min[(grid_eid, mn)] = (parent, block)
            by_min_any.setdefault(mn, []).append((parent, block, grid_eid))
    return {
        "by_eid": by_eid,
        "by_min": by_min,
        "by_eid_any": by_eid_any,
        "by_min_any": by_min_any,
    }


def _lookup_indexed_block(ident: Identity, index: dict) -> Optional[Tuple[ET.Element, ET.Element]]:
    gid, mn, eid = ident
    if eid:
        if gid:
            hit = index["by_eid"].get((gid, eid))
            if hit is not None:
                return hit
        else:
            hits = index["by_eid_any"].get(eid) or []
            if hits:
                return hits[0][0], hits[0][1]
        if gid:
            hit = index["by_min"].get((gid, mn))
            if hit is not None:
                return hit
        hits = index["by_min_any"].get(mn) or []
        if hits:
            return hits[0][0], hits[0][1]
        return None
    if gid:
        return index["by_min"].get((gid, mn))
    hits = index["by_min_any"].get(mn) or []
    if hits:
        return hits[0][0], hits[0][1]
    return None


def apply_edits_to_tree(
    tree: ET.ElementTree,
    deleted: Iterable[Identity],
    moves: Dict[Identity, Tuple[int, int, int]],
    new_name: Optional[str] = None,
) -> Tuple[int, int]:
    """Remove deleted CubeBlocks and rewrite Min for moves. Returns (deleted, moved)."""
    root = tree.getroot()
    deleted_list = list(deleted)
    deleted_set = set(deleted_list)
    index = _index_cube_blocks(root)
    removed = 0
    for ident in deleted_list:
        hit = _lookup_indexed_block(ident, index)
        if hit is None:
            continue
        parent, block = hit
        try:
            parent.remove(block)
        except ValueError:
            continue
        removed += 1
    moved = 0
    for ident, nxt in moves.items():
        if ident in deleted_set:
            continue
        hit = _lookup_indexed_block(ident, index)
        if hit is None:
            continue
        _parent, block = hit
        min_elem = block.find("Min")
        if min_elem is None:
            min_elem = block.find("{*}Min")
        if min_elem is not None:
            min_elem.attrib["x"] = str(int(nxt[0]))
            min_elem.attrib["y"] = str(int(nxt[1]))
            min_elem.attrib["z"] = str(int(nxt[2]))
            moved += 1
    if new_name:
        _rename_blueprint(root, new_name)
    return removed, moved


def _rename_blueprint(root: ET.Element, name: str) -> None:
    for tag in ("DisplayName", "CustomName"):
        for node in list(root.findall(f".//{tag}")) + list(root.findall(f".//{{*}}{tag}")):
            if node is not None:
                node.text = name
    for sub in list(root.findall(".//Id/SubtypeId")) + list(root.findall(".//{*}Id/{*}SubtypeId")):
        if sub is not None:
            sub.text = name


def save_blueprint_as(
    source_path: Path,
    deleted: Iterable[Identity],
    moves: Dict[Identity, Tuple[int, int, int]],
    dest_dir: Optional[Path] = None,
    overwrite_original: bool = False,
) -> Path:
    """
    Write a NEW blueprint folder with edits applied.

    overwrite_original=True is required to write back into the source
    folder. Default is a sibling "<name> (edited)".
    """
    source_dir = resolve_blueprint_dir(source_path)
    deleted_list = list(deleted)
    if overwrite_original:
        dest = source_dir
        if dest_dir is not None and not _same_path(Path(dest_dir), source_dir):
            raise ValueError("overwrite_original writes the source folder only")
        bp_file = dest / "bp.sbc"
        tree = safe_xml.parse(bp_file)
        apply_edits_to_tree(tree, deleted_list, moves, new_name=None)
        safe_xml.safe_write(tree, bp_file)
        cache = dest / "bp.sbcB5"
        if cache.exists():
            cache.unlink()
        return dest

    dest = Path(dest_dir) if dest_dir is not None else unique_edited_dir(source_dir)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")
    bp_file = copy_blueprint_folder(source_dir, dest)
    tree = safe_xml.parse(bp_file)
    apply_edits_to_tree(tree, deleted_list, moves, new_name=dest.name)
    safe_xml.safe_write(tree, bp_file)
    return dest


def nudge_block_instance(block: BlockInstance, delta: Sequence[int]) -> BlockInstance:
    """Shift Min one cell and keep the world matrix consistent with the grid pose."""
    dx, dy, dz = int(delta[0]), int(delta[1]), int(delta[2])
    old_min = block.local_min
    new_min = (old_min[0] + dx, old_min[1] + dy, old_min[2] + dz)
    cell = cell_size_meters(block.grid_size)
    old_center = ((old_min[0] + 0.5) * cell, (old_min[1] + 0.5) * cell, (old_min[2] + 0.5) * cell)
    new_center = ((new_min[0] + 0.5) * cell, (new_min[1] + 0.5) * cell, (new_min[2] + 0.5) * cell)
    local = mat3_to_mat4(orientation_matrix(block.forward, block.up), old_center)
    grid_world = mul_mat4(block.world_matrix, invert_rigid_mat4(local))
    new_local = mat3_to_mat4(orientation_matrix(block.forward, block.up), new_center)
    block.min_x, block.min_y, block.min_z = new_min
    block.local_min = new_min
    block.world_matrix = mul_mat4(grid_world, new_local)
    return block


__all__ = [
    "GridEditSession",
    "Identity",
    "apply_edits_to_tree",
    "copy_blueprint_folder",
    "nudge_block_instance",
    "resolve_blueprint_dir",
    "save_blueprint_as",
    "unique_edited_dir",
]
