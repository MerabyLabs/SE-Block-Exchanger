# Install SE Tactical Command v4.0.0

This v4 build is a **release candidate**. Read [COMPATIBILITY](COMPATIBILITY.md)
before using experimental SE2 migration. Do not tag/publish until native acceptance passes.

## Windows portable executable

When a verified build is available, extract `SE_Tactical_Command_v4.0.0_Portable.zip`
to a writable folder and run `SE_Tactical_Command_v4.0.0.exe`. Python is not required
for the executable. Never run an executable directly from inside its ZIP archive.

Check the archive/executable hash against the accompanying `SHA256SUMS.txt` or
`.sha256` file with `Get-FileHash -Algorithm SHA256`. The portable archive also has
`BUILD-MANIFEST.json` with the checksums of its runtime files.

`Create Desktop Shortcut.bat` creates the standard Desktop shortcut. To test or use
a separate shortcut without replacing an existing one:

```powershell
powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1 -TargetFolder "D:\Apps\SEBX" -TargetPath "D:\Apps\SEBX\SE_Tactical_Command_v4.0.0.exe" -ShortcutPath "D:\Apps\SEBX\SEBX v4 Test.lnk"
```

## Source installation

Python **3.11 and 3.12** are the validated release targets. Other Python versions
are not part of this release's acceptance matrix.

```powershell
git clone https://github.com/MerabyLabs/SE-Block-Exchanger.git
cd SE-Block-Exchanger
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe gui_standalone.py
```

Dependencies include CustomTkinter `>=6,<7`, NumPy, ModernGL, Pillow and defusedxml.
The accelerated 3D preview needs an OpenGL 3.3-capable driver. On Linux, Tk and a
working display are required; CI uses Xvfb for UI tests.

## Blueprint and game locations

- SE1 input root: `%APPDATA%\SpaceEngineers\Blueprints\local`.
- Native SE2 blueprint root: `%APPDATA%\SpaceEngineers2\AppData\Blueprints`.
- Choose a different SE1 root with Browse or `Ctrl+O`; recent roots are retained.
- Locate the SE1 installation in the app for game asset previews and runtime catalog
  validation. SE2 validation requires an installed game; `SEBX_SE2_INSTALL` can
  supply its root. No game assets are shipped in SEBX.

Missing blueprint folders do not block startup. Create a blueprint in the game or
choose a folder containing blueprint subfolders with `bp.sbc` files.

## Safe conversion

Inspect the blueprint, select categories or open Selective Exchange, and create a
new converted copy. Existing output names are refused. Keep backups; undo is only
for unchanged copies made by the current SEBX session. Files subsequently edited
by the game or another program are retained.

Grid rescaling supports single armor grids only. Prototech and DLC operations do
not convert every named block: unsupported builder types and footprints are excluded.
Native SE2 conversion currently supports a small armor subset, not functional ships.
An installed-catalog pass is not an in-game acceptance pass.

## Diagnostics and building

```powershell
python gui_standalone.py --version
python gui_standalone.py --self-test artifacts/runtime-selftest.json
python tools/check_runtime.py
python -m pytest -q
python tools/check_package.py
python -m PyInstaller --noconfirm --clean SE_Tactical_Command.spec
python package_release.py
```

The self-test checks bundled data, imports and shader compilation without opening
user blueprints. It is also available on the packaged executable. Build from a
clean checkout and use a fresh output directory; packaging never overwrites an
existing archive. `python tools/check_release_gate.py` must pass before publication.
