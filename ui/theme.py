"""Tactical Command Theme System."""

from __future__ import annotations

import customtkinter as ctk


class TacticalTheme:
    """Tactical hologram color scheme, modern typography, and styling constants."""

    APPEARANCE_MODES = ("Light", "Dark", "System")

    # Background surfaces
    BG_DARK = "#0b1324"
    BG_MEDIUM = "#131f37"
    BG_GLASS = "#1a2a47"
    BG_CARD = "#16243d"
    BG_HOVER = "#23385d"

    # Tactical neon accents
    CYAN_PRIMARY = "#06b6d4"
    CYAN_DIM = "#0891b2"
    CYAN_GLOW = "#38bdf8"
    ORANGE_PRIMARY = "#f59e0b"
    ORANGE_DIM = "#d97706"
    GREEN_PRIMARY = "#10b981"
    GREEN_DIM = "#059669"
    RED_PRIMARY = "#ef4444"
    RED_DIM = "#dc2626"
    YELLOW_PRIMARY = "#eab308"
    PURPLE_PRIMARY = "#8b5cf6"
    PINK_PRIMARY = "#ec4899"

    # Text colors
    TEXT_CYAN = "#7dd3fc"
    TEXT_WHITE = "#f8fafc"
    TEXT_GRAY = "#94a3b8"
    TEXT_MUTED = "#64748b"

    # Borders
    BORDER_CYAN = "#0ea5e9"
    BORDER_ORANGE = "#f97316"
    BORDER_SUBTLE = "#1e293b"

    # Subsystem category badges & canvas colors
    COLOR_ARMOR = "#475569"
    COLOR_PROPULSION = "#06b6d4"
    COLOR_WEAPONS = "#ef4444"
    COLOR_POWER = "#eab308"
    COLOR_COCKPIT = "#f59e0b"
    COLOR_UTILITY = "#8b5cf6"
    COLOR_SUBGRID = "#10b981"
    COLOR_DLC = "#ec4899"

    # Typography (Modern, crisp, high-legibility sans-serif)
    FONT_FAMILY = "Segoe UI"
    FONT_SMALL = ("Segoe UI", 11)
    FONT_NORMAL = ("Segoe UI", 12)
    FONT_LARGE = ("Segoe UI", 14, "bold")
    FONT_TITLE = ("Segoe UI", 18, "bold")
    FONT_HEADER = ("Segoe UI", 21, "bold")

    # Code / Monospace typography for XML & C# scripts
    FONT_CODE = ("Consolas", 11)
    FONT_CODE_SMALL = ("Consolas", 10)
    FONT_CODE_BOLD = ("Consolas", 11, "bold")

    @classmethod
    def normalize_appearance_mode(cls, mode: str) -> str:
        if not mode:
            return "System"
        normalized = mode.strip().capitalize()
        return normalized if normalized in cls.APPEARANCE_MODES else "System"

    @classmethod
    def apply(cls, appearance_mode: str = "System") -> None:
        """Configure CustomTkinter appearance for tactical theme."""
        ctk.set_appearance_mode(cls.normalize_appearance_mode(appearance_mode))
        ctk.set_default_color_theme("dark-blue")
