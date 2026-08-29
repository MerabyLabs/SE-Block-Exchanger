"""
PB Script Fixer Engine.
Automatically patches and fixes common Space Engineers Programmable Block scripting errors:
- Removes forbidden namespaces (System.IO, System.Threading, System.Net, System.Reflection)
- Injects standard MDK stubs (Program constructor, Main method)
- Balances mismatched braces and missing region directives
- Provides ready-to-use template scripts for unconfigured Programmable Blocks
"""

from __future__ import annotations

import re
from typing import List, Tuple


from pb_doctor.whitelist_rules import FORBIDDEN_NAMESPACES, mask_csharp_non_code


class ScriptFixer:
    """Automated C# Ingame Script repair and modernization engine."""

    USING_LINE_REGEX = re.compile(
        r"^\s*using\s+([^;]+);\s*$",
        re.MULTILINE,
    )

    TEMPLATE_RADAR = """// Space Engineers Ingame Radar / Subsystem Monitor
public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update100;
}

public void Main(string argument, UpdateType updateSource) {
    Echo($"[RADAR ONLINE] Runtime: {DateTime.Now:T}");
    Echo($"Instructions: {Runtime.CurrentInstructionCount}/{Runtime.MaxInstructionCount}");
}

public void Save() {
    // Persistent state storage
}
"""

    TEMPLATE_AIRLOCK = """// Space Engineers Automated Airlock Controller
public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update10;
}

public void Main(string argument, UpdateType updateSource) {
    var outerDoor = GridTerminalSystem.GetBlockWithName("Outer Airlock Door") as IMyDoor;
    var innerDoor = GridTerminalSystem.GetBlockWithName("Inner Airlock Door") as IMyDoor;

    if (outerDoor != null && innerDoor != null) {
        if (outerDoor.Status == DoorStatus.Opening || outerDoor.Status == DoorStatus.Open) {
            innerDoor.CloseDoor();
        }
    }
}
"""

    TEMPLATE_LCD_STATUS = """// Ship Diagnostics LCD Dashboard
public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update100;
}

public void Main(string argument, UpdateType updateSource) {
    var lcd = GridTerminalSystem.GetBlockWithName("Bridge LCD") as IMyTextPanel;
    if (lcd == null) {
        Echo("Warning: 'Bridge LCD' text panel not found.");
        return;
    }

    var powerBlocks = new List<IMyBatteryBlock>();
    GridTerminalSystem.GetBlocksOfType(powerBlocks);

    float totalStored = 0;
    float maxStored = 0;
    foreach (var bat in powerBlocks) {
        totalStored += bat.CurrentStoredPower;
        maxStored += bat.MaxStoredPower;
    }

    float powerPct = maxStored > 0 ? (totalStored / maxStored) * 100f : 0;
    lcd.ContentType = VRage.Game.GUI.TextPanel.ContentType.TEXT_AND_IMAGE;
    lcd.WriteText($"=== VESSEL STATUS ===\\nPower: {powerPct:F1}% ({totalStored:F2}/{maxStored:F2} MWh)\\nBatteries: {powerBlocks.Count}\\nStatus: NOMINAL");
}
"""

    @classmethod
    def fix_script(cls, raw_code: str) -> Tuple[str, List[str]]:
        """
        Applies automated fixes to C# script and returns (fixed_code, list_of_fixes_applied).
        """
        if not raw_code or not raw_code.strip():
            return cls.TEMPLATE_RADAR, ["Injected standard Radar/Diagnostics template for empty Programmable Block."]

        fixes: List[str] = []
        code = raw_code

        # 1. Strip only sandbox-forbidden using directives (keep System, VRage, etc.)
        def _keep_or_drop_using(match: re.Match) -> str:
            target = match.group(1).strip()
            if cls._is_forbidden_using(target):
                return ""
            return match.group(0)

        stripped = 0
        for match in cls.USING_LINE_REGEX.finditer(code):
            if cls._is_forbidden_using(match.group(1).strip()):
                stripped += 1
        if stripped:
            code = cls.USING_LINE_REGEX.sub(_keep_or_drop_using, code)
            code = re.sub(r"\n{3,}", "\n\n", code)
            fixes.append(
                f"Removed {stripped} forbidden 'using' directive(s) (IO/threading/net/reflection)."
            )

        # 2. Check and fix missing Main()
        if not re.search(r"\bvoid\s+Main\s*\(", code, re.IGNORECASE):
            code += "\n\n// [AUTO-FIX] Added missing Main entry point\npublic void Main(string argument, UpdateType updateSource) {\n    Echo(\"PB Active\");\n}\n"
            fixes.append("Added missing void Main() entry point method.")

        # 3. Check and fix missing Program() constructor
        if not re.search(r"\bProgram\s*\(\s*\)", code):
            # Prepend constructor if Main exists
            constructor_stub = "// [AUTO-FIX] Added standard Program constructor\npublic Program() {\n    Runtime.UpdateFrequency = UpdateFrequency.Update100;\n}\n\n"
            code = constructor_stub + code
            fixes.append("Added standard public Program() constructor with UpdateFrequency.")

        # 4. Fix unbalanced braces (ignore comments and string literals)
        structure = mask_csharp_non_code(code)
        open_braces = structure.count("{")
        close_braces = structure.count("}")
        if open_braces > close_braces:
            diff = open_braces - close_braces
            code = code.rstrip() + "\n" + ("}" * diff) + "\n"
            fixes.append(f"Appended {diff} missing closing brace(s) '}}'.")

        # 5. Fix unmatched #region / #endregion
        structure = mask_csharp_non_code(code)
        open_regions = len(re.findall(r"^\s*#region\b", structure, re.MULTILINE))
        close_regions = len(re.findall(r"^\s*#endregion\b", structure, re.MULTILINE))
        if open_regions > close_regions:
            diff = open_regions - close_regions
            code = code.rstrip() + "\n" + ("#endregion\n" * diff)
            fixes.append(f"Appended {diff} missing '#endregion' directive(s).")

        return code.strip(), fixes

    @staticmethod
    def _using_target_namespace(clause: str) -> str:
        text = clause.strip()
        if text.startswith("static "):
            text = text[7:].strip()
        if "=" in text:
            text = text.split("=", 1)[1].strip()
        if text.startswith("global::"):
            text = text[8:]
        return text

    @classmethod
    def _is_forbidden_using(cls, target: str) -> bool:
        namespace = cls._using_target_namespace(target)
        for ns in FORBIDDEN_NAMESPACES:
            if namespace == ns or namespace.startswith(ns + "."):
                return True
        return False
