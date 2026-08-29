"""
Isometric and 2.5D Grid Matrix Visualizer.
Generates coordinate bounds, cross-section density slices, and visual block representations.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import safe_xml


@dataclass
class GridBoundingBox:
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int
    max_z: int

    @property
    def size_x(self) -> int:
        return max(1, self.max_x - self.min_x + 1)

    @property
    def size_y(self) -> int:
        return max(1, self.max_y - self.min_y + 1)

    @property
    def size_z(self) -> int:
        return max(1, self.max_z - self.min_z + 1)


@dataclass
class VoxelBlockPoint:
    x: int
    y: int
    z: int
    subtype: str
    category: str
    is_modified: bool = False


@dataclass
class GridMatrixSummary:
    grid_name: str
    bounds: GridBoundingBox
    total_blocks: int
    dense_layers_count: int
    ascii_top_down_view: str
    ascii_side_view: str


class GridMatrixVisualizer:
    """Computes coordinate distribution and ASCII matrix previews of Space Engineers grids."""

    @classmethod
    def analyze_grid_matrix(
        cls,
        blueprint_path: Path,
        modified_subtypes: Optional[Dict[str, str]] = None,
    ) -> List[GridMatrixSummary]:
        blueprint_path = Path(blueprint_path)
        if not blueprint_path.is_file():
            return []

        tree = safe_xml.parse(blueprint_path)
        root = tree.getroot()
        return cls.analyze_element(root, modified_subtypes)

    @classmethod
    def analyze_element(
        cls,
        root: ET.Element,
        modified_subtypes: Optional[Dict[str, str]] = None,
    ) -> List[GridMatrixSummary]:
        summaries: List[GridMatrixSummary] = []
        modified_map = modified_subtypes or {}

        grids = root.findall(".//CubeGrid")
        grid_targets = grids if grids else [root]

        for idx, grid in enumerate(grid_targets):
            name_elem = grid.find("CustomName")
            grid_name = name_elem.text.strip() if (name_elem is not None and name_elem.text) else f"Grid_{idx+1}"

            blocks = grid.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock") or grid.findall(".//MyObjectBuilder_CubeBlock")
            points: List[VoxelBlockPoint] = []
            for b_idx, block in enumerate(blocks):
                min_elem = block.find("Min")
                if min_elem is not None:
                    x = int(min_elem.attrib.get("x", 0))
                    y = int(min_elem.attrib.get("y", 0))
                    z = int(min_elem.attrib.get("z", 0))
                else:
                    x = b_idx % 5
                    y = (b_idx // 25)
                    z = (b_idx // 5) % 5

                sub_name = block.find("SubtypeName")
                sub_id = block.find("SubtypeId")
                subtype_elem = sub_name if sub_name is not None else sub_id
                subtype = subtype_elem.text.strip() if (subtype_elem is not None and subtype_elem.text) else "Block"
                category = cls._categorize_subtype(subtype)
                is_mod = (subtype in modified_map)

                points.append(VoxelBlockPoint(x=x, y=y, z=z, subtype=subtype, category=category, is_modified=is_mod))

            if not points:
                continue

            min_x = min(p.x for p in points)
            max_x = max(p.x for p in points)
            min_y = min(p.y for p in points)
            max_y = max(p.y for p in points)
            min_z = min(p.z for p in points)
            max_z = max(p.z for p in points)
            bounds = GridBoundingBox(min_x, max_x, min_y, max_y, min_z, max_z)

            top_down = cls._render_top_down(points, bounds)
            side_view = cls._render_side_view(points, bounds)

            summaries.append(
                GridMatrixSummary(
                    grid_name=grid_name,
                    bounds=bounds,
                    total_blocks=len(points),
                    dense_layers_count=bounds.size_y,
                    ascii_top_down_view=top_down,
                    ascii_side_view=side_view,
                )
            )

        return summaries

    @staticmethod
    def _categorize_subtype(subtype: str) -> str:
        s = subtype.lower()
        if "prototech" in s:
            return "prototech"
        if "cockpit" in s or "controlseat" in s:
            return "cockpit"
        if "thrust" in s:
            return "thruster"
        if "turret" in s or "gun" in s or "missile" in s or "artillery" in s or "railgun" in s:
            return "weapon"
        if "armor" in s:
            return "armor"
        if "reactor" in s or "battery" in s or "solar" in s or "generator" in s:
            return "power"
        return "utility"

    @classmethod
    def _render_top_down(cls, points: List[VoxelBlockPoint], bounds: GridBoundingBox, width: int = 36, height: int = 18) -> str:
        """Projects blocks down onto the X-Z horizontal plane (Top-Down slice)."""
        grid = [["." for _ in range(width)] for _ in range(height)]
        scale_x = (width - 1) / max(1, bounds.size_x - 1)
        scale_z = (height - 1) / max(1, bounds.size_z - 1)

        for p in points:
            gx = min(width - 1, max(0, int(round((p.x - bounds.min_x) * scale_x))))
            gz = min(height - 1, max(0, int(round((p.z - bounds.min_z) * scale_z))))
            
            char = "#"
            if p.is_modified:
                char = "*"
            elif p.category == "prototech":
                char = "$"
            elif p.category == "cockpit":
                char = "@"
            elif p.category == "weapon":
                char = "!"
            elif p.category == "thruster":
                char = "^"
            elif p.category == "power":
                char = "+"
            grid[gz][gx] = char

        lines = ["Top-Down Projection (X/Z Plane):"]
        lines.append("+" + "-" * width + "+")
        for row in grid:
            lines.append("|" + "".join(row) + "|")
        lines.append("+" + "-" * width + "+")
        lines.append("Legend: [@] Cockpit  [#] Armor/other  [^] Thruster  [!] Weapon  [+] Power  [$] Prototech  [*] Swapped")
        return "\n".join(lines)

    @classmethod
    def _render_side_view(cls, points: List[VoxelBlockPoint], bounds: GridBoundingBox, width: int = 36, height: int = 14) -> str:
        """Projects blocks onto the Z-Y vertical elevation plane (Side/Profile view)."""
        grid = [["." for _ in range(width)] for _ in range(height)]
        scale_z = (width - 1) / max(1, bounds.size_z - 1)
        scale_y = (height - 1) / max(1, bounds.size_y - 1)

        for p in points:
            gz = min(width - 1, max(0, int(round((p.z - bounds.min_z) * scale_z))))
            gy = min(height - 1, max(0, int(round((bounds.max_y - p.y) * scale_y))))  # Invert Y so up is up
            
            char = "#"
            if p.is_modified:
                char = "*"
            elif p.category == "prototech":
                char = "$"
            elif p.category == "cockpit":
                char = "@"
            elif p.category == "weapon":
                char = "!"
            elif p.category == "thruster":
                char = "^"
            grid[gy][gz] = char

        lines = ["Side Profile Projection (Z/Y Elevation):"]
        lines.append("+" + "-" * width + "+")
        for row in grid:
            lines.append("|" + "".join(row) + "|")
        lines.append("+" + "-" * width + "+")
        return "\n".join(lines)

    @classmethod
    def extract_all_voxels(cls, blueprint_path: Path) -> List[dict]:
        """Extracts voxel data for all blocks across all grids in a blueprint."""
        blueprint_path = Path(blueprint_path)
        if not blueprint_path.is_file():
            return []

        try:
            tree = safe_xml.parse(blueprint_path)
            root = tree.getroot()
        except Exception:
            return []

        grids = root.findall(".//CubeGrid")
        grid_targets = grids if grids else [root]
        prepared = []
        for idx, grid in enumerate(grid_targets):
            name_elem = grid.find("CustomName")
            if name_elem is None or not (name_elem.text and name_elem.text.strip()):
                name_elem = grid.find("DisplayName")
            grid_name = name_elem.text.strip() if (name_elem is not None and name_elem.text) else f"Grid_{idx+1}"
            grid_size_elem = grid.find("GridSizeEnum")
            grid_size = grid_size_elem.text.strip() if (grid_size_elem is not None and grid_size_elem.text) else "Large"
            cube_blocks = grid.find("CubeBlocks")
            if cube_blocks is not None and list(cube_blocks):
                blocks = list(cube_blocks)
            else:
                blocks = grid.findall(".//CubeBlocks/*") or grid.findall(".//MyObjectBuilder_CubeBlock")
            prepared.append((idx, grid_name, grid_size, blocks))

        if not prepared:
            return []
        main_idx = max(range(len(prepared)), key=lambda i: (len(prepared[i][3]), -i))
        voxels: List[dict] = []

        for idx, grid_name, grid_size, blocks in prepared:
            is_subgrid = idx != main_idx
            for b_idx, block in enumerate(blocks):
                min_elem = block.find("Min")
                if min_elem is not None:
                    x = int(min_elem.attrib.get("x", 0))
                    y = int(min_elem.attrib.get("y", 0))
                    z = int(min_elem.attrib.get("z", 0))
                else:
                    x = b_idx % 5
                    y = (b_idx // 25)
                    z = (b_idx // 5) % 5

                sub_name = block.find("SubtypeName")
                sub_id = block.find("SubtypeId")
                subtype_elem = sub_name if sub_name is not None else sub_id
                subtype = subtype_elem.text.strip() if (subtype_elem is not None and subtype_elem.text) else "Block"

                voxels.append({
                    "x": x,
                    "y": y,
                    "z": z,
                    "subtype": subtype,
                    "grid_name": grid_name,
                    "grid_size": grid_size,
                    "is_subgrid": is_subgrid,
                })

        return voxels

