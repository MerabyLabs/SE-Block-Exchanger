"""Product theme: dark cyan/orange with readable UI type."""

from __future__ import annotations

import customtkinter as ctk


class TacticalTheme:
    """Color scheme and typography for the Block Exchanger UI."""

    APPEARANCE_MODES = ("Light", "Dark", "System")

    BG_DARK = "#0b1220"
    BG_MEDIUM = "#151d2e"
    BG_GLASS = "#1a2436"
    BG_CARD = "#182234"
    CYAN_PRIMARY = "#22d3ee"
    CYAN_DIM = "#0891b2"
    ORANGE_PRIMARY = "#f59e0b"
    ORANGE_DIM = "#d97706"
    TEXT_CYAN = "#a5f3fc"
    TEXT_GRAY = "#94a3b8"
    TEXT_WHITE = "#f1f5f9"
    BORDER_CYAN = "#22d3ee"
    BORDER_ORANGE = "#fb923c"
    BORDER_SUBTLE = "#2a364a"
    GREEN_PRIMARY = "#22c55e"
    RED_PRIMARY = "#ef4444"
    TEXT_MUTED = "#64748b"
    COLOR_ARMOR = "#64748b"
    COLOR_PROPULSION = "#22d3ee"
    COLOR_WEAPONS = "#ef4444"
    COLOR_POWER = "#eab308"
    COLOR_COCKPIT = "#f59e0b"
    COLOR_UTILITY = "#8b5cf6"
    COLOR_SUBGRID = "#22c55e"
    COLOR_DLC = "#ec4899"

    UI_FONT_CANDIDATES = (
        "Inter",
        "Segoe UI",
        "Ubuntu",
        "Noto Sans",
        "Cantarell",
        "DejaVu Sans",
        "Helvetica",
    )
    MONO_FONT_CANDIDATES = (
        "JetBrains Mono",
        "Cascadia Mono",
        "Consolas",
        "DejaVu Sans Mono",
        "Courier New",
    )

    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    FONT_SMALL = ("Segoe UI", 13)
    FONT_NORMAL = ("Segoe UI", 15)
    FONT_LARGE = ("Segoe UI", 18, "bold")
    FONT_TITLE = ("Segoe UI", 22, "bold")
    FONT_HEADER = ("Segoe UI", 24, "bold")
    FONT_MONO_SMALL = ("Consolas", 14)
    FONT_CODE = ("Consolas", 14)
    FONT_CODE_SMALL = ("Consolas", 14)

    @classmethod
    def normalize_appearance_mode(cls, mode: str) -> str:
        if not mode:
            return "System"
        normalized = mode.strip().capitalize()
        return normalized if normalized in cls.APPEARANCE_MODES else "System"

    @classmethod
    def apply(cls, appearance_mode: str = "System") -> None:
        """Configure CustomTkinter appearance for the product theme."""
        ctk.set_appearance_mode(cls.normalize_appearance_mode(appearance_mode))
        ctk.set_default_color_theme("dark-blue")

    @classmethod
    def resolve_fonts(cls) -> None:
        """Pick installed UI/mono families after a Tk root exists."""
        try:
            import tkinter.font as tkfont

            families = set(tkfont.families())
        except Exception:
            return

        for name in cls.UI_FONT_CANDIDATES:
            if name in families:
                cls.FONT_FAMILY = name
                break
        for name in cls.MONO_FONT_CANDIDATES:
            if name in families:
                cls.FONT_MONO = name
                break

        cls.FONT_SMALL = (cls.FONT_FAMILY, 13)
        cls.FONT_NORMAL = (cls.FONT_FAMILY, 15)
        cls.FONT_LARGE = (cls.FONT_FAMILY, 18, "bold")
        cls.FONT_TITLE = (cls.FONT_FAMILY, 22, "bold")
        cls.FONT_HEADER = (cls.FONT_FAMILY, 24, "bold")
        cls.FONT_MONO_SMALL = (cls.FONT_MONO, 14)
        cls.FONT_CODE = (cls.FONT_MONO, 14)
        cls.FONT_CODE_SMALL = (cls.FONT_MONO, 14)

    @classmethod
    def panel_kwargs(cls) -> dict:
        return {
            "fg_color": cls.BG_MEDIUM,
            "border_width": 1,
            "border_color": cls.BORDER_SUBTLE,
            "corner_radius": 12,
        }

    @classmethod
    def card_kwargs(cls) -> dict:
        return {
            "fg_color": cls.BG_GLASS,
            "border_width": 1,
            "border_color": cls.BORDER_SUBTLE,
            "corner_radius": 10,
        }
