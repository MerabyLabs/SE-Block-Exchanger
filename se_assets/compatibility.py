"""Catalog-backed SE1 mapping validation. Unknown targets never reach a writer."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Dict, Mapping, Optional

from resource_paths import resource_path
from se_assets.block_identity import BlockIdentity, normalize_type
from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog


@lru_cache(maxsize=1)
def baseline_catalog() -> CubeBlockCatalog:
    path = resource_path("data", "se1_catalog.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    catalog = CubeBlockCatalog()
    catalog.fingerprint = payload["definition_sha256"]
    for item in payload["definitions"]:
        raw = dict(item)
        raw["dlc"] = tuple(raw.get("dlc", []))
        definition = BlockDefinition(**raw, model_path="", model_offset=(0.0, 0.0, 0.0))
        catalog.definitions[definition.key] = definition
        if definition.subtype_id:
            catalog.by_subtype[definition.subtype_id] = definition
    return catalog


def conversion_catalog(install: Optional[Path] = None) -> CubeBlockCatalog:
    """Validate against the installed game when available, otherwise the baseline."""
    from se_assets.install_locator import resolve_install
    if os.getenv("SEBX_SE1_CATALOG") == "baseline":
        return baseline_catalog()
    if install is None:
        from app_settings import SettingsStore
        settings = SettingsStore().load()
        status = resolve_install(os.getenv("SEBX_SE1_INSTALL") or settings.space_engineers_install,
                                 allow_detect=not settings.space_engineers_cleared)
        install = status.path
    if install is None:
        return baseline_catalog()
    # load() checks definition timestamps, including game/mod updates.
    return CubeBlockCatalog().load(install)


def resolve_token(token: str, catalog: CubeBlockCatalog) -> Optional[BlockDefinition]:
    if "/" in token:
        type_id, subtype = token.split("/", 1)
        return catalog.get_exact(normalize_type(type_id), subtype)
    matches = [d for d in catalog.definitions.values() if d.subtype_id == token]
    if len(matches) == 1:
        return matches[0]
    # Legacy default-type tokens (e.g. Cockpit) are read compatibly, but writes
    # always use the resolved empty subtype and concrete object-builder type.
    return catalog.get_exact(token, "") if not matches else None


@dataclass(frozen=True)
class MappingIssue:
    source: str
    target: str
    reason: str


def validate_pair(source: str, target: str, catalog: CubeBlockCatalog) -> Optional[str]:
    before, after = resolve_token(source, catalog), resolve_token(target, catalog)
    if before is None:
        return "Source definition is missing or ambiguous"
    if after is None:
        return "Target definition is missing or ambiguous"
    if not after.public:
        return "Target is not a public buildable definition"
    if before.type_id != after.type_id:
        return "Object-builder type changes require an explicit field migration"
    if before.cube_size != after.cube_size:
        return "Target uses a different grid size"
    if before.size != after.size:
        return "Target footprint differs; automatic resizing is unsupported"
    return None


def validate_mapping(mapping: Mapping[str, str], catalog: CubeBlockCatalog):
    valid: Dict[str, str] = {}
    issues = []
    for source, target in mapping.items():
        reason = validate_pair(source, target, catalog)
        if reason:
            issues.append(MappingIssue(source, target, reason))
        else:
            valid[source] = target
    return valid, issues


def compile_mapping(mapping: Mapping[str, str], catalog: CubeBlockCatalog):
    valid, issues = validate_mapping(mapping, catalog)
    compiled: Dict[BlockIdentity, BlockIdentity] = {}
    for source, target in valid.items():
        before, after = resolve_token(source, catalog), resolve_token(target, catalog)
        assert before is not None and after is not None
        compiled[BlockIdentity(before.type_id, before.subtype_id)] = BlockIdentity(after.type_id, after.subtype_id)
    return compiled, issues
