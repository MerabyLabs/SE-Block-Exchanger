# Release Notes

## v4.0.0 (2026-08-26) — The Master Engineering & Prototech Update

### 🚀 What's New in v4.0

- **Full 2024–2026 DLC Support**:
  - Added every new block from the **Prosperity Pack (July 2026)**, **Contact Pack (2024)**, and **Signal Pack (2024)**.
  - Convert sloped cockpits, battery banks, factory stairs, decorative conduits, and radar antennas back to base-game blocks with 1 click so anyone can paste your ships without owning DLCs.

- **Prototech & Factorum Tech Tools**:
  - **Survival Projection Sanity**: Ever had a shipyard projector get stuck because a blueprint contains salvage-only Prototech blocks? Click "Survival Sanity" to swap them to normal craftable reactors, thrusters, and batteries.
  - **1-Click Prototech Upgrader**: Instantly upgrade your favorite vanilla ships into endgame Prototech beasts equipped with Factorum jump drives, reactors, thrusters, and weapons.

- **In-App PB Script Doctor**:
  - Checks C# scripts inside your Programmable Blocks before you spawn them in multiplayer.
  - Flags missing `Main()` methods, unclosed braces, and banned code (`System.IO`, `System.Threading`) that cause server kicks or crashes.
  - Shows an estimated instruction cost so you can prevent server simulation drops (Sim Speed lag).

- **Subgrid Inspector & 2.5D Ship Map**:
  - View a complete hierarchy tree of all rotors, hinges, pistons, and attached subgrids.
  - See top-down and side profile blueprint projections showing where weapons, cockpits, and thrusters are placed.

- **Steam Workshop & Mod.io Import**:
  - Paste any Steam Workshop link or ID to grab blueprints directly from your cache or Workshop.
  - Full support for Mod.io crossplay blueprint packages.

- **Smart Grid Rescaling**:
  - Convert Large grid capital ships into Small grid fighters (or vice versa). Coordinates automatically scale by 5x so blocks never overlap or float away.

- **Quality of Life & UI**:
  - Added new dedicated tabs: **PB DOCTOR** and **SUBGRIDS & MAP**.
  - New quick-action buttons for 1-click conversions.
  - Full keyboard shortcuts (`Ctrl+O`, `Ctrl+R`, `Ctrl+Z`, `F5`) and top menu bar.

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

