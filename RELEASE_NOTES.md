# Release Notes

## v3.2.0 (2026-08-29)

### Desktop app
- Convert a ship from a clearer converter window: sentence-case labels, grouped categories, and a Convert button that states how many blocks will change.
- Selecting a blueprint opens a live before/after preview. Convert writes a **new copy**; the original stays untouched.
- Stays on CustomTkinter 5.x.

### Import and tools
- **File → Import Workshop / Mod.io blueprint** — paste a Steam Workshop URL or ID, or a Mod.io URL, and copy the ship into your local blueprints folder.
- **Tools → Selective block exchange** — choose individual subtype swaps instead of a whole category.
- **Tools → PB Doctor** — inspect and fix programmable-block scripts against the Space Engineers whitelist.
- **Tools → Split into projector subgrids** — write projector-friendly copies of connected subgrids.
- **Tools → Survival Sanity** — Prototech → vanilla copy for survival crafting.
- **Tools → Upgrade to Prototech** — vanilla → Prototech copy.
- **Tools → Harden armor around cores** and **Lightweight outer hull**.
- **Tools → Export Space Engineers 2 JSON**.

### Mappings
- DLC substitution: 96 premium DLC → base-game pairs.
- Opt-in Prototech category (23 pairs). It is off by default and is not included in `--all-categories`.

### Reliability
- Blueprint XML writes go through a hardened writer (unique temp files, no leftover half-written `bp.sbc`).
- Workshop and Mod.io import refuse unsafe zip paths and Windows junctions/symlinks.
- PB Doctor keeps valid `using` directives (`System`, VRage) and strips forbidden namespaces, including `using static` and aliases.

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

