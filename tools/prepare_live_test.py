"""Prepare isolated live-test AppData and hash-protected copies of selected fixtures."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_settings import AppSettings, SettingsStore
from package_release import sha256
import safe_xml

NAMES = ("Drone - MSG", "MSGhome", "Salvage Drone", "SKP - SPACE DOCK 1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--appdata", type=Path, required=True)
    parser.add_argument("--install", type=Path, required=True)
    parser.add_argument("--empty", action="store_true")
    args = parser.parse_args()
    root = args.appdata.resolve()
    if root.exists():
        raise FileExistsError(f"Choose a new isolated AppData root: {root}")
    SettingsStore(root / "SEBlockExchanger/settings.json").save(AppSettings(
        auto_check_updates=False, appearance_mode="Dark", space_engineers_install=str(args.install)))
    evidence = {"appdata": str(root), "source_blueprints": []}
    if not args.empty:
        library = root / "SpaceEngineers/Blueprints/local"
        for name in NAMES:
            source = args.source / name
            if not (source / "bp.sbc").is_file():
                raise FileNotFoundError(source / "bp.sbc")
            digest = sha256(source / "bp.sbc")
            target = library / name
            shutil.copytree(source, target)
            if sha256(target / "bp.sbc") != digest:
                raise ValueError(f"Fixture copy failed hash verification: {name}")
            evidence["source_blueprints"].append({"name": name, "source": str(source),
                "copy": str(target), "sha256": digest, "bytes": (source / "bp.sbc").stat().st_size})
    safe_xml.atomic_write_text(root / "fixture-manifest.json", json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
