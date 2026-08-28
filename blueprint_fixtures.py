"""Shared helpers for constructing Space Engineers blueprint XML in tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

BlockSpec = Union[str, dict]


def write_blueprint(
    destination: Path,
    blocks: Sequence[BlockSpec],
    grid_size: str = "Large",
    include_grid: bool = True,
) -> Path:
    """
    Write a minimal bp.sbc.

    Each block may be a subtype string or a dict with keys:
    subtype, orientation (Forward), min (x, y, z tuple).
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("Definitions")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    ship_blueprints = ET.SubElement(root, "ShipBlueprints")
    ship_blueprint = ET.SubElement(ship_blueprints, "ShipBlueprint")

    if include_grid:
        cube_grid = ET.SubElement(ship_blueprint, "CubeGrid")
        ET.SubElement(cube_grid, "GridSizeEnum").text = grid_size
        cube_blocks = ET.SubElement(cube_grid, "CubeBlocks")
    else:
        cube_blocks = ET.SubElement(ship_blueprint, "CubeBlocks")

    for spec in blocks:
        if isinstance(spec, str):
            subtype = spec
            orientation = None
            min_xyz = None
        else:
            subtype = spec["subtype"]
            orientation = spec.get("orientation")
            min_xyz = spec.get("min")

        block = ET.SubElement(cube_blocks, "MyObjectBuilder_CubeBlock")
        ET.SubElement(block, "SubtypeId").text = subtype
        ET.SubElement(block, "SubtypeName").text = subtype
        if orientation:
            ET.SubElement(block, "BlockOrientation").attrib.update(
                {"Forward": orientation, "Up": "Up"}
            )
        if min_xyz:
            ET.SubElement(block, "Min").attrib.update(
                {"x": str(min_xyz[0]), "y": str(min_xyz[1]), "z": str(min_xyz[2])}
            )

    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def write_blueprint_dir(
    parent: Path,
    name: str,
    blocks: Sequence[BlockSpec],
    grid_size: str = "Large",
    extra_files: Optional[Iterable[str]] = None,
) -> Path:
    folder = Path(parent) / name
    folder.mkdir(parents=True, exist_ok=True)
    write_blueprint(folder / "bp.sbc", blocks, grid_size=grid_size)
    for extra in extra_files or ():
        (folder / extra).write_text("dummy", encoding="utf-8")
    return folder
