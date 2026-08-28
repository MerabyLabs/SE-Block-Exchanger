"""
Blueprint Card Widget
Rich card representation for blueprints in the list panel
"""

import customtkinter as ctk
from ui.theme import TacticalTheme


class BlueprintCard(ctk.CTkFrame):
    """A styled card widget representing a single blueprint."""

    def __init__(self, master, bp_info, index: int, on_select=None, **kwargs):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BG_MEDIUM,
            corner_radius=6,
            cursor="hand2",
            **kwargs,
        )
        self.bp_info = bp_info
        self.index = index
        self._on_select = on_select
        self._selected = False

        self.columnconfigure(2, weight=1)

        thumbnail = ctk.CTkFrame(
            self,
            width=42,
            height=42,
            corner_radius=6,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
        )
        thumbnail.grid(row=0, column=0, rowspan=3, padx=(8, 6), pady=8, sticky="n")
        ctk.CTkLabel(
            thumbnail,
            text=bp_info.grid_size[0] if bp_info.grid_size else "?",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY if bp_info.grid_size == "Large" else TacticalTheme.CYAN_PRIMARY,
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Grid size badge
        badge_color = TacticalTheme.ORANGE_PRIMARY if bp_info.grid_size == "Large" else TacticalTheme.CYAN_PRIMARY
        badge = ctk.CTkLabel(
            self,
            text=bp_info.grid_size.upper() if bp_info.grid_size else "UNK",
            width=68,
            height=20,
            corner_radius=4,
            fg_color=badge_color,
            text_color=TacticalTheme.BG_DARK,
            font=TacticalTheme.FONT_SMALL,
        )
        badge.grid(row=0, column=1, padx=(0, 6), pady=(8, 0), sticky="w")

        # Blueprint name
        name_label = ctk.CTkLabel(
            self,
            text=bp_info.display_name,
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
            anchor="w",
        )
        name_label.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(8, 0))

        # Stats row
        stats_text = (
            f"{bp_info.block_count} blocks  |  "
            f"{bp_info.light_armor_count} LA  |  {bp_info.heavy_armor_count} HA"
        )
        stats_label = ctk.CTkLabel(
            self,
            text=stats_text,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            anchor="w",
        )
        stats_label.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 0))

        convertible = bp_info.light_armor_count + bp_info.heavy_armor_count
        status_text = "READY" if convertible > 0 else "NO TARGETS"
        status_color = TacticalTheme.GREEN_PRIMARY if convertible > 0 else TacticalTheme.TEXT_GRAY
        status_label = ctk.CTkLabel(
            self,
            text=status_text,
            font=TacticalTheme.FONT_SMALL,
            text_color=status_color,
            anchor="w",
        )
        status_label.grid(row=2, column=1, columnspan=2, sticky="w", padx=(0, 8), pady=(0, 8))

        # Bind click events on the whole card and children
        for widget in [self, thumbnail, badge, name_label, stats_label, status_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Control-Button-1>", self._on_ctrl_click)

        # Hover effects
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_click(self, event):
        if self._on_select:
            self._on_select(self.index, multi=False)

    def _on_ctrl_click(self, event):
        if self._on_select:
            self._on_select(self.index, multi=True)
        return "break"

    def _on_enter(self, event):
        if not self._selected:
            self.configure(border_color=TacticalTheme.CYAN_DIM)

    def _on_leave(self, event):
        if not self._selected:
            self.configure(border_color=TacticalTheme.BG_MEDIUM)

    def set_selected(self, selected: bool):
        """Update the card's visual selection state."""
        self._selected = selected
        if selected:
            self.configure(
                border_color=TacticalTheme.ORANGE_PRIMARY,
                border_width=2,
            )
        else:
            self.configure(
                border_color=TacticalTheme.BG_MEDIUM,
                border_width=1,
            )
