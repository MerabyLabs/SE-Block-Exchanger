# Release Notes

## v4.0.0 (2026-08-26)

### Major Additions & Space Engineers 1 2024–2026 Content Expansion

- **2024–2026 DLC & Block Expansion**:
  - Full support for the **Prosperity Pack (July 2026)**: Sloped Cockpits, Battery Banks, Factory Stairs/Railings, Industrial Walkways, Decorative Conduits, and Flat Collectors.
  - Full support for the **Contact Pack (2024)**: Radar/Scanner Antennas, Contact Bridge Cockpits, Factorum Consoles, and Decorative Modules.
  - Full support for the **Signal Pack (2024)**: Signal Beacons, Broadcast Controllers, and Action Trigger blocks.
  - Updated cost database in `data/block_costs.json` with PCU, mass, and component breakdowns for all 29 new block additions.

- **Prototech & Factorum Endgame Systems**:
  - New `prototech` mapping category supporting bidirectional swaps (`Standard <-> Prototech`).
  - **Survival Projection Sanity Mode**: 1-click conversion to downgrade uncraftable Factorum Prototech blocks to standard survival craftable blocks so projection blueprints never stall in survival games.
  - **Prototech Upgrade Engine**: 1-click upgrade to equip blueprints with Factorum reactors, thrusters, jump drives, and weapons for creative and faction flagships.

- **Embedded Programmable Block (PB) Script Doctor**:
  - Scans blueprints for `MyObjectBuilder_MyProgrammableBlock` instances.
  - Static AST and whitelist analysis checking for banned namespaces (`System.IO`, `System.Threading`, `System.Reflection`, `System.Net`, etc.), forbidden keywords (`async`, `await`, `dynamic`, `…`), and MDK compliance.
  - Structural sanity auditing (brace matching, `#region` balancing, character limits up to 100k chars).
  - Per-tick instruction load heuristic estimator (~49,500 instruction warning thresholds).

- **Multi-Grid Hierarchy & Isometric Matrix Visualizer**:
  - Parses multi-grid blueprints and graphs mechanical chains across rotors, hinges, pistons, and connectors.
  - Computes 3D bounding boxes and generates 2.5D top-down (X/Z) and side-elevation (Z/Y) ASCII matrix projections with category legends and modification markers.

- **Steam Workshop & Mod.io Sync**:
  - Direct ingestion of Steam Workshop blueprints via Workshop IDs and URLs.
  - Auto-discovery of local Steam Workshop download caches.
  - Mod.io crossplay blueprint URL parsing and extraction.

- **UI & Workflow Enhancements**:
  - Dedicated **PB DOCTOR** tab with compliance score badges, diagnostic logs, and script inspectors.
  - Dedicated **SUBGRIDS & MAP** tab with hierarchy trees and density slices.
  - 1-click quick action buttons in Utilities for Survival Sanity and Prototech upgrades.
  - Added File Menu with direct Workshop/Mod.io imports and shortcut bindings.

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

