"""Blueprint card widget — one ship in the left-hand list."""

import customtkinter as ctk

from ui.labels import card_status_label, convertible_total
from ui.theme import TacticalTheme


class BlueprintCard(ctk.CTkFrame):
    """A styled card widget representing a single blueprint."""

    def __init__(self, master, bp_info, index: int, on_select=None, **kwargs):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=10,
            cursor="hand2",
            **kwargs,
        )
        self.bp_info = bp_info
        self.index = index
        self._on_select = on_select
        self._selected = False

        self.columnconfigure(2, weight=1)

        is_large = bp_info.grid_size == "Large"
        badge_color = TacticalTheme.ORANGE_PRIMARY if is_large else TacticalTheme.CYAN_PRIMARY
        grid_letter = (bp_info.grid_size or "?")[0]

        thumbnail = ctk.CTkFrame(
            self,
            width=44,
            height=44,
            corner_radius=8,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=badge_color,
        )
        thumbnail.grid(row=0, column=0, rowspan=3, padx=(10, 8), pady=10, sticky="n")
        ctk.CTkLabel(
            thumbnail,
            text=grid_letter,
            font=TacticalTheme.FONT_LARGE,
            text_color=badge_color,
        ).place(relx=0.5, rely=0.5, anchor="center")

        badge = ctk.CTkLabel(
            self,
            text=bp_info.grid_size or "Unknown",
            width=64,
            height=20,
            corner_radius=6,
            fg_color=badge_color,
            text_color=TacticalTheme.BG_DARK,
            font=TacticalTheme.FONT_SMALL,
        )
        badge.grid(row=0, column=1, padx=(0, 6), pady=(10, 0), sticky="w")

        name_label = ctk.CTkLabel(
            self,
            text=bp_info.display_name,
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
            anchor="w",
        )
        name_label.grid(row=0, column=2, sticky="ew", padx=(0, 10), pady=(10, 0))

        stats_text = (
            f"{bp_info.block_count} blocks  ·  "
            f"{bp_info.light_armor_count} light  ·  {bp_info.heavy_armor_count} heavy"
        )
        stats_label = ctk.CTkLabel(
            self,
            text=stats_text,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            anchor="w",
        )
        stats_label.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=(2, 0))

        ready = convertible_total(bp_info)
        status_text = card_status_label(ready, scanned=True)
        status_color = TacticalTheme.GREEN_PRIMARY if ready > 0 else TacticalTheme.TEXT_GRAY
        status_label = ctk.CTkLabel(
            self,
            text=status_text,
            font=TacticalTheme.FONT_SMALL,
            text_color=status_color,
            anchor="w",
        )
        status_label.grid(row=2, column=1, columnspan=2, sticky="w", padx=(0, 10), pady=(0, 10))

        for widget in [self, thumbnail, badge, name_label, stats_label, status_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Control-Button-1>", self._on_ctrl_click)

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
            self.configure(border_color=TacticalTheme.BORDER_SUBTLE)

    def set_selected(self, selected: bool):
        """Update the card's visual selection state."""
        self._selected = selected
        if selected:
            self.configure(
                border_color=TacticalTheme.ORANGE_PRIMARY,
                border_width=2,
                fg_color="#1f2a3d",
            )
        else:
            self.configure(
                border_color=TacticalTheme.BORDER_SUBTLE,
                border_width=1,
                fg_color=TacticalTheme.BG_CARD,
            )
