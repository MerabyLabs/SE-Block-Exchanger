"""Create authored native SE2 smoke-test blueprints using the installed catalog.

This verifies serialization only. Opening/pasting/saving in the game is a
separate acceptance step and is never reported as passed by this script.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_compat import SE2MigrationBridge
from se_assets.se2_catalog import SE2Catalog, find_install
from tests.native_fixtures import armor_blueprint
import safe_xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, default=Path("artifacts/native-se2"))
    parser.add_argument("--name-prefix", default="SEBX_v4_Acceptance")
    args = parser.parse_args()
    catalog = SE2Catalog(find_install()).load(progress=lambda done, total:
        print(f"SE2 catalog: {done}/{total}", flush=True) if done % 2000 == 0 or done == total else None)
    report = {"definition_count": len(catalog.definitions), "supported_variants": len(catalog.by_se1),
              "in_game_acceptance": "NOT_RUN", "blueprints": []}
    for size in ("Large", "Small"):
        name = f"{args.name_prefix}_{size}"
        source = armor_blueprint(args.evidence / "source" / name, size, all_shapes=True)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        destination, total, converted = SE2MigrationBridge.migrate_se1_to_se2(source, args.output / name, catalog=catalog)
        returned, _, _ = SE2MigrationBridge.migrate_se2_to_se1(destination, args.evidence / "roundtrip" / name, catalog=catalog)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        report["blueprints"].append({"size": size, "blocks": total, "converted": converted,
                                     "output": str(destination), "roundtrip": str(returned),
                                     "sha256": hashlib.sha256((destination / "grid.json").read_bytes()).hexdigest()})
    safe_xml.atomic_write_text(args.evidence / "serialization-report.json", json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
