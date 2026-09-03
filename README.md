# Space Engineers Tactical Command (SE Block Exchanger)

A desktop blueprint inspection and conversion tool by Meraby Labs.

**v4.0.0 is an unreleased candidate.** SE2 native acceptance is a release blocker;
do not treat experimental export as game-certified compatibility. See
[compatibility and limitations](COMPATIBILITY.md) and [release notes](RELEASE_NOTES.md).

## What v4 changes

- Identity-aware, catalog-validated SE1 conversions, including empty default subtypes.
- 116 light/heavy armor pairs, plus supported DLC, weapon and Prototech replacements.
  Unsafe or unavailable pairs are disabled with diagnostics.
- Converted copies are staged atomically; existing destinations are never overwritten.
  Undo removes only unchanged copies created during the current session.
- Responsive Subgrids 3D preview with orbit, zoom, isolate, dissection, shell and reset
  controls. Large scenes use explicitly reported preview simplification.
- Shared blueprint documents, background loading, XML inspection, selective exchange,
  analytics with catalog coverage, profiles, PB Doctor and Workshop tools.
- CustomTkinter 6.x and complete renderer/data packaging.
- Experimental native SE2 single-grid armor migration, with installed GUID validation
  and explicit unsupported/loss diagnostics. No invented JSON manifest or armor fallback.

The SE1 baseline is **1.210.014**. Experimental SE2 testing targets **2.4.0.95**.
Unknown costs are partial, not authoritative totals; PB Doctor is static advice, not
the game's C# compiler. Full functional/modded/subgrid SE2 migration is not implemented.

## Run from source

Use Python **3.11 or 3.12** in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe gui_standalone.py
```

SEBX discovers `%APPDATA%\SpaceEngineers\Blueprints\local`; use Browse to choose
another root. A missing root produces a nonblocking empty state. Select a blueprint,
inspect its tabs, and choose conversion categories in the Convert sidebar.
The original blueprint remains unchanged; output is a separately named folder.

`Ctrl+O`: browse root; `Ctrl+R`: convert; `Ctrl+Z`: undo; `F5`: refresh.

## Candidate packaging

`build_exe.bat` uses the shared PyInstaller specification and creates
`SE_Tactical_Command_v4.0.0.exe` plus `SE_Tactical_Command_v4.0.0_Portable.zip`.
The archive includes a file-hash manifest and a separate SHA-256 checksum. These
names describe build outputs, not a claim that v4 has been published.

Published versions are on [GitHub Releases](https://github.com/MerabyLabs/SE-Block-Exchanger/releases).
See [INSTALL](INSTALL.md) for setup, shortcuts and troubleshooting. The release
workflow refuses publication unless the acceptance manifest passes.

## Validation

```powershell
python tools/check_runtime.py
python -m pytest -q
python tools/check_package.py
```

CI runs the complete legacy and v4 suites on Python 3.11/3.12, Windows and Linux,
with Ruff, core/renderer mypy, import/compile and catalog/package checks. Live Windows
and native SE2 results remain separate acceptance gates.

## License

Free for personal, non-commercial use under [LICENSE](LICENSE). Commercial use
requires a separate license; redistribution rights are governed by that file.
Space Engineers is a trademark of Keen Software House. This fan-made tool is not
affiliated with Keen Software House.

(c) 2025–2026 Meraby Labs.
