"""Header component."""

import os
import customtkinter as ctk
from ui.theme import TacticalTheme


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    from resource_paths import resource_path
    return str(resource_path(relative_path))


class Header(ctk.CTkFrame):
    """Header bar with branding, blueprint count, and folder actions."""

    def __init__(
        self,
        master,
        on_rescan=None,
        on_browse=None,
        on_appearance_change=None,
        on_recent_dir_select=None,
        on_open_profiles=None,
        on_show_changelog=None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=12,
            **kwargs,
        )
        self._on_rescan = on_rescan
        self._on_browse = on_browse
        self._on_appearance_change = on_appearance_change
        self._on_recent_dir_select = on_recent_dir_select
        self._on_open_profiles = on_open_profiles
        self._on_show_changelog = on_show_changelog
        self._recent_lookup = {}

        brand_frame = ctk.CTkFrame(self, fg_color="transparent")
        brand_frame.pack(side="left", padx=(14, 0), pady=10)

        self._logo_image = None
        try:
            from PIL import Image
            logo_path = get_resource_path('logo.png')
            if not os.path.exists(logo_path):
                logo_path = get_resource_path('app_icon.png')
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                target_h = 44
                aspect = img.width / img.height
                target_w = int(target_h * aspect)
                self._logo_image = ctk.CTkImage(
                    light_image=img, dark_image=img,
                    size=(target_w, target_h),
                )
                logo_label = ctk.CTkLabel(
                    brand_frame, image=self._logo_image, text="",
                )
                logo_label.pack(side="left", padx=(0, 12))
        except Exception:
            pass

        title_block = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_block.pack(side="left", fill="y")

        ctk.CTkLabel(
            title_block,
            text="SE Block Exchanger",
            font=TacticalTheme.FONT_TITLE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_block,
            text="Convert blueprints without editing XML  ·  Meraby Labs",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(side="right", padx=12, pady=10)

        self.bp_count_label = ctk.CTkLabel(
            actions, text="No blueprints yet",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.bp_count_label.pack(side="left", padx=(0, 10))

        self.recent_var = ctk.StringVar(value="Recent folders")
        self.recent_menu = ctk.CTkOptionMenu(
            actions,
            values=["Recent folders"],
            variable=self.recent_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_GLASS,
            button_hover_color=TacticalTheme.CYAN_DIM,
            dropdown_fg_color=TacticalTheme.BG_MEDIUM,
            dropdown_hover_color=TacticalTheme.BG_GLASS,
            text_color=TacticalTheme.TEXT_WHITE,
            width=170,
            command=self._on_recent_selected,
        )
        self.recent_menu.pack(side="left", padx=3)

        self.appearance_var = ctk.StringVar(value="System")
        self.appearance_menu = ctk.CTkOptionMenu(
            actions,
            values=list(TacticalTheme.APPEARANCE_MODES),
            variable=self.appearance_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_GLASS,
            button_hover_color=TacticalTheme.CYAN_DIM,
            dropdown_fg_color=TacticalTheme.BG_MEDIUM,
            dropdown_hover_color=TacticalTheme.BG_GLASS,
            text_color=TacticalTheme.TEXT_WHITE,
            width=100,
            command=self._on_appearance_changed,
        )
        self.appearance_menu.pack(side="left", padx=3)

        self._outline_button(actions, "Open folder", TacticalTheme.CYAN_PRIMARY, 110, self._on_browse)
        self._outline_button(actions, "Profiles", TacticalTheme.GREEN_PRIMARY, 90, self._on_open_profiles)
        self._outline_button(actions, "What's new", TacticalTheme.ORANGE_PRIMARY, 100, self._on_show_changelog)

        ctk.CTkButton(
            actions, text="Refresh",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            hover_color=TacticalTheme.CYAN_DIM,
            width=88, height=32,
            corner_radius=8,
            command=self._on_rescan,
        ).pack(side="left", padx=3)

    def _outline_button(self, parent, text, color, width, command):
        ctk.CTkButton(
            parent, text=text,
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=color,
            text_color=color,
            hover_color=TacticalTheme.BG_DARK,
            width=width, height=32,
            corner_radius=8,
            command=command,
        ).pack(side="left", padx=3)

    def set_blueprint_count(self, count: int):
        if count == 1:
            self.bp_count_label.configure(text="1 blueprint")
        else:
            self.bp_count_label.configure(text=f"{count} blueprints")

    def set_recent_dirs(self, directories):
        values = ["Recent folders"]
        self._recent_lookup = {}
        for idx, directory in enumerate(directories):
            short_name = directory
            if len(short_name) > 48:
                short_name = "..." + short_name[-45:]
            key = f"{idx + 1}. {short_name}"
            self._recent_lookup[key] = directory
            values.append(key)
        self.recent_menu.configure(values=values)
        self.recent_var.set(values[0])

    def set_appearance_mode(self, mode: str):
        self.appearance_var.set(TacticalTheme.normalize_appearance_mode(mode))

    def _on_recent_selected(self, value: str):
        if value == "Recent folders":
            return
        directory = self._recent_lookup.get(value)
        if directory and self._on_recent_dir_select:
            self._on_recent_dir_select(directory)

    def _on_appearance_changed(self, mode: str):
        if self._on_appearance_change:
            self._on_appearance_change(mode)
