# Space Engineers Tactical Command (SEBX) — Installation & Setup Guide

Welcome to **Space Engineers Tactical Command**! This guide covers everything you need to get up and running in under 60 seconds.

---

## ⚡ Option 1: Standalone Windows App (Recommended for Gamers)

No Python or developer tools required.

1. **Download**:
   - Go to [GitHub Releases](https://github.com/MerabyLabs/SE-Block-Exchanger/releases).
   - Download the latest `SE_Tactical_Command_v4.0.0.exe` or `SE_Tactical_Command_v4.0.0_Portable.zip`.
2. **Launch**:
   - If you downloaded the portable zip, extract it to any folder (e.g. `D:\Games\SE-Block-Exchanger`).
   - Double-click **`SE Tactical Command.bat`** or `SE_Tactical_Command_v4.0.0.exe`.
3. **Pin to Desktop**:
   - Double-click **`Create Desktop Shortcut.bat`** in the folder.
   - A shortcut with the custom Space Engineers armor icon will immediately appear on your Windows Desktop!

---

## 🐍 Option 2: Running from Source (Modders & Developers)

If you want to run from source or customize mapping profiles:

### Prerequisites:
- Python 3.10, 3.11, 3.12, or 3.13 installed ([python.org](https://www.python.org/downloads/)).
- Git ([git-scm.com](https://git-scm.com/)).

### Steps:
```powershell
# 1. Clone the repository
git clone https://github.com/MerabyLabs/SE-Block-Exchanger.git
cd SE-Block-Exchanger

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create desktop shortcut (optional)
powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1

# 4. Launch the application
python main.py
```

---

## 📁 Blueprint Folder Configuration

By default, SEBX automatically discovers your local Space Engineers blueprint directory:
- **Default Path**: `%APPDATA%\SpaceEngineers\Blueprints\local`
- **Workshop Cache**: `%APPDATA%\SpaceEngineers\Blueprints\workshop`

### Custom Blueprint Directory:
If your Space Engineers blueprints are stored on a different drive or dedicated server folder:
1. Open the application.
2. Click **Browse Directory** in the top header or press `Ctrl + O`.
3. Select your custom folder. SEBX will remember this path in your recent directories list.

---

## 🛠️ Features Overview & How-To

### 🎯 Selective Block Exchanging (Pick & Choose)
1. Select any blueprint in the left panel.
2. Click the **SELECTIVE EXCHANGE** tab in the center panel.
3. Check the specific blocks you want to replace.
4. (Optional) Customize the target replacement block in the text box.
5. Click **EXCHANGE SELECTED BLOCKS >>**. A new prefixed blueprint will appear in your blueprints list ready to paste in game!

### 🚀 Space Engineers 2 (VRAGE3) Export
1. Select your blueprint.
2. Click the **SE2 TRANSITION** tab.
3. Review your ship's transition score, script complexity, and subgrid density.
4. Click **EXPORT TO SPACE ENGINEERS 2 (VRAGE3 JSON)**.

### 🩺 Programmable Block (PB) Doctor
1. Click the **PB DOCTOR** tab.
2. Review syntax compliance, banned namespace checks (`System.IO`), and estimated instruction counts per tick.

---

## ❓ Troubleshooting

- **Error: "No module named customtkinter"**:
  Run `pip install -r requirements.txt` in your command line.
- **Can't find bp.sbc**:
  Ensure you selected a valid Space Engineers blueprint folder. Blueprint folders contain a `bp.sbc` file and optionally a `thumb.png`.
- **Projector won't weld Prototech**:
  Open the blueprint in SEBX, switch to the **SE2 TRANSITION** tab, and click **SURVIVAL SANITY (STRIP PROTOTECH)**.
