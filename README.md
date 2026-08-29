# Space Engineers Block Exchanger

**Version 3.2.0 · A Meraby Labs product. Proprietary software. Free for personal, non-commercial use. Commercial use requires a license.**

[![CI](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml)
[![Release](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml)

Space Engineers Block Exchanger (SEBX, also branded **Tactical Command**) is a Windows desktop and command-line toolkit for converting and analysing Space Engineers `.sbc` blueprints. Convert always writes a new copy; the original blueprint stays untouched unless you use the CLI to overwrite in place.

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

Full terms: see [LICENSE](LICENSE). For commercial licensing inquiries contact Meraby Labs. Forks and pull requests are not solicited.

---

## Download

Official builds are published only at:

<https://github.com/MerabyLabs/SE-Block-Exchanger/releases>

Each release ships:

- `SE_Tactical_Command_v<version>.exe` — Windows portable app
- `SHA256SUMS.txt` — verify with `Get-FileHash -Algorithm SHA256`

Do not trust copies obtained from any other source.

---

## Run

### Windows executable (recommended)

1. Download `SE_Tactical_Command_v3.2.0.exe` from the official Releases page.
2. Double-click the executable. No installer is required.
3. Point the app at your local blueprints folder if it does not detect it automatically:

   `%APPDATA%\SpaceEngineers\Blueprints\local`

### Run from source

Requires **Windows 10/11** and **Python 3.11 or 3.12**.

```powershell
pip install -r requirements.txt
```

Then launch the GUI with any of:

- Double-click `launch.bat` (starts `main.py`)
- Double-click `launch_gui.bat` (starts `gui_standalone.py`)
- `python main.py`
- `python gui_standalone.py`

Optional desktop shortcut: double-click `Create Desktop Shortcut.bat`.

Dependencies in `requirements.txt`: CustomTkinter 5.x, `defusedxml`, and Pillow (header logo).

---

## What you can do

### Convert ships

- Multi-category conversion: armor (70 pairs), thrusters, weapons, functional, and DLC substitution (96 pairs that replace premium DLC blocks with base-game equivalents).
- Opt-in **Prototech** mappings (vanilla ↔ Factorum Prototech). These are off by default and are not included when you enable every built-in category.
- Live before/after preview when you select a blueprint.
- Mod profiles auto-load from `profiles/` (WeaponCore, Assertive Armaments, Build Vision). Use the profile editor to create or import `.sebx-profile` files for your own ships.

### File menu

- Open a blueprints folder (`Ctrl+O`)
- **Import Workshop / Mod.io blueprint** from a Steam Workshop URL or ID, or a Mod.io URL
- Refresh the list (`F5`)
- Create a desktop shortcut

### Tools menu

- **Selective block exchange** — pick individual subtype swaps
- **PB Doctor** — inspect and fix programmable-block C# against the Space Engineers whitelist
- **Split into projector subgrids** — write projector-friendly subgrid copies
- **Survival Sanity** — Prototech → vanilla copy for survival crafting
- **Upgrade to Prototech** — vanilla → Prototech copy
- **Harden armor around cores** / **Lightweight outer hull**
- **Export Space Engineers 2 JSON**

### Analytics and extras

- PCU, mass, ores, ingots, components, category distribution, conversion deltas
- Blueprint health audit (control, power, thruster balance, unknown subtypes)
- CSV/TXT report export
- Grid rescale (large ↔ small)
- SE2 readiness audit
- In-app changelog and optional update checks
- Native Windows drag-and-drop
- Keyboard shortcuts: `Ctrl+O` open, `Ctrl+R` convert, `Ctrl+Z` undo last conversion

---

## Command line

```powershell
# Default: Light -> Heavy armor (writes in place; use --dry-run first)
python se_armor_replacer.py path\to\blueprint\bp.sbc

python se_armor_replacer.py path\to\blueprint\bp.sbc --reverse
python se_armor_replacer.py path\to\blueprint\bp.sbc --dry-run
python se_armor_replacer.py path\to\blueprint\bp.sbc --categories armor,thrusters,weapons,functional
python se_armor_replacer.py path\to\blueprint\bp.sbc --all-categories

python se_armor_replacer.py --list-categories
python se_armor_replacer.py --list-mappings --categories armor,thrusters
python se_armor_replacer.py --version
```

`--all-categories` enables built-in categories only (armor, thrusters, weapons, functional, DLC substitution). Prototech and mod profiles stay opt-in.

The GUI converter writes a **new** blueprint copy. The CLI overwrites the input file unless you pass `-o` or `--dry-run`. The CLI creates a backup unless you pass `--no-backup`.

---

## Mapping categories

| Category | Notes |
|---|---|
| `armor` | 70 light ↔ heavy pairs (default) |
| `thrusters` | Vanilla thruster swaps |
| `weapons` | Vanilla weapon swaps |
| `functional` | Functional block swaps |
| `dlc_substitution` | 96 DLC → base-game pairs |
| `prototech` | Opt-in vanilla ↔ Prototech (23 pairs) |

Bundled profiles live in `profiles/`. Drop additional `.sebx-profile` files there to load them on startup. See `profiles/README.md` for the local file format.

---

## Verify a download

```powershell
Get-FileHash -Algorithm SHA256 .\SE_Tactical_Command_v3.2.0.exe
```

Compare the hash to `SHA256SUMS.txt` from the same release. Blueprint XML is parsed with `defusedxml`. Report security issues privately to Meraby Labs; do not open a public issue for vulnerabilities.

---

## Trademarks and ownership

"Meraby Labs", the Meraby Labs logo, and "Space Engineers Block Exchanger" are trademarks of Meraby Labs. All other trademarks are the property of their respective owners.

© 2025-2026 Meraby Labs. All Rights Reserved. See [LICENSE](LICENSE) for full terms.
