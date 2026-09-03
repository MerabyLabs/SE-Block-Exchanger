"""Native SE1 XML and SE2 EntityBundle conversion with explicit support limits."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import hashlib
import math
from pathlib import Path
import shutil
import tempfile
import uuid
import xml.etree.ElementTree as ET

import numpy as np
import safe_xml
from se_assets.block_identity import BlockIdentity
from se_assets.se2_catalog import (
    BLOCK_TYPE, CHILD_TRANSFORM_TYPE, ENTITY_BUNDLE, GRID_TYPE, HIERARCHY_TYPE,
    WORLD_TRANSFORM_TYPE, PHYSICS_TYPE, SE2Catalog, blueprint_root, component, find_install,
    validate_bundle,
)
from se_render.hsv import hsv_offset_to_standard
from se_render.orientation import BASE6, orientation_matrix


class GameEngine(str, Enum):
    SPACE_ENGINEERS_1 = "SE1_VRAGE2"
    SPACE_ENGINEERS_2 = "SE2_VRAGE3"


class BlueprintFormat(str, Enum):
    SE1_SBC_XML = "se1_sbc_xml"
    SE1_SBCB5_BIN = "se1_sbcb5_binary"
    SE2_JSON = "se2_json"
    SE2_VRAGE3_PKG = "se2_vrage3_package"  # legacy enum, never guessed from extension
    UNKNOWN = "unknown"


@dataclass
class EngineCompatibilityReport:
    source_path: Path
    detected_engine: GameEngine
    detected_format: BlueprintFormat
    is_se1_compatible: bool = False
    is_se2_compatible: bool = False
    se2_migratable: bool = False
    unsupported_blocks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    supported_blocks: int = 0
    total_blocks: int = 0
    catalog_validated: bool = False


class UnsupportedBlueprintError(ValueError):
    """Conversion did not write output because some input cannot be represented."""
    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("Conversion blocked:\n" + "\n".join(self.issues[:20])
                         + (f"\n... {len(self.issues) - 20} more issue(s)" if len(self.issues) > 20 else ""))


def _input(path: Path, filename: str) -> Path:
    path = Path(path)
    return path / filename if path.is_dir() else path


def _catalog(catalog=None) -> SE2Catalog:
    return catalog if catalog is not None else SE2Catalog(find_install()).load()


def _vec(node, default=(0.0, 0.0, 0.0)) -> list[float]:
    if node is None:
        return list(default)
    return [float(node.get(a.lower(), node.get(a, node.findtext("{*}" + a, str(default[i])))))
            for i, a in enumerate("XYZ")]


def _xyz(values) -> dict:
    return dict(zip("XYZ", (float(v) for v in values)))


def _quaternion(matrix) -> dict:
    """Stable matrix-to-quaternion conversion, including 180 degree rotations."""
    m = np.asarray(matrix, dtype=float)
    k = np.array([
        [m[0, 0]-m[1, 1]-m[2, 2], m[1, 0]+m[0, 1], m[2, 0]+m[0, 2], m[2, 1]-m[1, 2]],
        [m[1, 0]+m[0, 1], m[1, 1]-m[0, 0]-m[2, 2], m[2, 1]+m[1, 2], m[0, 2]-m[2, 0]],
        [m[2, 0]+m[0, 2], m[2, 1]+m[1, 2], m[2, 2]-m[0, 0]-m[1, 1], m[1, 0]-m[0, 1]],
        [m[2, 1]-m[1, 2], m[0, 2]-m[2, 0], m[1, 0]-m[0, 1], m.trace()],
    ]) / 3.0
    _, vectors = np.linalg.eigh(k)
    q = vectors[:, -1]
    if q[3] < 0:
        q = -q
    return dict(zip("XYZW", (float(x) for x in q)))


def _rotation(q: dict) -> np.ndarray:
    values = np.array([float(q.get(a, 1 if a == "W" else 0)) for a in "XYZW"])
    norm = float(np.linalg.norm(values))
    if not math.isfinite(norm) or norm < 1e-9:
        raise ValueError("Invalid native orientation quaternion")
    x, y, z, w = values / norm
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _transform(position, orientation) -> dict:
    return {"Transform": {"Position": _xyz(position), "Orientation": orientation},
            "EulerHint": {"X": 0, "Y": 0, "Z": 0}}


def _pose(grid) -> tuple:
    pose = grid.find("{*}PositionAndOrientation")
    if pose is None:
        return [0, 0, 0], _quaternion(np.eye(3))
    forward = np.array(_vec(pose.find("{*}Forward"), (0, 0, -1)))
    up = np.array(_vec(pose.find("{*}Up"), (0, 1, 0)))
    matrix = np.column_stack((np.cross(forward, up), up, -forward))
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-5):
        raise ValueError("Invalid SE1 grid orientation")
    return _vec(pose.find("{*}Position")), _quaternion(matrix)


def _preflight(root, catalog: SE2Catalog):
    grids = safe_xml.iter_cube_grids(root)
    issues = []
    unsupported: Counter[str] = Counter()
    supported = total = 0
    if len(grids) != 1:
        issues.append("Native migration currently supports one grid; mechanical subgrids require a separate migration implementation.")
    for grid in grids:
        size = grid.findtext("{*}GridSizeEnum", "Large")
        for vector_name in ("LinearVelocity", "AngularVelocity"):
            if not all(math.isfinite(x) for x in _vec(grid.find("{*}" + vector_name))):
                issues.append(f"Invalid grid {vector_name}")
        groups = grid.find("{*}BlockGroups")
        if groups is not None and len(groups):
            issues.append("SE1 block groups have no implemented native migration")
        positions = set()
        for block in safe_xml.iter_blocks_in_grid(grid):
            total += 1
            ident = BlockIdentity.from_block(block)
            target = catalog.by_se1.get(ident.subtype_id) if ident.type_id == "CubeBlock" else None
            if target is None:
                unsupported[ident.key] += 1
                continue
            if size != ("Small" if target.cell_size == 0.5 else "Large"):
                issues.append(f"{ident.key} does not belong on a {size} grid")
            position = tuple(_vec(block.find("{*}Min")))
            if not all(math.isfinite(v) and v == int(v) for v in position) or position in positions:
                issues.append(f"Invalid or overlapping SE1 block position: {position}")
            positions.add(position)
            orient = block.find("{*}BlockOrientation")
            fwd = orient.get("Forward", "Forward") if orient is not None else "Forward"
            up = orient.get("Up", "Up") if orient is not None else "Up"
            if fwd not in BASE6 or up not in BASE6 or abs(np.dot(BASE6.get(fwd, (0, 0, 0)), BASE6.get(up, (0, 0, 0)))) > 0.1:
                issues.append(f"Invalid block orientation: {fwd}/{up}")
            skin = block.findtext("{*}SkinSubtypeId", "")
            if skin:
                issues.append(f"SE1 skin '{skin}' has no native SE2 material mapping")
            for field_name in ("Owner", "BuiltBy", "MultiBlockId"):
                if block.findtext("{*}" + field_name, "0") not in ("0", "", None):
                    issues.append(f"{ident.key}: {field_name} has no cross-engine identity mapping")
            for field_name in ("ConstructionStockpile", "ComponentContainer"):
                extra = block.find("{*}" + field_name)
                if extra is not None and len(extra):
                    issues.append(f"{ident.key}: nonempty {field_name} cannot be migrated")
            color = _vec(block.find("{*}ColorMaskHSV"), (0.0, -0.8, 0.4))
            if not all(math.isfinite(x) for x in color):
                issues.append(f"{ident.key}: invalid color")
            elif not (0 <= color[0] <= 1 and -0.8 <= color[1] <= 0.2 and -0.45 <= color[2] <= 0.55):
                issues.append(f"{ident.key}: color would be clamped in SE2")
            supported += 1
        skeleton = grid.find("{*}Skeleton")
        if skeleton is not None and len(skeleton):
            issues.append("Deformed SE1 armor bones cannot be migrated losslessly")
    issues.extend(f"{count} unsupported block(s): {key}" for key, count in sorted(unsupported.items()))
    if not total:
        issues.append("Blueprint has no blocks")
    return grids, supported, total, issues


class EngineVersionDetector:
    @classmethod
    def detect_file_format(cls, path: Path) -> BlueprintFormat:
        path = Path(path)
        if path.is_dir():
            for name in ("grid.json", "bp.sbc", "bp.sbcB5"):
                if (path / name).is_file():
                    return cls.detect_file_format(path / name)
            return BlueprintFormat.UNKNOWN
        if not path.is_file():
            return BlueprintFormat.UNKNOWN
        if path.suffix.lower() == ".sbcb5":
            return BlueprintFormat.SE1_SBCB5_BIN
        try:
            if path.suffix.lower() == ".json":
                validate_bundle(json.loads(path.read_text(encoding="utf-8-sig")))
                return BlueprintFormat.SE2_JSON
            if path.suffix.lower() == ".sbc":
                root = safe_xml.parse(path).getroot()
                return BlueprintFormat.SE1_SBC_XML if safe_xml.iter_cube_grids(root) else BlueprintFormat.UNKNOWN
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
            pass
        return BlueprintFormat.UNKNOWN

    @classmethod
    def detect_engine(cls, path: Path) -> GameEngine:
        return (GameEngine.SPACE_ENGINEERS_2 if cls.detect_file_format(path) == BlueprintFormat.SE2_JSON
                else GameEngine.SPACE_ENGINEERS_1)

    @classmethod
    def inspect_compatibility(cls, blueprint_path: Path, *, catalog=None) -> EngineCompatibilityReport:
        path = Path(blueprint_path)
        fmt = cls.detect_file_format(path)
        report = EngineCompatibilityReport(path, cls.detect_engine(path), fmt)
        report.is_se1_compatible = fmt == BlueprintFormat.SE1_SBC_XML
        try:
            native = _catalog(catalog)
            if fmt == BlueprintFormat.SE1_SBC_XML:
                root = safe_xml.parse(_input(path, "bp.sbc")).getroot()
                _, report.supported_blocks, report.total_blocks, report.unsupported_blocks = _preflight(root, native)
                report.se2_migratable = not report.unsupported_blocks
            elif fmt == BlueprintFormat.SE2_JSON:
                payload = json.loads(_input(path, "grid.json").read_text(encoding="utf-8-sig"))
                validate_bundle(payload, native)
                report.is_se2_compatible = True
                report.notes.append("Native EntityBundle and installed definition GUIDs are valid; in-game behavior requires a separate test.")
            else:
                report.notes.append("Unsupported format. Native SE2 blueprints contain grid.json; arbitrary JSON is not an SE2 blueprint.")
            report.catalog_validated = fmt in (BlueprintFormat.SE1_SBC_XML, BlueprintFormat.SE2_JSON)
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
            report.notes.append(str(exc))
        report.notes.append("Migration support: standard cube, slope, corner and inverted-corner armor; light/heavy, large/small. Other blocks and subgrids are explicitly unsupported.")
        return report


def _publish_directory(target: Path, files: dict[str, str]) -> Path:
    """Publish complete outputs only; existing blueprints are never overwritten."""
    target = Path(target)
    if target.exists():
        raise FileExistsError(f"Destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # SE2 watches Blueprint children and can lock a half-written container.
    # Stage beside the watched root, on the same volume, then expose it once.
    stage = Path(tempfile.mkdtemp(prefix=".sebx-", dir=target.parent.parent))
    try:
        for name, text in files.items():
            safe_xml.atomic_write_text(stage / name, text)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    return target


class SE2MigrationBridge:
    @classmethod
    def migrate_se1_to_se2(cls, se1_bp_path: Path, output_dir=None, *, catalog=None):
        source = _input(Path(se1_bp_path), "bp.sbc")
        root = safe_xml.parse(source).getroot()
        native = _catalog(catalog)
        grids, supported, total, issues = _preflight(root, native)
        if issues:
            raise UnsupportedBlueprintError(issues)
        grid = grids[0]
        name = grid.findtext("{*}DisplayName") or source.parent.name
        entity = native.new_grid()
        entity["$ObjectId"] = 0
        entity["DebugName"] = name
        position, rotation = _pose(grid)
        component(entity, WORLD_TRANSFORM_TYPE)["TransformWithEulerHint"] = _transform(position, rotation)
        component(entity, GRID_TYPE)["DisplayName"] = {"RawText": name}
        physics = component(entity, PHYSICS_TYPE)
        physics["MotionType"] = "Static" if grid.findtext("{*}IsStatic", "false").lower() == "true" else "Dynamic"
        for vector_name in ("LinearVelocity", "AngularVelocity"):
            physics[vector_name] = _xyz(_vec(grid.find("{*}" + vector_name)))
        children = component(entity, HIERARCHY_TYPE)["Children"] = []
        source_ids = {"0": grid.findtext("{*}EntityId", "0")}
        for index, block in enumerate(safe_xml.iter_blocks_in_grid(grid), 1):
            ident = BlockIdentity.from_block(block)
            entry = native.by_se1[ident.subtype_id]
            orient = block.find("{*}BlockOrientation")
            fwd = orient.get("Forward", "Forward") if orient is not None else "Forward"
            up = orient.get("Up", "Up") if orient is not None else "Up"
            rot = _quaternion(np.array(orientation_matrix(fwd, up)).T)
            pos = np.array(_vec(block.find("{*}Min"))) * entry.cell_size
            hsv = hsv_offset_to_standard(*_vec(block.find("{*}ColorMaskHSV"), (0.0, -0.8, 0.4)))
            build = float(block.findtext("{*}BuildPercent", "1"))
            health = float(block.findtext("{*}IntegrityPercent", "1"))
            if not 0 <= health <= build <= 1:
                raise UnsupportedBlueprintError([f"Invalid build/integrity values on block {index}"])
            values = [
                {"$Type": CHILD_TRANSFORM_TYPE, "TransformWithEulerHint": _transform(pos, rot)},
                {"$Type": HIERARCHY_TYPE, "Children": []},
                {"$Type": BLOCK_TYPE, "Color": {"Values": {**_xyz(hsv), "W": 1}},
                 "BuildProgress": build, "HealthIntegrity": health, "PreviewOnly": False},
                None,
            ]
            child = {"$ObjectId": index, "Definition": entry.composition,
                     "ObjectBuilders": [{"Key": key, "Value": value}
                                        for key, value in zip(entry.component_keys, values)],
                     "DebugName": f"SEBX_{index}"}
            children.append({"Key": str(uuid.UUID(bytes_le=b'\0' * 8 + (index - 1).to_bytes(8, 'little'))), "Value": child})
            source_ids[str(index)] = block.findtext("{*}EntityId", "0")
        payload = {"$Bundles": native.bundles, "$Type": ENTITY_BUNDLE,
                   "$Value": {"Roots": 1, "Builders": [entity]}}
        validate_bundle(payload, native)
        parts = [int(x) for x in native.bundles["Game2"].split(".")]
        metadata = {"$Bundles": native.bundles,
                    "$Type": "VRage:Keen.VRage.Library.Filesystem.StorageManagers.ContainerInfo" + chr(96) + "1<Game2:Keen.Game2.Client.GameSystems.Blueprints.BlueprintMetadata>",
                    "$Value": {"Meta": {"BaseMetadata": {"Title": name,
                                        "Description": "Converted SE1 armor blueprint", "Tags": [],
                                        "Id": None, "Visiblity": "Private", "IsOwner": True,
                                        "CreatedAt": datetime.now(timezone.utc).isoformat(),
                                        "UpdatedAt": datetime.now(timezone.utc).isoformat(),
                                        "Dependencies": [], "PreviewFilePath": ""},
                                        "GameVersion": parts[0]*1000000 + parts[1]*1000 + parts[2],
                                        "GameBuildNumber": parts[3],
                                        "LastEdited": datetime.now(timezone.utc).isoformat(),
                                        "BlockCount": total, "PCU": total},
                               "AdditionalData": {}}}
        target = Path(output_dir) if output_dir is not None else blueprint_root() / f"SEBX_{source.parent.name}"
        grid_text = json.dumps(payload, indent=2)
        files = {"grid.json": grid_text, ".container-info": json.dumps(metadata, indent=2),
                 "snapshot": json.dumps(native.snapshot(payload), indent=2),
                 "sebx-migration.json": json.dumps({"schema": 1, "source_entity_ids": source_ids,
                                                   "native_sha256": hashlib.sha256(grid_text.encode("utf-8")).hexdigest(),
                                                   "notes": ["Source entity IDs are remapped to native object IDs."]}, indent=2)}
        return _publish_directory(target, files), total, supported

    @classmethod
    def migrate_se2_to_se1(cls, se2_json_path: Path, output_dir=None, *, catalog=None):
        source = _input(Path(se2_json_path), "grid.json")
        native = _catalog(catalog)
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        builders = validate_bundle(payload, native)
        if len(builders) != 1:
            raise UnsupportedBlueprintError(["Native subgrid import is not implemented"])
        entity = builders[0]
        if entity["Definition"] != native.grid_template["Definition"]:
            raise UnsupportedBlueprintError(["Native root is not a supported cube grid"])
        children = component(entity, HIERARCHY_TYPE).get("Children", [])
        issues = []
        entries = []
        for child in children:
            block = child["Value"]
            entry = native.by_composition.get(block["Definition"])
            if entry is None:
                issues.append(f"No SE1 mapping for native composition {block['Definition']}")
            else:
                entries.append((block, entry))
                if component(block, HIERARCHY_TYPE).get("Children"):
                    issues.append("Nested native block children are unsupported")
        sizes = {entry.cell_size for _, entry in entries}
        if len(sizes) != 1:
            issues.append("Mixed 0.5 m and 2.5 m native blocks cannot share one SE1 grid")
        if not entries:
            issues.append("Native blueprint contains no supported blocks")
        for ob in entity.get("ObjectBuilders", []):
            value = ob.get("Value") or {}
            if value.get("Bones"):
                issues.append("Deformed native armor bones cannot be imported losslessly")
            if value.get("Groups"):
                issues.append("Native block groups have no implemented SE1 migration")
        if issues:
            raise UnsupportedBlueprintError(issues)
        physics = component(entity, PHYSICS_TYPE)
        if physics.get("MotionType") not in ("Static", "Dynamic"):
            raise UnsupportedBlueprintError(["Unsupported native physics motion type"])
        source_ids = {}
        sidecar = source.parent / "sebx-migration.json"
        if sidecar.is_file():
            try:
                migration = json.loads(sidecar.read_text(encoding="utf-8"))
                if migration.get("native_sha256") == hashlib.sha256(source.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest():
                    source_ids = {k: str(int(v)) for k, v in migration.get("source_entity_ids", {}).items()
                                  if -(2**63) <= int(v) < 2**63}
            except (OSError, ValueError, TypeError, AttributeError):
                source_ids = {}
        id_note = ("Original SE1 entity IDs restored from hash-matched migration metadata." if source_ids
                   else "SE1 entity IDs generated; no matching source-ID metadata. Native object IDs are recorded below.")
        root = ET.Element("Definitions")
        ship = ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint")
        name = component(entity, GRID_TYPE).get("DisplayName", {}).get("RawText", source.parent.name)
        ET.SubElement(ship, "Id", Type="MyObjectBuilder_ShipBlueprintDefinition", Subtype=name)
        ET.SubElement(ship, "DisplayName").text = name
        grid = ET.SubElement(ET.SubElement(ship, "CubeGrids"), "CubeGrid")
        ET.SubElement(grid, "EntityId").text = source_ids.get(str(entity["$ObjectId"]), "1000000")
        ET.SubElement(grid, "DisplayName").text = name
        ET.SubElement(grid, "GridSizeEnum").text = "Small" if next(iter(sizes)) == 0.5 else "Large"
        ET.SubElement(grid, "IsStatic").text = str(physics["MotionType"] == "Static").lower()
        for vector_name in ("LinearVelocity", "AngularVelocity"):
            values = physics.get(vector_name, {a: 0 for a in "XYZ"})
            if not all(math.isfinite(float(values[a])) for a in "XYZ"):
                raise UnsupportedBlueprintError([f"Invalid native {vector_name}"])
            ET.SubElement(grid, vector_name, {a.lower(): str(values[a]) for a in "XYZ"})
        pose = component(entity, WORLD_TRANSFORM_TYPE)["TransformWithEulerHint"]["Transform"]
        matrix = _rotation(pose["Orientation"])
        pao = ET.SubElement(grid, "PositionAndOrientation")
        for tag, vec in (("Position", [pose["Position"][a] for a in "XYZ"]), ("Forward", -matrix[:, 2]), ("Up", matrix[:, 1])):
            vec_node = ET.SubElement(pao, tag)
            for axis, value in zip("XYZ", vec):
                ET.SubElement(vec_node, axis).text = str(float(value))
        blocks = ET.SubElement(grid, "CubeBlocks")
        seen = set()
        for index, (child, entry) in enumerate(entries, 1):
            transform = component(child, CHILD_TRANSFORM_TYPE)["TransformWithEulerHint"]["Transform"]
            coords = np.array([float(transform["Position"][a]) / entry.cell_size for a in "XYZ"])
            if not np.allclose(coords, np.round(coords), atol=1e-5):
                raise UnsupportedBlueprintError([f"Native block {index} is not aligned to the SE1 grid"])
            cell = tuple(int(round(v)) for v in coords)
            if cell in seen:
                raise UnsupportedBlueprintError(["Native blocks overlap on the SE1 grid"])
            seen.add(cell)
            matrix = _rotation(transform["Orientation"])
            directions = []
            for vector in (-matrix[:, 2], matrix[:, 1]):
                match = next((name for name, direction in BASE6.items() if np.allclose(vector, direction, atol=1e-5)), None)
                if match is None:
                    raise UnsupportedBlueprintError(["Non-orthogonal native block rotation cannot be represented in SE1"])
                directions.append(match)
            native_block = component(child, BLOCK_TYPE)
            if native_block.get("PreviewOnly"):
                raise UnsupportedBlueprintError(["Preview-only native blocks cannot be imported"])
            build = float(native_block.get("BuildProgress", 1))
            health = float(native_block.get("HealthIntegrity", 1))
            color = native_block["Color"]["Values"]
            if not (0 <= health <= build <= 1 and all(0 <= float(color[a]) <= 1 for a in "XYZ")
                    and float(color.get("W", 1)) == 1):
                raise UnsupportedBlueprintError(["Native health, build progress or color is not representable in SE1"])
            cube = ET.SubElement(blocks, "MyObjectBuilder_CubeBlock")
            BlockIdentity("CubeBlock", entry.se1_subtype).apply(cube)
            ET.SubElement(cube, "EntityId").text = source_ids.get(str(child["$ObjectId"]), str(1000000 + index))
            ET.SubElement(cube, "Min", dict(zip("xyz", map(str, cell))))
            ET.SubElement(cube, "BlockOrientation", Forward=directions[0], Up=directions[1])
            color = native_block["Color"]["Values"]
            ET.SubElement(cube, "ColorMaskHSV", x=str(color["X"]), y=str(color["Y"] - 0.8), z=str(color["Z"] - 0.45))
            ET.SubElement(cube, "BuildPercent").text = str(native_block.get("BuildProgress", 1))
            ET.SubElement(cube, "IntegrityPercent").text = str(native_block.get("HealthIntegrity", 1))
        target = Path(output_dir) if output_dir is not None else source.parent.parent / f"SE1_{source.parent.name}"
        xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
        migration_report = {"schema": 1, "notes": [id_note], "unsupported_blocks": [],
                            "native_object_ids": [entity["$ObjectId"]] + [child["$ObjectId"] for child, _ in entries]}
        return _publish_directory(target, {"bp.sbc": xml, "sebx-migration.json": json.dumps(migration_report, indent=2)}), len(entries), len(entries)
