"""Compile/import the shipped runtime and validate every enabled baseline mapping."""
from pathlib import Path
import importlib
import json
import py_compile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from package_release import RUNTIME_DIRS, RUNTIME_FILES
from mappings.registry import build_registry
from se_assets.compatibility import baseline_catalog, validate_mapping
from version import __version__


def main():
    paths = [ROOT / f for f in RUNTIME_FILES if f.endswith(".py")]
    paths += [p for d in RUNTIME_DIRS for p in (ROOT / d).rglob("*.py")]
    for path in paths:
        py_compile.compile(str(path), doraise=True)
    for name in ("gui_standalone", "ui.app", "blueprint_converter", "engine_compat", "se_render.viewport"):
        importlib.import_module(name)
    catalog = baseline_catalog()
    registry = build_registry(catalog=catalog)
    counts = {}
    for category in registry.list_categories():
        name = category.name
        _, issues = validate_mapping(category.pairs, catalog)
        if issues:
            raise ValueError(f"Invalid enabled mapping in {name}: {issues}")
        counts[name] = len(category.pairs)
    print(json.dumps({"version": __version__, "compiled_files": len(paths),
                      "catalog_definitions": len(catalog.definitions), "valid_pairs": counts}, indent=2))


if __name__ == "__main__":
    main()
