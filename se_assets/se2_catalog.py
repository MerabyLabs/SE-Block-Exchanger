"""Read native VRAGE3 definition GUIDs and prefab templates from an SE2 install.

Templates stay in the user's game installation. Nothing in this module invents
block IDs or ships game models, textures, or prefab data with the application.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

import safe_xml
from se_assets.install_locator import _steam_library_roots

ENTITY_BUNDLE = "VRage:Keen.VRage.Core.Game.Systems.EntityBundle"
SNAPSHOT_TYPE = "VRage:Keen.VRage.DCS.Serialization.EOBUpdateContext"
COMPOSITE_TYPE = "VRage:Keen.VRage.DCS.Definitions.EntityCompositeDefinitionObjectBuilder"
BLOCK_TYPE = "Game2:Keen.Game2.Simulation.WorldObjects.CubeBlocks.CubeBlockObjectBuilder"
HIERARCHY_TYPE = "VRage:Keen.VRage.Core.Game.Components.HierarchyComponentObjectBuilder"
CHILD_TRANSFORM_TYPE = "VRage:Keen.VRage.Core.Game.Components.ChildTransformComponentObjectBuilder"
WORLD_TRANSFORM_TYPE = "VRage:Keen.VRage.Core.Game.Components.WorldTransformComponentObjectBuilder"
GRID_TYPE = "Game2:Keen.Game2.Simulation.WorldObjects.CubeGrids.CubeGridObjectBuilder"
PHYSICS_TYPE = "Game2:Keen.Game2.Simulation.WorldObjects.CubeGrids.Physicss.GridPhysicsObjectBuilder"
ANALYTICS_TYPE = "Game2:Keen.Game2.Game.EntityComponents.Analytics.AnalyticsIdsObjectBuilder"

# Grid_Server.def contains every server-side component, including optional
# runtime collectors that are not serialized into a normal blueprint.  The
# list below is the component topology emitted by the installed 2.4 blueprint
# writer (the GUIDs are resolved from the installed composite definition, not
# invented by SEBX).  Keeping this topology is important: snapshot validation
# requires the serialized slot list to match the entity bundle exactly.
SERIALIZED_GRID_COMPONENTS = (
    "5a78c226-a5e7-5ea7-dd66-9dbde3bd074a",
    "f6895965-89a7-9ae4-eb64-ae48d362a505",
    "8a574b31-1134-d8a3-dc46-a93ad3c3f572",
    "9cb8c054-1da5-4caa-82e4-3ff703f7bb24",
    "f13d4b13-9d5e-3215-b602-e7ff1280448a",
    "8c57db5e-f174-3607-04f1-46ff6fa94ea1",
    "f4d99d3b-3698-a02c-bf7e-bc8d76b29768",
    "94e1c061-819e-c80b-d4f9-c6e0770e3452",
    "ead556bc-dcde-4c46-aa5e-2d6ce3143156",
    "863d212f-e36d-ee86-6f8a-3ea98668276f",
    "f0d091d0-be43-d91c-cfe6-7b549e9cc641",
    "b1c7052b-469b-2ae4-af92-d63c3ca03d48",
    "1e9812b9-4a0e-1429-a00b-0850d2abd4e4",
    "8716df7d-1a0a-16d0-3690-3b60709cd1f3",
    "0119b467-d1c3-01a8-916d-493ee953c767",
    "f4bd858b-6dac-3968-f0a2-6614e249dce6",
    "080dbd37-a5bd-3de1-1a07-817c9c877ec6",
    "9750196f-cdbf-f42a-b8ae-45065ff0631e",
    "c1257341-9599-5aa4-5cc5-202dfda5415b",
    "23cc6eca-a550-9a88-8924-48158ba2a1a0",
    "1768da27-19a7-a4d6-b6af-85eddfc7e7ce",
    "75fd2a0a-052e-dace-74f5-3bf9acfdf613",
    "47d2160a-ffc1-47bd-a862-df9482cf88d1",
    "4eecffc1-dd62-4e27-95bf-aa12957ac7f1",
    "1b223759-73ea-4b48-9c34-1a93da84dd23",
    "45d8e833-b9f4-4679-8692-8db01d9232cd",
    "757eb23f-3a2b-4f44-9c72-0c25249206c8",
    "2c9df20a-61ce-4210-8014-581253af6e8a",
    "01420fc4-5850-442e-8023-e73cd08e49c9",
    "ada860f7-db99-4cbb-ab9c-d63b416af189",
    "f8c52503-03ea-488a-95e4-bd9a84db352e",
    "cc4a45b8-7ece-4708-9170-3d256b0aa283",
)
EXTRA_SERIALIZED_GRID_COMPONENTS = frozenset({
    "f8c52503-03ea-488a-95e4-bd9a84db352e",
    "cc4a45b8-7ece-4708-9170-3d256b0aa283",
})

# Explicitly supported shape correspondences. Additional shapes/functions need
# geometry and in-game acceptance before entering this list.
ARMOR_SHAPES = {"ArmorBlock": "Cube", "ArmorSlope": "Slope",
                "ArmorCorner": "Corner", "ArmorCornerInv": "Inverted Corner"}


def blueprint_root() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "SpaceEngineers2" / "AppData" / "Blueprints"


def find_install(saved: Optional[Path] = None) -> Path:
    candidates = [saved] if saved else []
    if os.getenv("SEBX_SE2_INSTALL"):
        candidates.insert(0, Path(os.environ["SEBX_SE2_INSTALL"]))
    candidates.extend(p / "steamapps" / "common" / "SpaceEngineers2" for p in _steam_library_roots())
    for candidate in candidates:
        if candidate and (candidate / "GameData/Vanilla/Content/System/Grid/Grid_Server.def").is_file():
            return candidate
    raise FileNotFoundError("Locate an installed Space Engineers 2 game (SEBX_SE2_INSTALL) to validate native blueprints.")


@dataclass(frozen=True)
class NativeArmor:
    se1_subtype: str
    composition: str
    block_definition: str
    component_keys: tuple[str, ...]
    cell_size: float


class SE2Catalog:
    def __init__(self, install: Path):
        self.install = Path(install)
        self.content = self.install / "GameData/Vanilla/Content"
        self.definitions: dict[str, dict[str, Any]] = {}
        self.paths: dict[str, Path] = {}
        self.by_se1: dict[str, NativeArmor] = {}
        self.by_composition: dict[str, NativeArmor] = {}
        self.bundles: dict[str, str] = {}
        self.grid_template: dict[str, Any] = {}

    def load(self, *, progress: Optional[Callable[[int, int], None]] = None,
             use_cache: bool = True) -> "SE2Catalog":
        # The index includes all definitions so validation distinguishes an
        # unknown GUID from a real block that has no implemented SE1 mapping.
        self.definitions.clear()
        self.paths.clear()
        self.by_se1.clear()
        self.by_composition.clear()
        paths = sorted(self.content.rglob("*.def"))
        fingerprint = hashlib.sha256()
        for path in paths:
            stat = path.stat()
            fingerprint.update(f"{path.relative_to(self.content)}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
        digest = fingerprint.hexdigest()
        install_key = hashlib.sha256(str(self.install.resolve()).encode()).hexdigest()[:16]
        cache_base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
        cache = cache_base / "SETacticalCommand" / f"se2-catalog-v1-{install_key}.json"
        cached = None
        if use_cache:
            try:
                candidate = json.loads(cache.read_text(encoding="utf-8"))
                if candidate.get("fingerprint") == digest and candidate.get("schema") == 1:
                    definitions = candidate["definitions"]
                    relative_paths = candidate["paths"]
                    if (isinstance(definitions, dict) and isinstance(relative_paths, dict)
                            and definitions.keys() == relative_paths.keys()
                            and all(isinstance(v, dict) and isinstance(v.get("$Value"), dict)
                                    for v in definitions.values())
                            and all(isinstance(p, str) and not Path(p).is_absolute()
                                    and ".." not in Path(p).parts for p in relative_paths.values())):
                        cached = candidate
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
        if cached:
            self.definitions = cached["definitions"]
            self.paths = {guid: self.content / relative for guid, relative in cached["paths"].items()}
            if progress:
                progress(len(paths), len(paths))
        else:
            def read_definition(path):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8-sig"))
                    value = payload.get("$Value", {})
                    guid = value.get("Guid") if isinstance(value, dict) else None
                    if not isinstance(guid, str):
                        return None
                    # Keep identifiers and validation metadata, not game textures,
                    # models, sounds, or unrelated definition payloads in memory.
                    minimal = {"Guid": guid}
                    if payload.get("$Type") == COMPOSITE_TYPE:
                        minimal.update({k: value[k] for k in ("Components", "TagSlots") if k in value})
                    return guid, path, {"$Type": payload.get("$Type"), "$Value": minimal}
                except (OSError, ValueError, AttributeError):
                    return None
            with ThreadPoolExecutor(max_workers=4, thread_name_prefix="se2-index") as pool:
                for index, result in enumerate(pool.map(read_definition, paths), 1):
                    if result:
                        guid, path, payload = result
                        if guid in self.definitions:
                            raise ValueError(f"Duplicate SE2 definition GUID: {guid}")
                        self.definitions[guid] = payload
                        self.paths[guid] = path
                    if progress and (index % 250 == 0 or index == len(paths)):
                        progress(index, len(paths))
            if use_cache:
                try:
                    safe_xml.atomic_write_text(cache, json.dumps({"schema": 1, "fingerprint": digest,
                        "definitions": self.definitions,
                        "paths": {guid: path.relative_to(self.content).as_posix() for guid, path in self.paths.items()}}))
                except OSError:
                    pass  # A read-only cache directory must not prevent conversion.
        template = json.loads((self.content / "System/Grid/Grid_Server.def").read_text(encoding="utf-8-sig"))
        self.bundles = template["$Bundles"]
        template_entity = template["$Value"]["_entity"]
        # Start from the installed object-builder defaults, then retain only
        # slots the normal blueprint writer persists.  Optional components in
        # Grid_Server.def are valid runtime objects but are not blueprint
        # components and make the snapshot topology unverifiable.
        by_key = {entry["Key"]: entry for entry in template_entity.get("ObjectBuilders", [])}
        serialized = []
        for key in SERIALIZED_GRID_COMPONENTS:
            entry = copy.deepcopy(by_key.get(key, {"Key": key, "Value": None}))
            entry["Key"] = key
            if key == "cc4a45b8-7ece-4708-9170-3d256b0aa283":
                entry["Value"] = {"$Type": ANALYTICS_TYPE, "Id": str(uuid.uuid4())}
            serialized.append(entry)
        self.grid_template = {"Definition": template_entity["Definition"],
                              "ObjectBuilders": serialized}
        if self.grid_template["Definition"] not in self.definitions:
            raise ValueError("SE2 grid composition definition is missing")
        for suffix, shape in ARMOR_SHAPES.items():
            for size, prefix, meters in (("250", "Large", 2.5), ("50", "Small", 0.5)):
                for material in ("Light", "Heavy"):
                    folder = self.content / "Armors" / shape / size / material
                    matches = [guid for guid, path in self.paths.items()
                               if path.parent == folder and path.name.endswith("_ServerComposition.def")]
                    if len(matches) != 1:
                        continue
                    guid = matches[0]
                    definition = self.definitions[guid]
                    components = definition["$Value"].get("Components", {})
                    keys = components.get("Keys", [])
                    block_guid = None
                    for change in components.get("Changed", []):
                        ref = change.get("Value", {}).get("Definition")
                        target = self.definitions.get(ref, {}) if isinstance(ref, str) else {}
                        if target.get("$Type", "").endswith(".CubeBlockDefinitionObjectBuilder"):
                            block_guid = ref
                    if not block_guid or len(keys) != 4:
                        continue
                    subtype = f"{prefix}{'Heavy' if material == 'Heavy' else ''}Block{suffix}"
                    entry = NativeArmor(subtype, guid, block_guid, tuple(keys), meters)
                    self.by_se1[subtype] = entry
                    self.by_composition[guid] = entry
        if not self.by_se1:
            raise ValueError("No supported native SE2 armor definitions found")
        return self

    def new_grid(self) -> dict[str, Any]:
        return copy.deepcopy(self.grid_template)

    def snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Describe serialized component slots for the native EOB migration loader."""
        pending = list(validate_bundle(payload, self))
        snapshots: dict[str, dict[str, Any]] = {}
        while pending:
            entity = pending.pop()
            entries = entity.get("ObjectBuilders", [])
            keys = [entry["Key"] for entry in entries]
            types = [(entry.get("Value") or {}).get("$Type") for entry in entries]
            guid = entity["Definition"]
            value = {"Definition": guid, "Components": keys, "ObjectBuilders": types}
            if guid in snapshots and snapshots[guid] != value:
                raise ValueError(f"Inconsistent serialized component slots for {guid}")
            snapshots[guid] = value
            for entry in entries:
                child = entry.get("Value")
                if isinstance(child, dict) and child.get("$Type") == HIERARCHY_TYPE:
                    pending.extend(item["Value"] for item in child.get("Children", []))
        return {"$Bundles": self.bundles, "$Type": SNAPSHOT_TYPE, "$Value": {"Snapshots": snapshots}}

    def validate_entity(self, entity: dict[str, Any]) -> None:
        guid = entity.get("Definition")
        definition = self.definitions.get(guid, {}) if isinstance(guid, str) else {}
        if definition.get("$Type") != COMPOSITE_TYPE:
            raise ValueError(f"Unknown SE2 entity composition GUID: {guid}")
        components = definition["$Value"].get("Components", {})
        if isinstance(components, dict):
            keys = set(components.get("Keys", []))
        else:
            keys = {c.get("Key", c.get("$Key")) for c in components}
        # Full composites use Key/Value entries; delta definitions use Keys.
        if not keys:
            keys = {c.get("$Value") for c in definition["$Value"].get("TagSlots", [])}
        for entry in entity.get("ObjectBuilders", []):
            if keys and entry.get("Key") not in keys and not (
                    guid == self.grid_template.get("Definition")
                    and entry.get("Key") in EXTRA_SERIALIZED_GRID_COMPONENTS):
                raise ValueError(f"Unknown component slot {entry.get('Key')} for {guid}")


def component(entity: dict[str, Any], type_name: str) -> dict[str, Any]:
    for entry in entity.get("ObjectBuilders", []):
        value = entry.get("Value")
        if isinstance(value, dict) and value.get("$Type") == type_name:
            return value
    raise ValueError(f"Native entity has no {type_name.rsplit('.', 1)[-1]}")


def validate_bundle(payload: dict[str, Any], catalog: Optional[SE2Catalog] = None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("$Type") != ENTITY_BUNDLE or not isinstance(payload.get("$Bundles"), dict):
        raise ValueError("Not a native Space Engineers 2 EntityBundle")
    value = payload.get("$Value", {})
    if not isinstance(value, dict):
        raise ValueError("Invalid native bundle value")
    builders = value.get("Builders")
    roots = value.get("Roots")
    if not isinstance(builders, list) or not isinstance(roots, int) or roots != len(builders) or roots < 1:
        raise ValueError("Invalid native blueprint root count")
    seen: set[int] = set()
    pending = list(builders)
    while pending:
        entity = pending.pop()
        if not isinstance(entity, dict):
            raise ValueError("Invalid native entity")
        object_id = entity.get("$ObjectId")
        if not isinstance(object_id, int) or object_id < 0 or object_id in seen:
            raise ValueError("Native object IDs must be unique nonnegative integers")
        seen.add(object_id)
        entries = entity.get("ObjectBuilders", [])
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise ValueError("Invalid native component entries")
        keys = [entry.get("Key") for entry in entries]
        if any(not isinstance(key, str) for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Native component keys must be unique strings")
        if any(entry.get("Value") is not None and not isinstance(entry["Value"], dict) for entry in entries):
            raise ValueError("Native component values must be objects or null")
        if catalog:
            catalog.validate_entity(entity)
        for entry in entries:
            child = entry.get("Value")
            if isinstance(child, dict) and child.get("$Type") == HIERARCHY_TYPE:
                children = child.get("Children", [])
                if not isinstance(children, list) or not all(isinstance(item, dict) and "Value" in item for item in children):
                    raise ValueError("Invalid native hierarchy children")
                child_keys = [item.get("Key") for item in children]
                if any(not isinstance(key, str) for key in child_keys) or len(set(child_keys)) != len(child_keys):
                    raise ValueError("Native hierarchy keys must be unique strings")
                pending.extend(item["Value"] for item in children)
    return builders
