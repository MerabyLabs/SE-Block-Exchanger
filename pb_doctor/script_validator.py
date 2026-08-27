"""
Programmable Block (PB) Script Validator and Compliance Checker.
Analyzes C# code embedded in Space Engineers blueprints against in-game sandbox rules.
"""

from __future__ import annotations
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Optional
from pb_doctor.whitelist_rules import (
    MAX_PROGRAM_CHARACTERS,
    RECOMMENDED_SAFE_CHARACTERS,
    ESTIMATED_INSTRUCTION_LIMIT,
    INSTRUCTION_WARNING_THRESHOLD,
    COMPILED_FORBIDDEN_NAMESPACES,
    COMPILED_FORBIDDEN_PATTERNS,
    RE_REGION_OPEN,
    RE_REGION_CLOSE,
    RE_PROGRAM_CTOR,
    RE_MAIN_METHOD,
    RE_SAVE_METHOD,
    RE_LOOPS,
    RE_CONDITIONALS,
    RE_METHOD_CALLS,
    RE_ALLOCATIONS,
    RE_LINQ,
)


@dataclass
class PBDiagnostic:
    """Represents an issue found during PB script analysis."""
    severity: str  # "Error", "Warning", "Info"
    rule_id: str
    line_number: Optional[int]
    message: str
    suggestion: str


@dataclass
class PBScriptReport:
    """Comprehensive compliance and health report for a PB script."""
    script_name: str
    is_valid: bool
    compliance_score: int  # 0 to 100
    character_count: int
    line_count: int
    estimated_instructions: int
    has_program_constructor: bool
    has_main_method: bool
    has_save_method: bool
    diagnostics: List[PBDiagnostic] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "Error")

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "Warning")


class PBScriptValidator:
    """Validates Programmable Block C# scripts against Space Engineers sandbox rules."""

    @classmethod
    def validate_script(cls, script_name: str, code: str) -> PBScriptReport:
        diagnostics: List[PBDiagnostic] = []

        if not code or not code.strip():
            diagnostics.append(
                PBDiagnostic(
                    severity="Warning",
                    rule_id="EMPTY_SCRIPT",
                    line_number=None,
                    message="Programmable block has empty script code.",
                    suggestion="Paste a valid Space Engineers C# script or load from an MDK template.",
                )
            )
            return PBScriptReport(
                script_name=script_name,
                is_valid=True,
                compliance_score=100,
                character_count=0,
                line_count=0,
                estimated_instructions=0,
                has_program_constructor=False,
                has_main_method=False,
                has_save_method=False,
                diagnostics=diagnostics,
            )

        char_count = len(code)
        lines = code.splitlines()
        line_count = len(lines)

        # 1. Character limit checks
        if char_count > MAX_PROGRAM_CHARACTERS:
            diagnostics.append(
                PBDiagnostic(
                    severity="Error",
                    rule_id="CHAR_LIMIT_EXCEEDED",
                    line_number=None,
                    message=f"Script length ({char_count:,} chars) exceeds the in-game PB limit ({MAX_PROGRAM_CHARACTERS:,}).",
                    suggestion="Minify your code using SEBX Minifier or split logic across multiple Programmable Blocks.",
                )
            )
        elif char_count > RECOMMENDED_SAFE_CHARACTERS:
            diagnostics.append(
                PBDiagnostic(
                    severity="Warning",
                    rule_id="CHAR_LIMIT_HIGH",
                    line_number=None,
                    message=f"Script is close to character limit ({char_count:,} / {MAX_PROGRAM_CHARACTERS:,} chars).",
                    suggestion="Consider minifying before pasting into multiplayer servers.",
                )
            )

        # 2. Brace and Region balance
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            diagnostics.append(
                PBDiagnostic(
                    severity="Error",
                    rule_id="UNBALANCED_BRACES",
                    line_number=None,
                    message=f"Unbalanced braces detected: {open_braces} '{{' vs {close_braces} '}}'.",
                    suggestion="Ensure all opened classes, methods, and blocks have matching closing braces.",
                )
            )

        open_regions = len(RE_REGION_OPEN.findall(code))
        close_regions = len(RE_REGION_CLOSE.findall(code))
        if open_regions != close_regions:
            diagnostics.append(
                PBDiagnostic(
                    severity="Error",
                    rule_id="UNBALANCED_REGIONS",
                    line_number=None,
                    message=f"Unbalanced preprocessor directives: {open_regions} #region vs {close_regions} #endregion.",
                    suggestion="Ensure every #region is properly closed with #endregion.",
                )
            )

        # 3. Forbidden namespaces and patterns per line (precompiled)
        for idx, line in enumerate(lines, 1):
            for regex, ns in COMPILED_FORBIDDEN_NAMESPACES:
                if regex.search(line):
                    diagnostics.append(
                        PBDiagnostic(
                            severity="Error",
                            rule_id="FORBIDDEN_NAMESPACE",
                            line_number=idx,
                            message=f"Disallowed namespace or type reference '{ns}' detected.",
                            suggestion="Space Engineers sandboxes PB scripts. Use allowed Ingame APIs or in-memory state instead.",
                        )
                    )

            for regex, msg, suggestion in COMPILED_FORBIDDEN_PATTERNS:
                if regex.search(line):
                    diagnostics.append(
                        PBDiagnostic(
                            severity="Error" if "Unicode" in msg or "Async" in msg or "Dynamic" in msg or "Namespace" in msg else "Warning",
                            rule_id="FORBIDDEN_SYNTAX",
                            line_number=idx,
                            message=msg,
                            suggestion=suggestion,
                        )
                    )

        # 4. Entry point detection
        has_program = bool(RE_PROGRAM_CTOR.search(code))
        has_main = bool(RE_MAIN_METHOD.search(code))
        has_save = bool(RE_SAVE_METHOD.search(code))

        if not has_main:
            diagnostics.append(
                PBDiagnostic(
                    severity="Error",
                    rule_id="MISSING_MAIN",
                    line_number=None,
                    message="No 'void Main(...)' entry point found in script.",
                    suggestion="Add 'public void Main(string argument, UpdateType updateSource)' to allow script execution.",
                )
            )

        # 5. Static instruction complexity estimation
        estimated_instructions = cls._estimate_instructions(code)
        if estimated_instructions > ESTIMATED_INSTRUCTION_LIMIT:
            diagnostics.append(
                PBDiagnostic(
                    severity="Warning",
                    rule_id="INSTRUCTION_LIMIT_EXCEEDED",
                    line_number=None,
                    message=f"Estimated per-tick instruction cost (~{estimated_instructions:,}) exceeds server limit (~{ESTIMATED_INSTRUCTION_LIMIT:,}).",
                    suggestion="Spread heavy calculations over multiple ticks using Runtime.UpdateFrequency or state machines.",
                )
            )
        elif estimated_instructions > INSTRUCTION_WARNING_THRESHOLD:
            diagnostics.append(
                PBDiagnostic(
                    severity="Info",
                    rule_id="INSTRUCTION_LIMIT_HIGH",
                    line_number=None,
                    message=f"High estimated instruction cost (~{estimated_instructions:,} / {ESTIMATED_INSTRUCTION_LIMIT:,}).",
                    suggestion="Check loops and large collections to avoid server lag or PB overruns.",
                )
            )

        # Calculate compliance score
        errors = sum(1 for d in diagnostics if d.severity == "Error")
        warnings = sum(1 for d in diagnostics if d.severity == "Warning")
        score = max(0, 100 - (errors * 35) - (warnings * 10))

        return PBScriptReport(
            script_name=script_name,
            is_valid=(errors == 0),
            compliance_score=score,
            character_count=char_count,
            line_count=line_count,
            estimated_instructions=estimated_instructions,
            has_program_constructor=has_program,
            has_main_method=has_main,
            has_save_method=has_save,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _estimate_instructions(code: str) -> int:
        """Lightweight static heuristic estimation for PB instruction load."""
        instructions = 500  # Base boilerplate overhead
        
        loops = len(RE_LOOPS.findall(code))
        conditionals = len(RE_CONDITIONALS.findall(code))
        method_calls = len(RE_METHOD_CALLS.findall(code))
        allocations = len(RE_ALLOCATIONS.findall(code))
        linq_usages = len(RE_LINQ.findall(code))

        instructions += (loops * 2500)
        instructions += (conditionals * 150)
        instructions += (method_calls * 40)
        instructions += (allocations * 200)
        instructions += (linq_usages * 800)

        return min(instructions, 100_000)

