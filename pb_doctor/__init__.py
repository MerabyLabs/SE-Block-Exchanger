"""
PB Script Doctor package.
Provides embedded script extraction, compliance diagnostics, and in-game whitelist auditing.
"""

from pb_doctor.script_extractor import PBScriptExtractor, ExtractedPBScript
from pb_doctor.script_validator import PBScriptValidator, PBScriptReport, PBDiagnostic
from pb_doctor.whitelist_rules import (
    MAX_PROGRAM_CHARACTERS,
    ESTIMATED_INSTRUCTION_LIMIT,
    FORBIDDEN_NAMESPACES,
    ALLOWED_INGAME_NAMESPACES,
)

__all__ = [
    "PBScriptExtractor",
    "ExtractedPBScript",
    "PBScriptValidator",
    "PBScriptReport",
    "PBDiagnostic",
    "MAX_PROGRAM_CHARACTERS",
    "ESTIMATED_INSTRUCTION_LIMIT",
    "FORBIDDEN_NAMESPACES",
    "ALLOWED_INGAME_NAMESPACES",
]
