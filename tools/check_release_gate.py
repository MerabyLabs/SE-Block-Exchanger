"""Reject publication until every required acceptance check has evidence."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from version import __version__

REQUIRED = {"unified_python311", "unified_python312", "catalog_validation", "live_app_and_3d",
            "source_blueprint_hashes", "clean_windows_package", "se2_single_grid_open_save_reopen",
            "se2_subgrid_diagnostics"}


def validate_gate(data):
    errors = []
    if data.get("version") != __version__:
        errors.append("Acceptance version does not match version.py")
    if data.get("status") != "APPROVED" or data.get("blockers"):
        errors.append("Release is on hold")
    for key in sorted(REQUIRED):
        check = data.get("checks", {}).get(key, {})
        if check.get("status") != "PASS" or not check.get("evidence"):
            errors.append(f"Missing passing evidence: {key}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("release_acceptance.json"))
    args = parser.parse_args()
    errors = validate_gate(json.loads(args.manifest.read_text(encoding="utf-8")))
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Release {__version__} acceptance approved")


if __name__ == "__main__":
    main()
