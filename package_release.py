"""
Release Packaging Script for Space Engineers Tactical Command (SE Block Exchanger).
Builds a clean distribution package containing ONLY runtime files and executable.
Excludes all test files, dev scripts, and internal documentation.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from version import __version__


def create_release_package(output_dir: Path = Path("dist")) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    package_name = f"SE_Tactical_Command_v{__version__}_Portable"
    stage_dir = output_dir / package_name
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    runtime_dirs = ["mappings", "pb_doctor", "subgrid_engine", "workshop_sync", "ui", "data", "profiles"]
    runtime_files = [
        "main.py",
        "gui_standalone.py",
        "se_armor_replacer.py",
        "blueprint_converter.py",
        "blueprint_scanner.py",
        "blueprint_analytics.py",
        "mapping_profiles.py",
        "app_settings.py",
        "update_checker.py",
        "safe_xml.py",
        "engine_compat.py",
        "version.py",
        "requirements.txt",
        "launch.bat",
        "SE Tactical Command.bat",
        "Create Desktop Shortcut.bat",
        "create_desktop_shortcut.ps1",
        "README.md",
        "RELEASE_NOTES.md",
        "LICENSE",
        "app_icon.ico",
        "app_icon.png",
    ]

    for d in runtime_dirs:
        src = Path(d)
        if src.exists():
            shutil.copytree(src, stage_dir / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

    for f in runtime_files:
        src = Path(f)
        if src.exists():
            shutil.copy2(src, stage_dir / f)

    for exe in output_dir.glob("*.exe"):
        shutil.copy2(exe, stage_dir / exe.name)

    zip_path = output_dir / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(stage_dir):
            for file in files:
                file_path = Path(root) / file
                archive_name = file_path.relative_to(stage_dir)
                zf.write(file_path, archive_name)

    shutil.rmtree(stage_dir)
    print(f"[PACKAGE] Successfully built clean release archive: {zip_path}")
    return zip_path


if __name__ == "__main__":
    create_release_package()
