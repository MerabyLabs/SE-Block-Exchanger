# Meraby Block Exchanger

## Offline blueprint toolkit

**Version 3.2.3 · A Meraby Labs product. Proprietary software. Free for personal, non-commercial use. Commercial use requires a license.**

[![CI](https://github.com/MerabyLabs/Meraby-Block-Exchanger/actions/workflows/ci.yml/badge.svg)](https://github.com/MerabyLabs/Meraby-Block-Exchanger/actions/workflows/ci.yml)
[![Release](https://github.com/MerabyLabs/Meraby-Block-Exchanger/actions/workflows/release.yml/badge.svg)](https://github.com/MerabyLabs/Meraby-Block-Exchanger/actions/workflows/release.yml)

Meraby Block Exchanger (MBX) is a Windows desktop and command-line toolkit for local blueprint files.

It converts blocks (armor, thrusters, weapons, functional, DLC → vanilla, opt-in Prototech), imports Workshop/Mod.io ships, inspects programmable-block scripts, splits projector subgrids, hardens or lightens armor, rescales large ↔ small grid, audits PCU/mass/ores, and scores Space Engineers 2 readiness. The GUI **always writes a new copy**, including analytics repair; the original ship is not overwritten. The CLI overwrites in place unless you pass `-o` or `--dry-run`.

Works with local Space Engineers blueprint (`.sbc`) files. Not affiliated with or endorsed by Keen Software House. Space Engineers is a trademark of Keen Software House.

---

## License at a Glance

| Use case | Allowed? |
|---|---|
| Personal use on your own blueprints | Yes, free |
| Use in private community servers (non-revenue) | Yes, free |
| Streaming / video content where MBX is a minor incidental tool | Yes, free |
| Commercial deployment, paid services, enterprise rollout | **Requires commercial license** |
| Bundling MBX into a paid product or paid mod pack | **Requires commercial license** |
| Redistributing the binaries or source | **No** |
| Forking and publishing modified versions | **No** |
| Repackaging or mirroring releases | **No** |

Full terms: see [LICENSE](LICENSE). For commercial licensing inquiries email legal@merabylabs.com. Forks and pull requests are not solicited.

---

## Download

Builds are published only at:

<https://github.com/MerabyLabs/Meraby-Block-Exchanger/releases>

Each release ships:

- `Meraby_Block_Exchanger_v<version>.exe` — Windows portable app (no installer)
- `Meraby_Block_Exchanger_v<version>.exe.sha256` — SHA-256 sidecar for that exe
- `SHA256SUMS.txt` — same hash, with the exe basename on each line

GitHub Release title: `Meraby Block Exchanger v<version>`.

Assets already published under the previous exe name are renamed on the release separately. This repository’s build scripts produce `Meraby_Block_Exchanger_v<version>.exe`. Do not use a v3.2.0 exe — it crashes when opened from a desktop shortcut.

Do not trust copies obtained from any other source. Typical blueprints folder:

`%APPDATA%\SpaceEngineers\Blueprints\local`

---

## Run

### Windows executable (recommended)

1. Download `Meraby_Block_Exchanger_v<version>.exe` from the Releases page. Until that asset is published, use the checksum that shipped with the previous exe name on the same release. Do not use a v3.2.0 exe — it crashes when opened from a desktop shortcut.
2. Double-click it. No installer is required.
3. If the app does not find your ships, open that local blueprints folder (`Ctrl+O`).

### Run from source

Requires **Windows 10/11** and **Python 3.11 or 3.12**.

```powershell
pip install -r requirements.txt
```

Then launch with any of:

- `launch.bat` → `main.py`
- `launch_gui.bat` → `gui_standalone.py`
- `python main.py`
- `python gui_standalone.py`

Desktop shortcut: `Create Desktop Shortcut.bat` or File → Create desktop shortcut. The packaged exe shortcut targets the `.exe`; from source it points at `launch.bat`.

Dependencies: CustomTkinter 5.x, `defusedxml`, Pillow (header logo).

---

## What the program does

### Convert a ship

- Pick a blueprint on the left. The Convert button states how many blocks will change.
- Categories (toggle independently): **armor** (70 light ↔ heavy pairs), **thrusters**, **weapons**, **functional**, **DLC → vanilla** (96 premium DLC → base-game pairs), and opt-in **Prototech** (23 vanilla ↔ Factorum pairs). Prototech is off by default and is **not** included when you enable every built-in category.
- Direction: light → heavy or reverse. Armor before/after counts only use armor swaps (other categories do not fake armor totals).
- **Convert** writes a new folder next to the original. **Undo last copy** removes that copy. **Convert all in folder** batch-converts every listed ship the same way.
- Live **Preview** tab: before/after diff. Convert is disabled until counts are fresh after you change categories or direction.

### Center tabs

| Tab | What it shows |
|---|---|
| **Overview** | Block totals, conversion readiness, file location |
| **Preview** | Live before/after of the current mapping and direction |
| **XML** | Blueprint XML (truncated if huge). Errors appear in the tab status, not a fake “loaded” label |
| **Analytics** | PCU, mass, ores, ingots, components, category mix, conversion cost delta, health audit (control, power, thruster balance, unknown subtypes). Fix actions write a new `REPAIRED_` copy; CSV/TXT export |
| **Subgrids** | Clickable CubeGrid tree and a 2D voxel map from `Min` coordinates (`TopGridId` links). Click a rotor/turret to isolate that grid; Fit uses that grid’s bounds. Single-grid ships still draw a map |
| **SE2** | Readiness score from DLC usage, programmable-block scripts, and mechanical subgrids. **Replace DLC with vanilla** and **large ↔ small grid rescale** from this tab |

### File menu

- **Open folder…** (`Ctrl+O`) — scan a blueprints directory; recent folders are remembered
- **Import Workshop / Mod.io blueprint…** — paste a Steam Workshop URL or ID, or a Mod.io URL. Copies the ship into local blueprints. If the item has no `bp.sbc`, a sorted fallback `*.sbc` is copied to `bp.sbc` so it appears in the list. Unsafe zip paths, drive-letter entries, and Windows junctions/symlinks are refused
- **Refresh blueprints** (`F5`)
- **Create desktop shortcut**
- **Exit** (`Alt+F4`) — the window close button quits; the process does not stay running

Drop a blueprint folder onto the window on Windows.

### Tools menu

- **Selective block exchange** — choose individual subtype swaps instead of a whole category
- **PB Doctor** — inspect and fix programmable-block C# against the Space Engineers whitelist. Keeps valid `using` (`System`, VRage). Strips forbidden namespaces, including `using static`, aliases, and `global::`. Ignores braces and tokens inside comments and strings
- **Split into projector subgrids** — writes projector-friendly copies of connected grids
- **Survival Sanity** — Prototech → vanilla copy for survival crafting
- **Upgrade to Prototech** — vanilla → Prototech copy
- **Harden armor around cores** — heavy armor near reactors, cockpits, and similar
- **Lightweight outer hull** — light armor on the outer shell
- **Export Space Engineers 2 JSON**

Armor skin / HSV palette is included in the engine: primary hex on armor (or every matching block if secondary is omitted); secondary hex on non-armor, or on heavy armor when both colors are set with armor-only.

### Profiles

Files in `profiles/` load on startup. Shipped: WeaponCore, Assertive Armaments, Build Vision. The profile editor can create, duplicate, import/export `.sebx-profile`, import from a URL, test pairs against a ship, and copy a Discord share payload. Drop your own `.sebx-profile` into `profiles/` and restart. The `.sebx-profile` extension is unchanged so existing profiles still load. See `profiles/README.md`.

Settings, the update cache, and frozen-build profile edits stay in `%APPDATA%\SEBlockExchanger` (or `~/.se_block_exchanger` when AppData is not set). That folder name is unchanged so existing installs keep their data.

### Header and Help

- Appearance: Light / Dark / System
- What’s new / Help → View Changelog
- Optional auto-check for updates on startup
- Help → Report an Issue
- Keyboard: `Ctrl+O` open, `Ctrl+R` convert, `Ctrl+Z` undo, `F5` refresh, `Alt+F4` exit

---

## Command line

```powershell
python se_armor_replacer.py path\to\blueprint\bp.sbc
python se_armor_replacer.py path\to\folder
python se_armor_replacer.py path\to\ship.sbc --reverse
python se_armor_replacer.py path\to\bp.sbc --dry-run
python se_armor_replacer.py path\to\bp.sbc -o path\to\out.sbc
python se_armor_replacer.py path\to\bp.sbc --no-backup
python se_armor_replacer.py path\to\bp.sbc --categories armor,thrusters,weapons,functional
python se_armor_replacer.py path\to\bp.sbc --all-categories
python se_armor_replacer.py --list-categories
python se_armor_replacer.py --list-mappings --categories armor,thrusters
python se_armor_replacer.py --version
python se_armor_replacer.py path\to\blueprint --stage-for-spawn path\to\MerabyQA_folder
```

- Any `.sbc` file is accepted. A folder prefers `bp.sbc`, then the first sorted `*.sbc`.
- `--all-categories` is **built-in only** (armor, thrusters, weapons, functional, DLC substitution). Prototech and mod profiles stay opt-in so WeaponCore / Assertive Armaments cannot collide with vanilla mappings.
- Default CLI conversion is light → heavy armor, **in place**, with a `.sbc.backup` unless `--no-backup`. Use `--dry-run` first.
- After a write, leftover `bp.sbcB5` binary cache next to the file is removed. If that file stays locked, the operation fails instead of leaving a stale binary for the game to load.
- Staging SOP, before spawn: `python se_armor_replacer.py path\to\blueprint --stage-for-spawn path\to\MerabyQA_folder`. This copies the folder and deletes `bp.sbcB5`. It does not change block subtypes. Exit code 2 is the QA gate: non-vanilla subtypes are present, so do not mark the check CLEAR unless that world has the mods loaded. A `bp.sbcB5` the game writes while spawning is a bake, not a file this step left behind. If a staged folder already contains `bp.sbcB5`, delete it before spawn.
- Grid rescale (GUI) uses a 5:1 `Min` ratio; small → large truncates toward zero so negative coordinates are not shifted.

---

## Mapping categories

| Category | Notes |
|---|---|
| `armor` | 70 light ↔ heavy pairs (CLI default) |
| `thrusters` | Vanilla thruster swaps |
| `weapons` | Vanilla weapon swaps |
| `functional` | Functional block swaps |
| `dlc_substitution` | 96 DLC → base-game pairs |
| `prototech` | Opt-in vanilla ↔ Prototech (23 pairs) |

---

## How files are written

GUI conversions, projector splits, Workshop import, and other production SBC writes use a temp file then replace, so an interrupted run does not leave a half-written `bp.sbc`. XML is parsed with `defusedxml`. Report security issues privately to Meraby Labs (do not open a public issue for vulnerabilities).

Tagged Windows builds embed README, LICENSE, RELEASE_NOTES, `profiles/`, `data/`, `create_desktop_shortcut.ps1`, `app_icon.ico`, and `logo.png`.

---

## Verify a download

```powershell
Get-FileHash -Algorithm SHA256 .\Meraby_Block_Exchanger_v3.2.3.exe
```

Compare the hash to `Meraby_Block_Exchanger_v3.2.3.exe.sha256` or to the matching line in `SHA256SUMS.txt` from the **same** release. Both name the exe `Meraby_Block_Exchanger_v<version>.exe`. If a release asset still uses the previous exe name, hash that file against the checksum published beside it.

---

## Trademarks and ownership

"Meraby Labs", the Meraby Labs logo, and "Meraby Block Exchanger" are trademarks of Meraby Labs. All other trademarks are the property of their respective owners.

© 2025-2026 Meraby Labs. All Rights Reserved. See [LICENSE](LICENSE) for full terms.
