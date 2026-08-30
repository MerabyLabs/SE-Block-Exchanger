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
    color_rgb: Tuple[float, float, float]
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
    total_blocks: int = 0

    def filter_grid(self, grid_name: Optional[str]) -> "PreviewScene":
        if not grid_name:
            return self
        filtered = [b for b in self.blocks if b.grid_name == grid_name]
        grids = [g for g in self.grids if g.name == grid_name]
        return PreviewScene(
            blocks=filtered,
            grids=grids,
            main_grid_name=self.main_grid_name,
            total_blocks=len(filtered),
        )


def extract_scene_from_root(root: ET.Element) -> PreviewScene:
    grids = _iter_cube_grids(root)
    if not grids:
        fake = _single_grid_from_root(root)
        grids = [fake] if fake is not None else []
    if not grids:
        return PreviewScene()

    parsed = [_parse_grid(grid, idx) for idx, grid in enumerate(grids)]
    parsed = [g for g in parsed if g is not None]
    if not parsed:
        return PreviewScene()

    main = max(parsed, key=lambda g: (len(g["blocks"]), -parsed.index(g)))
    world = _assemble_grid_worlds(parsed, main["entity_id"])

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
                    world_matrix=mul_mat4(grid_world, local),
                    local_min=block["min"],
                )
            )

    return PreviewScene(
        blocks=instances,
        grids=poses,
        main_grid_name=main["name"],
        total_blocks=len(instances),
    )


def _single_grid_from_root(root: ET.Element) -> Optional[ET.Element]:
    blocks = root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock") or root.findall(
        ".//MyObjectBuilder_CubeBlock"
    )
    if not blocks:
        return None
    return root


def _parse_grid(grid: ET.Element, idx: int) -> Optional[dict]:
    name = _grid_label(grid, f"Grid {idx + 1}")
    entity_id = _text(grid, "EntityId") or f"grid_{idx}"
    grid_size = _text(grid, "GridSizeEnum") or "Large"
    pose, has_pose = _grid_pose(grid)
    blocks = []
    for b_idx, block in enumerate(_blocks_in_grid(grid)):
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


def _parse_block(block: ET.Element, index: int) -> dict:
    min_elem = block.find("Min")
    if min_elem is None:
        min_elem = block.find("{*}Min")
    if min_elem is not None:
        mn = (
            int(float(min_elem.attrib.get("x", 0))),
            int(float(min_elem.attrib.get("y", 0))),
            int(float(min_elem.attrib.get("z", 0))),
        )
    else:
        mn = (index % 5, index // 25, (index // 5) % 5)

    subtype = _text(block, "SubtypeName") or _text(block, "SubtypeId") or "Block"
    type_id = _type_id(block)
    orient = block.find("BlockOrientation")
    if orient is None:
        orient = block.find("{*}BlockOrientation")
    forward = "Forward"
    up = "Up"
    if orient is not None:
        forward = orient.attrib.get("Forward") or _text(orient, "Forward") or "Forward"
        up = orient.attrib.get("Up") or _text(orient, "Up") or "Up"

    hsv_elem = block.find("ColorMaskHSV")
    if hsv_elem is None:
        hsv_elem = block.find("{*}ColorMaskHSV")
    hsv = parse_xyz_attrib(hsv_elem, 0.0) if hsv_elem is not None else (0.0, 0.0, 0.0)
    color = hsv_offset_to_rgb(*hsv)
    skin = _text(block, "SkinSubtypeId") or "None"
    entity_id = _text(block, "EntityId") or ""
    xsi_type = block.attrib.get(f"{XSI}type", "") or block.attrib.get("xsi:type", "")

    top_id = (
        _text(block, "TopBlockId")
        or _text(block, "TopPartEntityId")
        or _text(block, "RotorEntityId")
        or _text(block, "AttachedSubgridId")
        or _text(block, "TopGridId")
    )
    joint = _classify_joint(xsi_type, subtype)
    angle = _first_float(block, ("CurrentPosition", "Angle", "CurrentAngle", "WeldRotation"))
    displacement = _first_float(block, ("DummyDisplacement", "Displacement", "RotorDisplacement"))
    piston_pos = _first_float(block, ("CurrentPosition",)) if joint == "Piston" else 0.0

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
        "top_id": top_id if top_id and top_id != "0" else None,
        "joint": joint,
        "angle": angle,
        "displacement": displacement,
        "piston_pos": piston_pos,
    }


def _block_local_matrix(block: dict, cell: float) -> list:
    mx, my, mz = block["min"]
    # Occupancy box origin at Min; mesh centered on the first cell.
    center = ((mx + 0.5) * cell, (my + 0.5) * cell, (mz + 0.5) * cell)
    rotation = orientation_matrix(block["forward"], block["up"])
    return mat3_to_mat4(rotation, center)


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


def _assemble_grid_worlds(parsed: List[dict], main_id: str) -> Dict[str, list]:
    by_id = {g["entity_id"]: g for g in parsed}
    block_owner: Dict[str, str] = {}
    for grid in parsed:
        for block in grid["blocks"]:
            if block["entity_id"]:
                block_owner[block["entity_id"]] = grid["entity_id"]

    children: Dict[str, List[tuple]] = {g["entity_id"]: [] for g in parsed}
    child_ids = set()
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
                child_grid = by_id.get(child_id)
                if child_grid is not None:
                    child_grid["attachment_via"] = f"{block['joint'] or 'Mechanical'} ({block['subtype']})"

    usable_poses = sum(1 for g in parsed if g["has_pose"])
    if usable_poses == len(parsed) and len(parsed) > 0:
        return {g["entity_id"]: g["pose"] for g in parsed}

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
    return worlds


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
    found = root.findall(".//CubeGrid") + root.findall(".//{*}CubeGrid")
    unique: List[ET.Element] = []
    seen = set()
    for grid in found:
        key = id(grid)
        if key in seen:
            continue
        seen.add(key)
        unique.append(grid)
    return unique


def _blocks_in_grid(grid: ET.Element) -> List[ET.Element]:
    cube_blocks = grid.find("CubeBlocks")
    if cube_blocks is None:
        cube_blocks = grid.find("{*}CubeBlocks")
    if cube_blocks is not None:
        children = [child for child in list(cube_blocks) if isinstance(child.tag, str)]
        if children:
            return children
    return (
        grid.findall("./CubeBlocks/MyObjectBuilder_CubeBlock")
        or grid.findall("./{*}CubeBlocks/{*}MyObjectBuilder_CubeBlock")
        or grid.findall("./MyObjectBuilder_CubeBlock")
    )


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


def _first_float(element: ET.Element, tags: Tuple[str, ...]) -> float:
    for tag in tags:
        value = _text(element, tag)
        if value:
            try:
                raw = float(value)
            except ValueError:
                continue
            # Rotor CurrentPosition is radians in modern blueprints; if a
            # value looks like degrees (> 2π and a multiple-ish of 1), keep it
            # as radians anyway — Keen stores radians here.
            if tag in ("Angle", "CurrentAngle", "WeldRotation") and abs(raw) > math.pi * 2 + 0.01:
                return math.radians(raw)
            return raw
    return 0.0
