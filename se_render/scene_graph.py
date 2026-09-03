"""
Build a renderable multi-grid scene from a blueprint XML tree.

Uses CubeGrid PositionAndOrientation when present. Otherwise assembles
child grids from rotor / hinge / piston bases and stored joint values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

import safe_xml
from se_render.hsv import hsv_offset_to_rgb
from se_render.orientation import (
    BASE6,
    cell_size_meters,
    identity_mat4,
    mat3_to_mat4,
    mul_mat4,
    orientation_matrix,
    parse_xyz_attrib,
    parse_xyz_children,
    pose_matrix,
    rotation_axis_mat4,
    transform_dir,
    transform_point,
    translation_mat4,
)


XSI = "{http://www.w3.org/2001/XMLSchema-instance}"


@dataclass
class BlockInstance:
    grid_name: str
    grid_entity_id: str
    grid_size: str
    is_subgrid: bool
    subtype: str
    type_id: str
    entity_id: str
    min_x: int
    min_y: int
    min_z: int
    forward: str
    up: str
    hsv: Tuple[float, float, float]
    color_rgb: Optional[Tuple[float, float, float]]
    skin: str
    world_matrix: List[List[float]]
    local_min: Tuple[int, int, int]


@dataclass
class GridPose:
    entity_id: str
    name: str
    grid_size: str
    world_matrix: List[List[float]]
    from_blueprint_pose: bool
    attachment_via: Optional[str] = None


@dataclass
class PreviewScene:
    blocks: List[BlockInstance] = field(default_factory=list)
    grids: List[GridPose] = field(default_factory=list)
    main_grid_name: str = ""
    main_grid_entity_id: str = ""
    total_blocks: int = 0
    # child CubeGrid EntityId → parent CubeGrid EntityId (mechanical attach)
    parent_of: Dict[str, str] = field(default_factory=dict)

    def filter_grid(
        self,
        grid_name: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
    ) -> "PreviewScene":
        if grid_entity_id:
            filtered = [b for b in self.blocks if b.grid_entity_id == grid_entity_id]
            grids = [g for g in self.grids if g.entity_id == grid_entity_id]
        elif grid_name:
            filtered = [b for b in self.blocks if b.grid_name == grid_name]
            grids = [g for g in self.grids if g.name == grid_name]
        else:
            return self
        keep_ids = {g.entity_id for g in grids}
        return PreviewScene(
            blocks=filtered,
            grids=grids,
            main_grid_name=self.main_grid_name,
            main_grid_entity_id=self.main_grid_entity_id,
            total_blocks=len(filtered),
            parent_of={c: p for c, p in self.parent_of.items() if c in keep_ids and p in keep_ids},
        )


def extract_scene_from_root(
    root: ET.Element,
    token=None,
    generation: int = 0,
) -> PreviewScene:
    if token is not None:
        token.raise_if_stale(generation)
    grids = _iter_cube_grids(root)
    if not grids:
        fake = _single_grid_from_root(root)
        grids = [fake] if fake is not None else []
    if not grids:
        return PreviewScene()

    candidates = [_parse_grid(grid, idx, token=token, generation=generation) for idx, grid in enumerate(grids)]
    parsed = [g for g in candidates if g is not None]
    if not parsed:
        return PreviewScene()

    children, parent_of, child_ids = _link_mechanical_grids(parsed)
    non_children = [g for g in parsed if g["entity_id"] not in child_ids] or parsed
    main = max(non_children, key=lambda g: (len(g["blocks"]), -parsed.index(g)))
    world, parent_of = _assemble_grid_worlds(parsed, main["entity_id"], children, parent_of)

    instances: List[BlockInstance] = []
    poses: List[GridPose] = []
    for grid in parsed:
        gid = grid["entity_id"]
        grid_world = world.get(gid, identity_mat4())
        poses.append(
            GridPose(
                entity_id=gid,
                name=grid["name"],
                grid_size=grid["grid_size"],
                world_matrix=grid_world,
                from_blueprint_pose=grid["has_pose"],
                attachment_via=grid.get("attachment_via"),
            )
        )
        cell = cell_size_meters(grid["grid_size"])
        is_sub = gid != main["entity_id"]
        identity_world = _is_identity_mat4(grid_world)
        for block in grid["blocks"]:
            local = _block_local_matrix(block, cell)
            instances.append(
                BlockInstance(
                    grid_name=grid["name"],
                    grid_entity_id=gid,
                    grid_size=grid["grid_size"],
                    is_subgrid=is_sub,
                    subtype=block["subtype"],
                    type_id=block["type_id"],
                    entity_id=block["entity_id"],
                    min_x=block["min"][0],
                    min_y=block["min"][1],
                    min_z=block["min"][2],
                    forward=block["forward"],
                    up=block["up"],
                    hsv=block["hsv"],
                    color_rgb=block["color_rgb"],
                    skin=block["skin"],
                    world_matrix=local if identity_world else mul_mat4(grid_world, local),
                    local_min=block["min"],
                )
            )

    return PreviewScene(
        blocks=instances,
        grids=poses,
        main_grid_name=main["name"],
        main_grid_entity_id=main["entity_id"],
        total_blocks=len(instances),
        parent_of=parent_of,
    )


def voxels_from_scene(scene: PreviewScene) -> List[dict]:
    """2D map points derived from the same BlockInstance list the 3D preview uses."""
    return [
        {
            "x": block.min_x,
            "y": block.min_y,
            "z": block.min_z,
            "subtype": block.subtype,
            "grid_name": block.grid_name,
            "grid_entity_id": block.grid_entity_id,
            "grid_size": block.grid_size,
            "is_subgrid": block.is_subgrid,
            "hsv": block.hsv,
            "color_rgb": block.color_rgb,
        }
        for block in scene.blocks
    ]


def _single_grid_from_root(root: ET.Element) -> Optional[ET.Element]:
    blocks = root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock") or root.findall(
        ".//MyObjectBuilder_CubeBlock"
    )
    if not blocks:
        return None
    return root


def _parse_grid(grid: ET.Element, idx: int, token=None, generation: int = 0) -> Optional[dict]:
    name = _grid_label(grid, f"Grid {idx + 1}")
    entity_id = _text(grid, "EntityId") or f"grid_{idx}"
    grid_size = _text(grid, "GridSizeEnum") or "Large"
    pose, has_pose = _grid_pose(grid)
    blocks = []
    for b_idx, block in enumerate(safe_xml.iter_blocks_in_grid(grid)):
        if token is not None and (b_idx & 255) == 0:
            token.raise_if_stale(generation)
        blocks.append(_parse_block(block, b_idx))
    if not blocks and idx > 0:
        return None
    return {
        "name": name,
        "entity_id": entity_id,
        "grid_size": grid_size,
        "pose": pose,
        "has_pose": has_pose,
        "blocks": blocks,
        "element": grid,
        "attachment_via": None,
    }


_HSV_RGB_CACHE: Dict[Tuple[float, float, float], Tuple[float, float, float]] = {}


def _color_rgb(hsv: Tuple[float, float, float]) -> Tuple[float, float, float]:
    key = hsv
    cached = _HSV_RGB_CACHE.get(key)
    if cached is not None:
        return cached
    color = hsv_offset_to_rgb(*hsv)
    _HSV_RGB_CACHE[key] = color
    return color


def _parse_block(block: ET.Element, index: int) -> dict:
    kids = safe_xml.index_children(block)
    min_elem = kids.get("Min")
    if min_elem is not None:
        mn = (
            int(float(min_elem.attrib.get("x", 0))),
            int(float(min_elem.attrib.get("y", 0))),
            int(float(min_elem.attrib.get("z", 0))),
        )
    else:
        mn = (index % 5, index // 25, (index // 5) % 5)

    subtype = _kid_text(kids, "SubtypeName") or _kid_text(kids, "SubtypeId") or ""
    type_id = _type_id(block)
    orient = kids.get("BlockOrientation")
    forward = "Forward"
    up = "Up"
    if orient is not None:
        forward = orient.attrib.get("Forward") or _text(orient, "Forward") or "Forward"
        up = orient.attrib.get("Up") or _text(orient, "Up") or "Up"

    hsv_elem = kids.get("ColorMaskHSV")
    if hsv_elem is not None:
        hsv = parse_xyz_attrib(hsv_elem, 0.0)
        color = _color_rgb(hsv)
    else:
        hsv = (0.0, 0.0, 0.0)
        color = None
    skin = _kid_text(kids, "SkinSubtypeId") or "None"
    entity_id = _kid_text(kids, "EntityId") or ""
    xsi_type = block.attrib.get(f"{XSI}type", "") or block.attrib.get("xsi:type", "")

    joint = _classify_joint(xsi_type, subtype)
    top_id = None
    angle = 0.0
    displacement = 0.0
    piston_pos = 0.0
    if joint or _looks_mechanical(xsi_type, subtype, kids):
        top_id = (
            _kid_text(kids, "TopBlockId")
            or _kid_text(kids, "TopPartEntityId")
            or _kid_text(kids, "RotorEntityId")
            or _kid_text(kids, "AttachedSubgridId")
            or _kid_text(kids, "TopGridId")
        )
        if top_id == "0":
            top_id = None
        angle = _kid_float(kids, ("CurrentPosition", "Angle", "CurrentAngle", "WeldRotation"))
        displacement = _kid_float(kids, ("DummyDisplacement", "Displacement", "RotorDisplacement"))
        piston_pos = _kid_float(kids, ("CurrentPosition",)) if joint == "Piston" else 0.0

    return {
        "min": mn,
        "subtype": subtype,
        "type_id": type_id,
        "forward": forward,
        "up": up,
        "hsv": hsv,
        "color_rgb": color,
        "skin": skin,
        "entity_id": entity_id,
        "xsi_type": xsi_type,
        "top_id": top_id,
        "joint": joint,
        "angle": angle,
        "displacement": displacement,
        "piston_pos": piston_pos,
    }


def _block_local_matrix(block: dict, cell: float) -> list:
    mx, my, mz = block["min"]
    # Occupancy box origin at Min; mesh centered on the first cell.
    center = ((mx + 0.5) * cell, (my + 0.5) * cell, (mz + 0.5) * cell)
    if block["forward"] == "Forward" and block["up"] == "Up":
        return [
            [1.0, 0.0, 0.0, center[0]],
            [0.0, 1.0, 0.0, center[1]],
            [0.0, 0.0, 1.0, center[2]],
            [0.0, 0.0, 0.0, 1.0],
        ]
    rotation = orientation_matrix(block["forward"], block["up"])
    return mat3_to_mat4(rotation, center)


def _is_identity_mat4(matrix: list) -> bool:
    return (
        matrix[0][0] == 1.0
        and matrix[1][1] == 1.0
        and matrix[2][2] == 1.0
        and matrix[0][3] == 0.0
        and matrix[1][3] == 0.0
        and matrix[2][3] == 0.0
        and matrix[0][1] == 0.0
        and matrix[0][2] == 0.0
        and matrix[1][0] == 0.0
        and matrix[1][2] == 0.0
        and matrix[2][0] == 0.0
        and matrix[2][1] == 0.0
    )


def _grid_pose(grid: ET.Element) -> Tuple[list, bool]:
    node = grid.find("PositionAndOrientation")
    if node is None:
        node = grid.find("{*}PositionAndOrientation")
    if node is None:
        return identity_mat4(), False
    pos_el = node.find("Position")
    if pos_el is None:
        pos_el = node.find("{*}Position")
    fwd_el = node.find("Forward")
    if fwd_el is None:
        fwd_el = node.find("{*}Forward")
    up_el = node.find("Up")
    if up_el is None:
        up_el = node.find("{*}Up")
    pos = parse_xyz_attrib(pos_el) if pos_el is not None else parse_xyz_children(node.find("Position"))
    if fwd_el is not None:
        forward = parse_xyz_attrib(fwd_el)
    else:
        forward = BASE6["Forward"]
    if up_el is not None:
        up = parse_xyz_attrib(up_el)
    else:
        up = BASE6["Up"]
    if pos == (0.0, 0.0, 0.0) and forward == BASE6["Forward"] and up == BASE6["Up"]:
        # Identity pose is still a valid stored pose for the main hull.
        return pose_matrix(pos, forward, up), True
    return pose_matrix(pos, forward, up), True


def _link_mechanical_grids(
    parsed: List[dict],
) -> Tuple[Dict[str, List[tuple]], Dict[str, str], set]:
    by_id = {g["entity_id"]: g for g in parsed}
    block_owner: Dict[str, str] = {}
    for grid in parsed:
        for block in grid["blocks"]:
            if block["entity_id"]:
                block_owner[block["entity_id"]] = grid["entity_id"]

    children: Dict[str, List[tuple]] = {g["entity_id"]: [] for g in parsed}
    parent_of: Dict[str, str] = {}
    child_ids: set = set()
    for grid in parsed:
        for block in grid["blocks"]:
            top = block.get("top_id")
            if not top:
                continue
            child_id = None
            if top in by_id:
                child_id = top
            elif top in block_owner:
                child_id = block_owner[top]
            if child_id and child_id != grid["entity_id"]:
                children[grid["entity_id"]].append((child_id, block))
                child_ids.add(child_id)
                parent_of[child_id] = grid["entity_id"]
                child_grid = by_id.get(child_id)
                if child_grid is not None:
                    child_grid["attachment_via"] = f"{block['joint'] or 'Mechanical'} ({block['subtype']})"
    return children, parent_of, child_ids


def _assemble_grid_worlds(
    parsed: List[dict],
    main_id: str,
    children: Optional[Dict[str, List[tuple]]] = None,
    parent_of: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, list], Dict[str, str]]:
    if children is None or parent_of is None:
        children, parent_of, _ = _link_mechanical_grids(parsed)
    by_id = {g["entity_id"]: g for g in parsed}

    usable_poses = sum(1 for g in parsed if g["has_pose"])
    if usable_poses == len(parsed) and len(parsed) > 0:
        return {g["entity_id"]: g["pose"] for g in parsed}, parent_of

    worlds: Dict[str, list] = {}
    main = by_id[main_id]
    worlds[main_id] = main["pose"] if main["has_pose"] else identity_mat4()

    def walk(parent_id: str, visited: set) -> None:
        visited.add(parent_id)
        parent_world = worlds[parent_id]
        parent_grid = by_id[parent_id]
        cell = cell_size_meters(parent_grid["grid_size"])
        for child_id, base_block in children.get(parent_id, []):
            if child_id in visited or child_id not in by_id:
                continue
            worlds[child_id] = _child_world(parent_world, base_block, by_id[child_id], cell)
            walk(child_id, visited)

    walk(main_id, set())
    for grid in parsed:
        if grid["entity_id"] not in worlds:
            worlds[grid["entity_id"]] = grid["pose"] if grid["has_pose"] else identity_mat4()
    return worlds, parent_of


def _child_world(parent_world: list, base_block: dict, child_grid: dict, parent_cell: float) -> list:
    if child_grid["has_pose"] and _pose_is_nonzero(child_grid["pose"]):
        return child_grid["pose"]

    base_local = _block_local_matrix(base_block, parent_cell)
    base_world = mul_mat4(parent_world, base_local)
    joint = base_block.get("joint") or "Mechanical"
    axis = transform_dir(base_world, BASE6["Up"])
    attach = _attach_offset(joint, parent_cell, base_block)
    offset = translation_mat4(
        (
            axis[0] * attach,
            axis[1] * attach,
            axis[2] * attach,
        )
    )
    angle = float(base_block.get("angle") or 0.0)
    if joint == "Piston":
        angle = 0.0
    spin = rotation_axis_mat4(axis, angle)
    head = mul_mat4(offset, spin)

    child_cell = cell_size_meters(child_grid["grid_size"])
    top = _top_part_block(child_grid, base_block)
    if top is not None:
        top_local = _block_local_matrix(top, child_cell)
        # Inverse of a rigid top-part local matrix: map child origin so the
        # top part sits on the mechanical head.
        inv_top = _invert_local(top_local)
        return mul_mat4(mul_mat4(base_world, head), inv_top)
    return mul_mat4(base_world, head)


def _attach_offset(joint: str, cell: float, block: dict) -> float:
    if joint == "Piston":
        return float(block.get("piston_pos") or 0.0) + cell
    return cell * 0.5 + float(block.get("displacement") or 0.0)


def _top_part_block(child_grid: dict, base_block: dict) -> Optional[dict]:
    top_id = base_block.get("top_id")
    if top_id:
        for block in child_grid["blocks"]:
            if block["entity_id"] == top_id:
                return block
    for block in child_grid["blocks"]:
        subtype = block["subtype"].lower()
        if "rotorpart" in subtype or "hingepart" in subtype or "pistonpart" in subtype or "pistonhead" in subtype:
            return block
    return None


def _invert_local(matrix: list) -> list:
    # Transpose rotation, then -R^T * t
    r00, r01, r02, tx = matrix[0]
    r10, r11, r12, ty = matrix[1]
    r20, r21, r22, tz = matrix[2]
    return [
        [r00, r10, r20, -(r00 * tx + r10 * ty + r20 * tz)],
        [r01, r11, r21, -(r01 * tx + r11 * ty + r21 * tz)],
        [r02, r12, r22, -(r02 * tx + r12 * ty + r22 * tz)],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _pose_is_nonzero(pose: list) -> bool:
    origin = transform_point(pose, (0.0, 0.0, 0.0))
    return abs(origin[0]) + abs(origin[1]) + abs(origin[2]) > 1e-4


def _classify_joint(xsi_type: str, subtype: str) -> Optional[str]:
    blob = f"{xsi_type} {subtype}"
    if "Hinge" in blob:
        return "Hinge"
    if "Motor" in xsi_type or "Rotor" in subtype:
        return "Rotor"
    if "Piston" in blob:
        return "Piston"
    return None


def _type_id(block: ET.Element) -> str:
    xsi = block.attrib.get(f"{XSI}type") or block.attrib.get("xsi:type") or ""
    if xsi.startswith("MyObjectBuilder_"):
        return xsi[len("MyObjectBuilder_") :]
    if xsi:
        return xsi
    return "CubeBlock"


def _iter_cube_grids(root: ET.Element) -> List[ET.Element]:
    return safe_xml.iter_cube_grids(root)


def _blocks_in_grid(grid: ET.Element) -> List[ET.Element]:
    return safe_xml.iter_blocks_in_grid(grid)


def _looks_mechanical(xsi_type: str, subtype: str, kids: Dict[str, ET.Element]) -> bool:
    if any(tag in kids for tag in ("TopBlockId", "TopPartEntityId", "RotorEntityId", "AttachedSubgridId", "TopGridId")):
        return True
    blob = f"{xsi_type} {subtype}".lower()
    return "rotor" in blob or "stator" in blob or "hinge" in blob or "piston" in blob


def _kid_text(kids: Dict[str, ET.Element], tag: str) -> Optional[str]:
    child = kids.get(tag)
    if child is not None and child.text and child.text.strip():
        return child.text.strip()
    return None


def _kid_float(kids: Dict[str, ET.Element], tags: Tuple[str, ...]) -> float:
    for tag in tags:
        value = _kid_text(kids, tag)
        if not value:
            continue
        try:
            raw = float(value)
        except ValueError:
            continue
        if tag in ("Angle", "CurrentAngle", "WeldRotation") and abs(raw) > math.pi * 2 + 0.01:
            return math.radians(raw)
        return raw
    return 0.0


def _grid_label(grid: ET.Element, fallback: str) -> str:
    for tag in ("DisplayName", "CustomName", "Name"):
        value = _text(grid, tag)
        if value:
            return value
    return fallback


def _text(element: ET.Element, tag: str) -> Optional[str]:
    child = element.find(tag)
    if child is None:
        child = element.find(f"{{*}}{tag}")
    if child is not None and child.text and child.text.strip():
        return child.text.strip()
    return None
