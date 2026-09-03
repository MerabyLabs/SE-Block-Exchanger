# Release Notes

## v4.0.0 (unreleased candidate)

This is the first public v4 version under preparation. Keep **4.0.0**: the unified
UI/document/renderer changes and stricter conversion contracts are a major change
from v3.2.1. No v4 release has been approved; native SE2 acceptance is a hard gate.

### Changes

- Reconcile the cumulative PR29 renderer/document/performance work with the v4 line.
  Retain the historical converter, analytics, profile, PB Doctor and UI regression tests.
- Validate SE1 mappings using object-builder type plus subtype, including empty
  default weapon subtypes, against the installed 1.210 catalog or versioned baseline.
- Refresh the 1,503-definition catalog and cost metadata. The baseline offers 116
  light/heavy pairs, 21 DLC replacements, one weapon pair and one Prototech pair.
  Unsafe footprint/type changes and stale IDs are excluded with diagnostics.
- Stage converted copies before publication, refuse existing output names, and
  protect user-edited converted copies from undo deletion.
- Limit grid-size scaling to single armor grids; preserve cell coordinates.
- Show analytics coverage and partial totals instead of treating unknown blocks as zero.
- Add the native SE2 EntityBundle bridge and installed definition index. The first
  supported subset is 16 armor variants on one grid; unsupported functional/modded/
  subgrid conversions fail with explicit diagnostics. No readiness score certifies
  compatibility, and no synthetic JSON manifest or silent armor fallback remains.
- Move the Subgrids layout to a responsive split view, clarify shell-empty states,
  report simplification and make missing-root startup nonblocking.
- Upgrade to CustomTkinter 6.x; package NumPy, ModernGL, Pillow, shaders, catalogs,
  document modules and the complete renderer through one PyInstaller specification.
- Add Python 3.11/3.12 unified CI, catalog checks, clean-package checks, frozen runtime
  probes, file hashes and a fail-closed release acceptance manifest.

### Release limitations

Native SE2 open/place/save/reopen verification is still required. Single-grid and
subgrid results must be recorded separately. The official SE2 build also has
incomplete subgrid projection support. See [COMPATIBILITY](COMPATIBILITY.md) for
the exact support boundary; this candidate does not claim full SE2 export support.

## v3.2.1 (2026-08-29)

Patch for the portable Windows build. The 3.2.0 executable could fail when
started from a desktop shortcut because it resolved bundled data from the
current working directory. This patch made resource resolution bundle-safe,
kept frozen profile edits in `%APPDATA%`, fixed 64-bit drag-and-drop values, and
included the shortcut helper in tagged builds.

## v3.2.0 (2026-08-29)

The 3.2 line introduced the product workflow: copy-on-convert previews, armor
and multi-category mappings, subgrid maps, analytics, PB Doctor, selective
exchange, Workshop/Mod.io import, profiles, and a responsive CustomTkinter UI.
It also added safe XML parsing, atomic writes, desktop shortcut handling and
the first portable Windows packaging workflow. v4 retains those regression
contracts while moving the tested UI to CustomTkinter 6.x and adding the
catalog-backed renderer and native-SE2 boundary described above.

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

