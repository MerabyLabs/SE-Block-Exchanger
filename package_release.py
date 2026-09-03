"""Build a complete, non-overwriting portable archive from an explicit source root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from version import __version__, __channel__

RUNTIME_DIRS = ("mappings", "pb_doctor", "subgrid_engine", "workshop_sync", "ui", "data",
                "profiles", "se_assets", "se_render")
RUNTIME_FILES = (
    "main.py", "gui_standalone.py", "se_armor_replacer.py", "blueprint_converter.py",
    "blueprint_scanner.py", "blueprint_analytics.py", "blueprint_document.py", "blueprint_edit.py",
    "mapping_profiles.py", "app_settings.py", "update_checker.py", "safe_xml.py", "engine_compat.py",
    "resource_paths.py", "runtime_selftest.py", "version.py", "requirements.txt", "launch.bat",
    "SE Tactical Command.bat", "Create Desktop Shortcut.bat", "create_desktop_shortcut.ps1",
    "README.md", "INSTALL.md", "COMPATIBILITY.md", "RELEASE_NOTES.md", "release_acceptance.json",
    "LICENSE", "logo.png",
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_release_package(output_dir: Path = Path("dist"), *, source_root: Path | None = None,
                           require_exe: bool = True) -> Path:
    source = (source_root or Path(__file__).resolve().parent).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f"SE_Tactical_Command_v{__version__}_Portable"
    target = output / f"{name}.zip"
    checksum = output / f"{name}.zip.sha256"
    if target.exists() or checksum.exists():
        raise FileExistsError(f"Release artifact already exists: {target}")
    executable = output / f"SE_Tactical_Command_v{__version__}.exe"
    if require_exe and not executable.is_file():
        raise FileNotFoundError(f"Build the matching executable first: {executable}")
    missing = [p for p in (*RUNTIME_DIRS, *RUNTIME_FILES) if not (source / p).exists()]
    if missing:
        raise FileNotFoundError("Incomplete runtime source: " + ", ".join(missing))
    with tempfile.TemporaryDirectory(prefix="sebx-package-", dir=output) as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        for directory in RUNTIME_DIRS:
            shutil.copytree(source / directory, stage / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        for filename in RUNTIME_FILES:
            shutil.copy2(source / filename, stage / filename)
        for filename in ("app_icon.ico", "app_icon.png"):
            if (source / filename).is_file():
                shutil.copy2(source / filename, stage / filename)
        if executable.is_file():
            shutil.copy2(executable, stage / executable.name)
        files = sorted(p for p in stage.rglob("*") if p.is_file())
        manifest = {"version": __version__, "channel": __channel__, "executable": executable.is_file(),
                    "files": {p.relative_to(stage).as_posix(): sha256(p) for p in files}}
        (stage / "BUILD-MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        archive = Path(temporary) / target.name
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(stage.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(stage).as_posix())
        if target.exists():
            raise FileExistsError(target)
        archive.rename(target)
    with checksum.open("x", encoding="ascii") as stream:
        stream.write(f"{sha256(target)}  {target.name}\n")
    print(f"[PACKAGE] {target}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--source-only", action="store_true", help="For CI integrity testing; not an executable release")
    options = parser.parse_args()
    create_release_package(options.output, require_exe=not options.source_only)
