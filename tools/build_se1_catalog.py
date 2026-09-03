"""Rebuild the distributable SE1 metadata snapshot from an installed game.

Only definition identifiers, dimensions and numerical costs are exported; no
models, textures, executable code or other game assets are included.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import safe_xml
from se_assets.cube_catalog import CubeBlockCatalog, CATALOG_SCHEMA


def build(install: Path, output: Path) -> dict:
    with tempfile.TemporaryDirectory() as scratch:
        catalog = CubeBlockCatalog(Path(scratch) / "catalog.json").load(install, force=True)
    if not catalog.definitions:
        raise ValueError("No SE1 block definitions found")
    masses = {}
    digest = hashlib.sha256()
    for path in sorted((install / "Content" / "Data").rglob("*.sbc")):
        digest.update(path.read_bytes())
        if path.name != "Components.sbc":
            continue
        root = safe_xml.parse(path).getroot()
        for component in root.findall("./{*}Components/*"):
            subtype = component.findtext("./{*}Id/{*}SubtypeId")
            if subtype:
                masses[subtype] = float(component.findtext("{*}Mass", "0"))
    blocks = []
    for definition in sorted(catalog.definitions.values(), key=lambda d: d.key):
        item = asdict(definition)
        item.pop("model_path")
        item.pop("model_offset")
        blocks.append(item)
    payload = {
        "schema": CATALOG_SCHEMA,
        "game": "Space Engineers 1",
        "version": "1.210.014",
        "steam_build": "24675677",
        "definition_sha256": digest.hexdigest(),
        "component_masses": masses,
        "definitions": blocks,
    }
    safe_xml.atomic_write_text(output, json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/se1_catalog.json"))
    args = parser.parse_args()
    data = build(args.install, args.output)
    print(f"Exported {len(data['definitions'])} definitions to {args.output}")
