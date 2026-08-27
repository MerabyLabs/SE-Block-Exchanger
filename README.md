# Space Engineers Block Exchanger (SEBX)

**A free desktop tool by Meraby Labs for Space Engineers builders, survival players, and server admins.**

[![CI](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/ci.yml)
[![Release](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml/badge.svg)](https://github.com/MerabyLabs/SE-Block-Exchanger/actions/workflows/release.yml)

Ever downloaded an awesome ship from the Steam Workshop only to find out:
- You can't weld it in your survival game because it has **paid DLC blocks you don't own**?
- Your projector gets stuck because it contains **uncraftable Prototech / Factorum blocks**?
- The ship's **in-game script crashes your server** or uses banned code?
- You want to convert a light armor scout into a heavy combat tank in 2 seconds?

**SE Block Exchanger (SEBX)** solves all of this with simple 1-click tools.

> Space Engineers is a trademark of Keen Software House. SEBX is a fan-made tool and is not affiliated with Keen Software House.

---

## What Can You Do With SEBX?

### 🛠️ 1. Fix Stuck Survival Projectors (Vanillafyer & Prototech Sanity)
- **DLC to Base (Vanillafy)**: Replaces all decorative DLC blocks (including the July 2026 Prosperity Pack, Contact, Signal, Automations, and Warfare) with standard base-game blocks you can build without owning DLCs.
- **Survival Projection Sanity**: Replaces salvage-only Prototech blocks with standard craftable reactors, thrusters, and batteries so your shipyard projectors weld smoothly without getting stuck.

### ⚡ 2. Upgrade Fleets to Prototech / Factorum Tier
- Turn any vanilla ship into an endgame flagship by upgrading standard reactors, thrusters, jump drives, and weapons to maximum Factorum Prototech tech with 1 click.

### 🩺 3. Built-In PB Script Doctor
- Checks embedded Programmable Block C# scripts *before* you spawn them in game.
- Catches missing `Main()` methods, unclosed braces/regions, character limit overruns (100k max), and banned commands (`System.IO`, `System.Threading`) that cause server kicks or crashes.
- Estimates per-tick instruction costs to help you avoid server lag.

### 📐 4. Subgrid Inspector & 2.5D Ship Map
- See how your ship's subgrids, rotors, hinges, and pistons are connected in a clean visual tree.
- View top-down and side profile slices of your ship showing where cockpits, thrusters, weapons, and power blocks are located.

### 🔄 5. Light <-> Heavy Armor & Component Conversions
- Swap Light Armor to Heavy Armor (or vice-versa) across 70+ block shapes with full volume matching.
- Swap standard thrusters, weapons, and functional blocks.
- Preview resource costs, PCU, mass changes, and ore requirements before saving.

### 🌐 6. Import Directly from Steam Workshop & Mod.io
- Paste a Steam Workshop link or ID to grab blueprints directly from your cache or Workshop.
- Crossplay support for Mod.io blueprint packages.

### 📏 7. Rescale Grid Size (Large <-> Small)
- Scale Large grid ships to Small grid fighters (or vice versa). Automatically recalculates block positions so blocks don't overlap or end up floating in midair.

---

## License (Simple Version)

| Use Case | Free? |
|---|---|
| Using SEBX on your own blueprints | **Yes, 100% Free** |
| Using SEBX for your private/community gaming server | **Yes, 100% Free** |
| Using SEBX in gameplay videos / Twitch streams | **Yes, 100% Free** |
| Selling SEBX or bundling it into paid products | Requires Commercial License |
| Re-uploading or repackaging SEBX binaries | Not Allowed |

Full legal terms are in [LICENSE](LICENSE).

---

## Download & Installation

1. Download the latest portable `.exe` from [GitHub Releases](https://github.com/MerabyLabs/SE-Block-Exchanger/releases).
2. Run `SE_Tactical_Command_v4.0.0.exe` (no installation required).
3. The app will automatically find your Space Engineers blueprint folder in `%APPDATA%\SpaceEngineers\Blueprints\local`.

### Running from Source (Developers)
If you prefer running via Python:
```powershell
git clone https://github.com/MerabyLabs/SE-Block-Exchanger.git
cd SE-Block-Exchanger
pip install -r requirements.txt
python gui_standalone.py
```

---

## Keyboard Shortcuts

- `Ctrl + O` : Browse blueprint directory
- `Ctrl + R` : Convert selected blueprint
- `Ctrl + Z` : Undo last conversion
- `F5` : Refresh blueprint list

---

(c) 2025–2026 Meraby Labs. All Rights Reserved.

