# Space Engineers Block Exchanger

**A Meraby Labs product. Proprietary software. Free for personal, non-commercial use. Commercial use requires a license.**

[![CI](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml)
[![Release](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml)

Space Engineers Block Exchanger ("SEBX") is a Windows desktop and CLI toolkit, developed and owned by **Meraby Labs**, for converting and analysing Space Engineers blueprints.

- Multi-category block conversion (armor, thrusters, weapons, functional, DLC substitution, Prototech/Factorum)
- Full 2024–2026 SE1 content coverage: Prosperity Pack (July 2026), Contact, Signal, Automations, Warfare 2/3
- Survival Projection Sanity Mode (1-click downgrade of uncraftable Prototech blocks for survival projectors)
- In-App Programmable Block (PB) Script Doctor (AST whitelist auditing, MDK compliance, instruction estimation)
- Multi-Grid Hierarchy & 2.5D Isometric Matrix Visualizer (rotors, pistons, hinges, coordinate slices)
- Steam Workshop & Mod.io Direct Blueprint Ingestion
- Modular mapping registry with shareable `.sebx-profile` profiles
- Blueprint analytics: ores, ingots, components, PCU, mass, category distribution
- Dry-run diff preview and conversion cost delta reporting
- Space Engineers 2 (VRage 3) readiness audit, DLC -> Base vanillafyer, grid rescaler
- Update checker and changelog viewer
- Hardened XML parsing (defusedxml), SHA-256 release checksums

> Space Engineers is a trademark of Keen Software House. This product is not affiliated with or endorsed by Keen Software House.

---

## License at a Glance

| Use case | Allowed? |
|---|---|
| Personal use on your own blueprints | Yes, free |
| Use in private community servers (non-revenue) | Yes, free |
| Streaming / video content where SEBX is a minor incidental tool | Yes, free |
| Commercial deployment, paid services, enterprise rollout | **Requires commercial license** |
| Bundling SEBX into a paid product or paid mod pack | **Requires commercial license** |
| Redistributing the binaries or source | **No** |
| Forking and publishing modified versions | **No** |
| Repackaging or mirroring releases | **No** |

Full terms: see [LICENSE](LICENSE). For commercial licensing inquiries contact Meraby Labs.

---

## Download

Official builds are published only at the Meraby Labs GitHub Releases page:
<https://github.com/MerabyLabs/SE-Block-Exchanger/releases>

Each release ships:

- `SE_Tactical_Command_v<version>.exe` — Windows portable build
- `SHA256SUMS.txt` — verify your download with `Get-FileHash`

Do not trust copies obtained from any other source.

---

## Quick Start

### GUI (recommended)

Double-click `launch_gui.bat`, or:

```powershell
python gui_standalone.py
```

### CLI

```powershell
python se_armor_replacer.py path\to\blueprint\bp.sbc
```

---

## Requirements (running from source)

- Windows 10/11
- Python 3.11 or 3.12
- `customtkinter`
- `defusedxml`
- Optional: `Pillow` for logo/icon utilities

Install dependencies:

```powershell
pip install -r requirements.txt
```

---

## CLI Reference

```powershell
# Default: Light -> Heavy armor conversion
python se_armor_replacer.py <path>

# Reverse conversion
python se_armor_replacer.py <path> --reverse

# Preview changes without modifying the blueprint
python se_armor_replacer.py <path> --dry-run

# Enable additional categories
python se_armor_replacer.py <path> --categories armor,thrusters,weapons,functional

# Inspect mapping registry
python se_armor_replacer.py --list-categories
python se_armor_replacer.py --list-mappings --categories armor,thrusters
```

---

## GUI Highlights

- CustomTkinter modular UI (`ui/` package)
- Category toggles for conversion mapping selection
- Keyboard shortcuts: `Ctrl+O` open, `Ctrl+R` run, `Ctrl+Z` undo
- Recent blueprint directories and quick access
- Native Windows drag-and-drop loading
- Before/after diff preview
- Analytics dashboard: PCU/mass counters, category distribution, ore -> ingot -> component -> block tree, conversion deltas, health audit with fix actions
- CSV/TXT analytics export
- Profile editor: create/edit/duplicate, add/remove pairs with subtype suggestions, test against blueprint, import/export `.sebx-profile`, import from URL, Discord share payload
- In-app changelog and update notifications

---

## Mapping Registry

Built-in categories:

- `armor` (70 pairs)
- `thrusters`
- `weapons`
- `functional`
- `dlc_substitution` (vanillafies blueprints by replacing premium DLC blocks with base-game equivalents)

Profiles auto-load from `profiles/` at startup. Bundled mod profiles:

- `profiles/weaponcore.sebx-profile`
- `profiles/assertive_armaments.sebx-profile`
- `profiles/build_vision.sebx-profile`

---

## SE2 Transition Utilities

Prepare creations for **Space Engineers 2** (VRage 3 Engine):

- **SE2 Readiness Score** — audits scripts, mechanical chains (pistons/rotors/hinges), and DLC footprint, producing a readiness score.
- **DLC -> Base Convert (Vanillafyer)** — replaces DLC blocks with vanilla alternatives so blueprints load for everyone.
- **Grid Rescaler (Large <-> Small Grid)** — scales block types and coordinates between grid sizes.

---

## Security

- XML parsed via `defusedxml` to prevent XXE and entity-expansion attacks.
- Release pipeline pins all GitHub Actions to commit SHAs and publishes SHA-256 checksums alongside every binary.
- Dependabot keeps Actions and Python dependencies updated.

Report security issues privately to Meraby Labs (do not open a public issue).

---

## Packaging and Release (internal)

- CI workflow: `.github/workflows/ci.yml`
- Release workflow: `.github/workflows/release.yml` (triggered by tag `vX.Y.Z`)
- Version source of truth: `version.py`

---

## Trademarks and Ownership

"Meraby Labs", the Meraby Labs logo, and "Space Engineers Block Exchanger" are trademarks of Meraby Labs. All other trademarks are the property of their respective owners.

(c) 2025-2026 Meraby Labs. All Rights Reserved. See [LICENSE](LICENSE) for full terms.
