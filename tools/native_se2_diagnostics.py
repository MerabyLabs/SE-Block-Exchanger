"""Record explicit native-SE2 diagnostics for multi-grid SE1 fixtures.

This tool performs read-only preflight.  It deliberately does not create a
native output when a blueprint contains subgrids or unsupported blocks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_compat import EngineVersionDetector
from se_assets.se2_catalog import SE2Catalog, find_install
import safe_xml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="SE1 blueprint root containing named folders")
    parser.add_argument("--name", action="append", required=True,
                        help="Blueprint folder name; may be repeated")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = SE2Catalog(find_install()).load()
    reports = []
    for name in args.name:
        path = args.root / name
        report = EngineVersionDetector.inspect_compatibility(path, catalog=catalog)
        reports.append({"name": name, "path": str(path), "format": report.detected_format.value,
                        "catalog_validated": report.catalog_validated,
                        "se2_migratable": report.se2_migratable,
                        "supported_blocks": report.supported_blocks,
                        "total_blocks": report.total_blocks,
                        "unsupported_blocks": report.unsupported_blocks,
                        "notes": report.notes})
    result = {"catalog_definitions": len(catalog.definitions), "passed": bool(reports) and all(
        r["catalog_validated"] and not r["se2_migratable"] and any("one grid" in note.lower()
        for note in r["notes"] + r["unsupported_blocks"]) for r in reports), "blueprints": reports}
    safe_xml.atomic_write_text(args.output, json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("Native SE2 subgrid diagnostics did not fail closed")


if __name__ == "__main__":
    main()
