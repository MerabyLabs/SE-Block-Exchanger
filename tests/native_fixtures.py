"""Small authored blueprint/catalog fixtures; no user ships or game assets."""
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from engine_compat import _quaternion, _transform
from se_assets.block_identity import BlockIdentity
from se_assets.se2_catalog import (SE2Catalog, NativeArmor, COMPOSITE_TYPE, WORLD_TRANSFORM_TYPE,
                                  GRID_TYPE, HIERARCHY_TYPE, PHYSICS_TYPE)
import safe_xml


def armor_blueprint(folder: Path, size="Large", all_shapes=False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    root = ET.Element("Definitions")
    ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
    grid = ET.SubElement(ET.SubElement(ship, "CubeGrids"), "CubeGrid")
    ET.SubElement(grid, "GridSizeEnum").text = size
    ET.SubElement(grid, "EntityId").text = "9876543210123"
    ET.SubElement(grid, "DisplayName").text = folder.name
    cubes = ET.SubElement(grid, "CubeBlocks")
    shapes = ("ArmorBlock", "ArmorSlope", "ArmorCorner", "ArmorCornerInv") if all_shapes else ("ArmorBlock",)
    for heavy in (False, True):
        for index, suffix in enumerate(shapes):
            block = ET.SubElement(cubes, "MyObjectBuilder_CubeBlock")
            BlockIdentity("CubeBlock", f"{size}{'Heavy' if heavy else ''}Block{suffix}").apply(block)
            ET.SubElement(block, "EntityId").text = str(90000 + len(cubes))
            ET.SubElement(block, "Min", x=str(index), y="0", z=str(int(heavy)))
            ET.SubElement(block, "BlockOrientation", Forward="Forward", Up="Up")
            ET.SubElement(block, "ColorMaskHSV", x="0.575", y="0", z="0")
            ET.SubElement(block, "BuildPercent").text = "1"
            ET.SubElement(block, "IntegrityPercent").text = "1"
    path = folder / "bp.sbc"
    safe_xml.safe_write(ET.ElementTree(root), path)
    return path


def catalog_fixture(root: Path) -> SE2Catalog:
    catalog = SE2Catalog(root)
    catalog.bundles = {"Game2": "2.4.0.29", "VRage": "2.4.0.29", "System.Runtime": "1.0.0.0"}
    catalog.grid_template = {"Definition": "grid", "ObjectBuilders": [
        {"Key": "world", "Value": {"$Type": WORLD_TRANSFORM_TYPE, "TransformWithEulerHint": _transform((0, 0, 0), _quaternion(np.eye(3)))}},
        {"Key": "hierarchy", "Value": {"$Type": HIERARCHY_TYPE, "Children": []}},
        {"Key": "grid", "Value": {"$Type": GRID_TYPE, "DisplayName": {"RawText": "Fixture"}}},
        {"Key": "physics", "Value": {"$Type": PHYSICS_TYPE, "MotionType": "Static"}},
    ]}
    catalog.definitions["grid"] = {"$Type": COMPOSITE_TYPE, "$Value": {"Components": {"Keys": ["world", "hierarchy", "grid", "physics"]}}}
    for size, meters in (("Large", 2.5), ("Small", 0.5)):
        for material in ("", "Heavy"):
            for shape in ("ArmorBlock", "ArmorSlope", "ArmorCorner", "ArmorCornerInv"):
                name = f"{size}{material}Block{shape}"
                keys = ("transform", "hierarchy", "block", "armor")
                entry = NativeArmor(name, name, f"definition_{name}", keys, meters)
                catalog.by_se1[name] = entry
                catalog.by_composition[name] = entry
                catalog.definitions[name] = {"$Type": COMPOSITE_TYPE, "$Value": {"Components": {"Keys": list(keys)}}}
    return catalog
