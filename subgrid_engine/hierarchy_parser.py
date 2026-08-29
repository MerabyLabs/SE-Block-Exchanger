"""
Multi-grid and Subgrid Hierarchy Parser.
Discovers and models parent-child mechanical relationships (rotors, hinges, pistons) across CubeGrids.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import xml.etree.ElementTree as ET
import safe_xml


@dataclass
class MechanicalLink:
    """Represents a mechanical block connecting two grids."""
    block_type: str  # Rotor, Hinge, Piston (mechanical; connectors are not parsed yet)
    subtype: str
    custom_name: str
    base_entity_id: str
    top_entity_id: Optional[str]


@dataclass
class SubgridNode:
    """Represents a single CubeGrid and its child subgrids."""
    grid_name: str
    entity_id: str
    grid_size: str  # "Large" or "Small"
    block_count: int
    is_main_grid: bool
    attachment_via: Optional[str]  # e.g., "Rotor (Large Advanced Rotor)"
    children: List[SubgridNode] = field(default_factory=list)


@dataclass
class MultiGridStructure:
    """Overall multi-grid structure of a blueprint."""
    root_node: Optional[SubgridNode]
    total_grids: int
    total_blocks: int
    mechanical_links: List[MechanicalLink]
    orphaned_grids: List[SubgridNode] = field(default_factory=list)


class SubgridHierarchyParser:
    """Parses blueprint XML into a connected tree of CubeGrids."""

    @classmethod
    def parse_file(cls, blueprint_path: Path) -> MultiGridStructure:
        blueprint_path = Path(blueprint_path)
        if not blueprint_path.is_file():
            return MultiGridStructure(root_node=None, total_grids=0, total_blocks=0, mechanical_links=[])

        try:
            tree = safe_xml.parse(blueprint_path)
            root = tree.getroot()
            return cls.parse_element(root)
        except Exception:
            return MultiGridStructure(root_node=None, total_grids=0, total_blocks=0, mechanical_links=[])

    @staticmethod
    def _iter_blocks(grid: ET.Element) -> List[ET.Element]:
        cube_blocks = grid.find("CubeBlocks")
        if cube_blocks is not None:
            children = list(cube_blocks)
            if children:
                return children
        return (
            grid.findall(".//CubeBlocks/*")
            or grid.findall(".//MyObjectBuilder_CubeBlock")
        )

    @classmethod
    def parse_element(cls, root: ET.Element) -> MultiGridStructure:
        grids = root.findall(".//CubeGrid")
        if not grids:
            blocks = cls._iter_blocks(root)
            if blocks:
                node = SubgridNode(
                    grid_name="MainGrid",
                    entity_id="grid_default",
                    grid_size="Large",
                    block_count=len(blocks),
                    is_main_grid=True,
                    attachment_via=None,
                    children=[],
                )
                return MultiGridStructure(
                    root_node=node,
                    total_grids=1,
                    total_blocks=len(blocks),
                    mechanical_links=[],
                    orphaned_grids=[],
                )
            return MultiGridStructure(root_node=None, total_grids=0, total_blocks=0, mechanical_links=[])

        grid_data: Dict[str, dict] = {}
        all_links: List[MechanicalLink] = []
        top_to_base_map: Dict[str, str] = {}  # top_part_id -> base_grid_id
        top_id_to_link_desc: Dict[str, str] = {}

        for grid in grids:
            grid_entity_id = cls._get_text(grid, "EntityId") or f"grid_{id(grid)}"
            grid_name = cls._get_text(grid, "CustomName") or cls._get_text(grid, "DisplayName") or "CubeGrid"
            grid_size = cls._get_text(grid, "GridSizeEnum") or "Large"

            blocks = cls._iter_blocks(grid)
            block_count = len(blocks)

            # Detect mechanical bases and top parts in this grid
            for block in blocks:
                xsi_type = block.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                subtype = cls._get_text(block, "SubtypeName") or cls._get_text(block, "SubtypeId") or "Block"
                custom_name = cls._get_text(block, "CustomName") or subtype

                top_part_id = (
                    cls._get_text(block, "TopBlockId")
                    or cls._get_text(block, "TopPartEntityId")
                    or cls._get_text(block, "RotorEntityId")
                    or cls._get_text(block, "AttachedSubgridId")
                )
                if top_part_id and top_part_id != "0":
                    link_type = "Mechanical"
                    if "Motor" in xsi_type or "Rotor" in subtype:
                        link_type = "Hinge" if "Hinge" in subtype else "Rotor"
                    elif "Piston" in xsi_type or "Piston" in subtype:
                        link_type = "Piston"

                    link = MechanicalLink(
                        block_type=link_type,
                        subtype=subtype,
                        custom_name=custom_name,
                        base_entity_id=grid_entity_id,
                        top_entity_id=top_part_id,
                    )
                    all_links.append(link)
                    top_to_base_map[top_part_id] = grid_entity_id
                    top_id_to_link_desc[top_part_id] = f"{link_type} ({custom_name})"

            grid_data[grid_entity_id] = {
                "name": grid_name,
                "entity_id": grid_entity_id,
                "grid_size": grid_size,
                "block_count": block_count,
                "element": grid,
            }

        # Match top parts on child grids to identify parent-child connections
        parent_child_map: Dict[str, List[tuple]] = {gid: [] for gid in grid_data}
        child_grid_ids: Set[str] = set()

        for grid_id, data in grid_data.items():
            grid_elem = data["element"]
            for block in cls._iter_blocks(grid_elem):
                block_id = cls._get_text(block, "EntityId")
                if block_id in top_to_base_map:
                    parent_grid_id = top_to_base_map[block_id]
                    if parent_grid_id != grid_id:
                        desc = top_id_to_link_desc.get(block_id, "Mechanical Link")
                        parent_child_map[parent_grid_id].append((grid_id, desc))
                        child_grid_ids.add(grid_id)

        # Identify primary root grid (largest block count among non-children)
        root_candidates = [gid for gid in grid_data if gid not in child_grid_ids]
        if not root_candidates:
            root_candidates = list(grid_data.keys())

        # Pick candidate with highest block count as main hull
        root_grid_id = max(root_candidates, key=lambda gid: grid_data[gid]["block_count"])

        def build_tree(current_id: str, attachment_desc: Optional[str], visited: Set[str]) -> SubgridNode:
            visited.add(current_id)
            cdata = grid_data[current_id]
            node = SubgridNode(
                grid_name=cdata["name"],
                entity_id=cdata["entity_id"],
                grid_size=cdata["grid_size"],
                block_count=cdata["block_count"],
                is_main_grid=(current_id == root_grid_id),
                attachment_via=attachment_desc,
                children=[],
            )
            for child_id, desc in parent_child_map.get(current_id, []):
                if child_id not in visited and child_id in grid_data:
                    node.children.append(build_tree(child_id, desc, visited))
            return node

        visited_nodes: Set[str] = set()
        root_node = build_tree(root_grid_id, None, visited_nodes)

        orphans: List[SubgridNode] = []
        for gid in grid_data:
            if gid not in visited_nodes:
                orphans.append(build_tree(gid, "Unlinked Grid", visited_nodes))

        total_blocks = sum(d["block_count"] for d in grid_data.values())

        return MultiGridStructure(
            root_node=root_node,
            total_grids=len(grid_data),
            total_blocks=total_blocks,
            mechanical_links=all_links,
            orphaned_grids=orphans,
        )

    @staticmethod
    def _get_text(element: ET.Element, tag: str) -> Optional[str]:
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None
