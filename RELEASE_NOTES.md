# Release Notes

## v3.2.0 (2026-08-29)

Space Engineers Block Exchanger (Tactical Command) for Windows. Convert and analyse `.sbc` blueprints. In the GUI, **Convert writes a new copy**; the original ship is not overwritten.

A Meraby Labs product. Free for personal, non-commercial use. Commercial use requires a license. See LICENSE. Not affiliated with or endorsed by Keen Software House.

### Desktop converter
- Converter window is a product flow: pick a ship, see a live before/after, then convert a copy. Sentence-case labels, readable 15–17pt type, grouped category names, and a Convert button that states how many blocks will change.
- Selecting a blueprint opens the live preview automatically.
- Armor before/after counts only use armor conversions. Enabling thrusters, DLC substitution, or other categories no longer inflates or goes negative on the armor totals.
- Convert stays disabled and the “Will convert” chip clears as soon as you change categories or direction, then comes back from a fresh dry-run so you cannot convert against stale scanner counts.
- Clearing the selection no longer leaves Convert stuck on “Updating conversion counts…”.
- Empty toast overlay no longer paints a solid box over Profiles, Changelog, Rescan, and the control panel. The overlay shows only while a toast is visible.
- Stays on CustomTkinter 5.x.

### Subgrids map
- Subgrids tab lists CubeGrid hierarchy as a clickable tree and draws a 2D voxel map from `Min` coordinates, including `TopGridId` parent/child links.
- Clicking a rotor, turret, or other subgrid isolates that grid; redraw and Fit use that grid’s bounds so it is not left off-center and tiny.
- The map refreshes after the tab is shown, including single-grid ships (no empty black panel). Reopening the tab does not rebuild the map if the ship has not changed.
- The main hull is chosen by block count, not XML order.
- Hierarchy painting no longer collides with CustomTkinter’s internal redraw (the Subgrids tab crashed on startup when that happened).

### Window, tabs, and Windows desktop
- XML, analytics, SE2, and map painting wait until those tabs are shown so switching ships stays responsive.
- Preview work runs on a worker thread; results are applied on the UI thread through a queue (no Tk calls from background threads).
- Each inspect parses the blueprint XML once and reuses it for dry-run conversion, analytics, and the subgrid map.
- Failed XML loads set the XML tab status to the error instead of a normal “Source:” label.
- File → Exit. The Windows title-bar close button quits (drag-and-drop no longer swallows `WM_CLOSE`). The process exits after destroy so `python.exe` does not hang around.
- File → Create desktop shortcut (shortcut targets `launch.bat`). Launchers: `launch.bat` / `main.py` and `launch_gui.bat` / `gui_standalone.py`.
- Native Windows drag-and-drop: Explorer still gets a successful ack if a drop callback fails; the traceback is printed to stderr.

### Import and tools
- **File → Import Workshop / Mod.io blueprint** — paste a Steam Workshop URL or ID, or a Mod.io URL, and copy the ship into `%APPDATA%\SpaceEngineers\Blueprints\local`.
- Workshop folders that only have a fallback `*.sbc` (no `bp.sbc`) still import: the chosen file is copied to `bp.sbc` so the GUI scanner lists the ship. If several `.sbc` files exist, the first name in sorted order is used.
- Import refuses symlink/junction item roots, nested reparse points, and zip members with `C:/`, UNC, or absolute paths. An existing local folder is replaced only when it is a real directory inside the local blueprints root (`rmtree` will not follow a junction out of that folder).
- **Tools → Selective block exchange** — pick individual subtype swaps instead of a whole category.
- **Tools → PB Doctor** — inspect and fix programmable-block C# against the Space Engineers whitelist. Allowed `using` directives (`System`, VRage, and similar) are kept. Forbidden namespaces are stripped, including `using static`, aliases (`using IO = System.IO`), and `global::`. Brace/`#region` balance and forbidden-token scans ignore comments and string literals.
- **Tools → Split into projector subgrids** — writes projector-friendly copies of connected subgrids. Generated SBC uses a real `xsi:type` XML namespace. A successful single-grid skip is not reported as an error.
- **Tools → Survival Sanity** — Prototech → vanilla copy for survival crafting.
- **Tools → Upgrade to Prototech** — vanilla → Prototech copy.
- **Tools → Harden armor around cores** and **Lightweight outer hull**.
- **Tools → Export Space Engineers 2 JSON**.
- Armor skin / HSV palette engine: primary hex paints armor (or every matching block if secondary is omitted); secondary hex paints non-armor accents, or heavy armor when both colors are set with armor-only.

### Mappings and CLI
- Built-in categories: armor (70 light ↔ heavy pairs), thrusters, weapons, functional, DLC substitution (96 premium DLC → base-game pairs).
- Opt-in Prototech (23 vanilla ↔ Factorum Prototech pairs). Off by default; **not** included in `--all-categories` (it overlaps thrusters/functional/weapons).
- `--all-categories` enables built-in mappings only. Bundled WeaponCore and Assertive Armaments profiles stay opt-in so they cannot crash the CLI with duplicate sources.
- CLI accepts any `.sbc` path (not only a folder named with `bp.sbc`). Nested search prefers `bp.sbc`, then a sorted `*.sbc`.
- Binary cache cleanup looks for `bp.sbcB5`.
- Scanner tracks reverse-mode convertible blocks so Convert matches `--reverse`.
- Grid rescale (large ↔ small) multiplies/divides `Min` coordinates by the 5:1 ratio. Small → large truncates toward zero so negative coordinates are not shifted by floor division.
- Profile export can write to an existing extensionless file path instead of treating it as a directory.
- Bundled profiles: WeaponCore, Assertive Armaments, Build Vision.

### Reliability
- Production blueprint writes go through `safe_xml.safe_write` (unique temp names, replace). An interrupted conversion cannot leave a truncated `bp.sbc`.
- XML parse path uses `defusedxml` (XXE / entity expansion).
- Pillow ≥ 12.3.0 for the header logo. Tagged Windows builds embed `logo.png`, `app_icon.ico`, README, LICENSE, RELEASE_NOTES, `profiles/`, and `data/`.
- Official README is the 3.2.0 user guide. The public GitHub tree is the runtime app (test suite and internal planning notes are not published). GitHub Releases use this version’s notes as the release body and publish `SHA256SUMS.txt`.

## v3.1.2 (2026-05-24)

### Fixes
- Fix mypy `[type-arg]` failures on `xml.etree.ElementTree` annotations that broke CI for every Dependabot PR.
- Drop end-of-life Python 3.8 from the CI matrix; supported versions are now Python 3.11 and 3.12.

### Security
- XML parsing hardened with `defusedxml` via new `safe_xml.py` wrapper (XXE / billion-laughs protection).
- GitHub Actions pinned to commit SHAs with least-privilege `permissions:` blocks.
- Release workflow now publishes `SHA256SUMS.txt` alongside binaries.
- Added Dependabot config for `github-actions` and `pip` ecosystems.
- `UpdateChecker` now validates the `owner/repo` identifier before issuing HTTP requests.

### Project / Licensing
- Project ownership consolidated under Meraby Labs.
- License re-issued as a proprietary EULA: free for personal non-commercial use; commercial use requires a separate license. The project is not open source.
- README rewritten to reflect ownership and licensing.
- Removed `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` (external contributions are not solicited).

## v3.0.0 (2026-02-07)

### Major Architecture

- Added `version.py` as single source of truth for version/build/channel.
- Added `app_settings.py` and `update_checker.py` to centralize config and updates.
- Introduced modular mapping registry (`mappings/`) with validation:
  - duplicate targets
  - circular swaps
  - category registration and merge checks
- Refactored conversion engine to support multi-category conversion in a single pass.
- Preserved legacy armor constants and default behavior for CLI backward compatibility.

### Mapping Expansion

- Added built-in categories:
  - `armor` (existing 70 pairs)
  - `thrusters`
  - `weapons`
  - `functional`
- Added profile loading system (`mapping_profiles.py`) and `profiles/` auto-discovery.
- Shipped built-in mod profiles:
  - WeaponCore
  - Assertive Armaments
  - Build Vision

### Analytics Dashboard

- Added block cost database: `data/block_costs.json`.
- Implemented analytics engine (`blueprint_analytics.py`):
  - component totals
  - ingot and ore back-calculation
  - PCU and mass totals
  - category distribution
  - conversion delta comparison
  - CSV/TXT report export
- Added blueprint health audit:
  - missing control/power checks
  - thruster balance warnings
  - unknown block subtype detection
  - fix actions for missing control/power blocks

### UI Overhaul

- Fully migrated runtime UI to modular CustomTkinter app (`ui/app.py`).
- Replaced legacy monolithic `gui_standalone.py` with compatibility launcher.
- Added:
  - category toggles
  - animated progress ring
  - before/after diff preview
  - analytics visualization tab
  - profile editor dialog (create/edit/duplicate/import/export/share/test)
  - keyboard shortcuts (`Ctrl+O`, `Ctrl+R`, `Ctrl+Z`)
  - recent directories/blueprints
  - native Windows drag-and-drop blueprint loading
  - appearance mode selector (Light/Dark/System)
  - in-app changelog window
  - update notification checks

### Distribution and Community

- Added CI workflow (`.github/workflows/ci.yml`) with lint, mypy, tests.
- Added release workflow (`.github/workflows/release.yml`) for tagged builds.
- Updated packaging scripts/spec to embed data/profiles and versioned executable names.
- Added icon/logo generation tooling (`generate_icon.py`, `convert_icon.py`) and app icon assets.
- Updated documentation: `README.md`, `INSTALL.md`, `DEVELOPMENT_PLAN.md`.
- Added community files:
  - `CONTRIBUTING.md`
  - `CODE_OF_CONDUCT.md`
  - issue templates for bug, feature, mapping request

### Test Coverage

- Kept existing 19 compatibility tests passing.
- Added new tests for:
  - mapping registry
  - profile management
  - analytics engine/report export
  - update checker cache behavior

## v2.0.0

- Expanded armor mappings to 70 pairs.
- Added dry-run preview and batch conversion.
- Added custom directory browsing and improved branding.

