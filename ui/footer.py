"""Footer component."""

import customtkinter as ctk
from ui.theme import TacticalTheme
from version import __build_date__, __channel__, __version__


class Footer(ctk.CTkFrame):
    """Status bar footer with operation status and stats."""

    def __init__(self, master, on_update_click=None, **kwargs):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=12,
            height=42,
            **kwargs,
        )
        self._on_update_click = on_update_click

        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(side="left", padx=14, pady=8)

        ctk.CTkLabel(
            status_frame, text="Status",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(0, 6))

        self.status_label = ctk.CTkLabel(
            status_frame, text="Ready",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        self.status_label.pack(side="left")

        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(side="left", padx=18)

        ctk.CTkLabel(
            stats_frame, text="Scanned",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(0, 6))

        self.scanned_label = ctk.CTkLabel(
            stats_frame, text="0",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
        )
        self.scanned_label.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(
            stats_frame, text="Converted",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(0, 6))

        self.converted_label = ctk.CTkLabel(
            stats_frame, text="0",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        )
        self.converted_label.pack(side="left")

        self.update_button = ctk.CTkButton(
            self,
            text="",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            text_color=TacticalTheme.GREEN_PRIMARY,
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_DARK,
            width=240,
            height=26,
            corner_radius=8,
            command=self._on_update_click,
        )
        self.update_button.pack(side="right", padx=(6, 2))
        self.update_button.pack_forget()

        version_text = f"v{__version__}  ·  {__channel__}  ·  {__build_date__}"
        ctk.CTkLabel(
            self,
            text=version_text,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="right", padx=14)

    def set_status(self, text: str, color: str = None):
        """Update the status text."""
        self.status_label.configure(
            text=text,
            text_color=color or TacticalTheme.CYAN_PRIMARY,
        )

    def set_scanned(self, count):
        self.scanned_label.configure(text=str(count))

    def set_converted(self, count):
        self.converted_label.configure(text=str(count))

    def show_update(self, latest_version: str):
        self.update_button.configure(text=f"Update available: {latest_version}")
        self.update_button.pack(side="right", padx=(6, 2))

    def hide_update(self):
        self.update_button.pack_forget()
