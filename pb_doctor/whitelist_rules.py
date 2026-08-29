import re
from typing import Set, Tuple, List, Pattern

# Character limits in Space Engineers PB
MAX_PROGRAM_CHARACTERS = 100_000
RECOMMENDED_SAFE_CHARACTERS = 80_000

# Estimated instruction budget per tick in SE (soft threshold ~45,000, hard crash at 50,000)
ESTIMATED_INSTRUCTION_LIMIT = 49_500
INSTRUCTION_WARNING_THRESHOLD = 35_000

# Strictly forbidden namespaces in PB sandboxed environment
FORBIDDEN_NAMESPACES: Set[str] = {
    "System.IO",
    "System.Threading",
    "System.Reflection",
    "System.Net",
    "System.Net.Sockets",
    "System.Diagnostics",
    "System.Runtime",
    "System.Runtime.InteropServices",
    "System.Security",
    "System.Timers",
    "System.Environment",
    "System.AppDomain",
    "System.Management",
    "Microsoft.Win32",
}

# Precompiled namespace regexes for high-performance line scanning
COMPILED_FORBIDDEN_NAMESPACES: List[Tuple[Pattern, str]] = [
    (re.compile(r"\b" + re.escape(ns) + r"\b"), ns) for ns in sorted(FORBIDDEN_NAMESPACES)
]

# Forbidden keywords / patterns raw definitions
FORBIDDEN_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\bnamespace\s+[A-Za-z0-9_]+", "Namespaces cannot be declared inside a PB script.", "Remove the namespace wrapper."),
    (r"\busing\s+[A-Za-z0-9_.]+\s*;", "Using directives cannot be placed inside PB scripts directly.", "Remove using directives and use fully qualified type names if needed."),
    (r"\basync\b", "Async methods are not supported in the PB sandbox.", "Use state machines with Runtime.UpdateFrequency instead of async/await."),
    (r"\bawait\b", "Await expressions are forbidden in PB scripts.", "Use sequential state execution in Main(string argument, UpdateType updateSource)."),
    (r"\bdynamic\b", "Dynamic typing is prohibited in PB scripts.", "Use strong typing or object casts."),
    (r"\bgoto\b", "Goto statements are considered hazardous in PB runtime.", "Refactor into standard loops or methods."),
    (r"\bThread\b", "Direct threading is prohibited.", "Space Engineers runs PB scripts deterministically on the game thread."),
    (r"…", "Unicode ellipsis detected ('…'). This causes invalid token compiler syntax errors.", "Replace '…' with standard code or three periods '...'."),
]

# Precompiled forbidden patterns
COMPILED_FORBIDDEN_PATTERNS: List[Tuple[Pattern, str, str]] = [
    (re.compile(pattern), msg, suggestion) for pattern, msg, suggestion in FORBIDDEN_PATTERNS
]

# Precompiled entry points & structure regexes
RE_REGION_OPEN = re.compile(r"^\s*#region\b", re.MULTILINE)
RE_REGION_CLOSE = re.compile(r"^\s*#endregion\b", re.MULTILINE)
RE_PROGRAM_CTOR = re.compile(r"\b(?:public\s+)?Program\s*\(\s*\)")
RE_MAIN_METHOD = re.compile(r"\b(?:public\s+)?void\s+Main\s*\(")
RE_SAVE_METHOD = re.compile(r"\b(?:public\s+)?void\s+Save\s*\(\s*\)")

# Precompiled instruction estimation patterns
RE_LOOPS = re.compile(r"\b(for|foreach|while|do)\b")
RE_CONDITIONALS = re.compile(r"\b(if|switch|case|\?)\b")
RE_METHOD_CALLS = re.compile(r"\b[A-Za-z0-9_]+\s*\(")
RE_ALLOCATIONS = re.compile(r"\bnew\s+[A-Za-z0-9_]+")
RE_LINQ = re.compile(r"\b(Select|Where|OrderBy|GroupBy|ToList|ToArray)\b")

# Standard allowed namespaces in Space Engineers Ingame API
ALLOWED_INGAME_NAMESPACES: Set[str] = {
    "Sandbox.ModAPI.Ingame",
    "Sandbox.ModAPI.Interfaces",
    "VRage.Game.ModAPI.Ingame",
    "VRage.Game.ModAPI.Ingame.Utilities",
    "VRage.Game.GUI.TextPanel",
    "VRageMath",
    "System",
    "System.Collections.Generic",
    "System.Text",
    "System.Text.RegularExpressions",
    "System.Linq",
}
