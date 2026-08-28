"""
Control Panel Component
Right panel with blueprint details, exchange visualization, and conversion controls
"""

import customtkinter as ctk
from ui.theme import TacticalTheme
from ui.widgets.progress_ring import ProgressRing
from se_armor_replacer import ArmorBlockReplacer


class ControlPanel(ctk.CTkFrame):
    """Right panel with details, exchange visualization, and conversion controls."""

    def __init__(
        self,
        master,
        on_convert=None,
        on_batch_convert=None,
        on_mode_change=None,
        on_categories_change=None,
        on_undo=None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            corner_radius=8,
            **kwargs,
        )
        self._on_convert = on_convert
        self._on_batch_convert = on_batch_convert
        self._on_mode_change = on_mode_change
        self._on_categories_change = on_categories_change
        self._on_undo = on_undo
        self._category_vars = {}

        # Main scrollable container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)

        # --- DETAILS SECTION ---
        details_frame = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1, border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
        )
        details_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            details_frame, text=">> SELECTED BLUEPRINT",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(pady=(8, 4))

        info_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        info_frame.pack(fill="x", padx=16, pady=(0, 12))
        info_frame.columnconfigure(1, weight=1)

        self.detail_labels = {}
        fields = [
            ("NAME:", "name", TacticalTheme.CYAN_PRIMARY),
            ("GRID SIZE:", "grid", TacticalTheme.CYAN_PRIMARY),
            ("TOTAL BLOCKS:", "blocks", TacticalTheme.CYAN_PRIMARY),
            ("LIGHT ARMOR:", "light_armor", TacticalTheme.ORANGE_PRIMARY),
            ("HEAVY ARMOR:", "heavy_armor", TacticalTheme.CYAN_PRIMARY),
            ("MAPPINGS:", "mappings", TacticalTheme.CYAN_PRIMARY),
        ]

        for i, (label_text, key, color) in enumerate(fields):
            ctk.CTkLabel(
                info_frame, text=label_text,
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.TEXT_GRAY,
            ).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)

            value_label = ctk.CTkLabel(
                info_frame, text="--",
                font=TacticalTheme.FONT_NORMAL,
                text_color=color,
                anchor="w",
            )
            value_label.grid(row=i, column=1, sticky="ew", pady=2)
            self.detail_labels[key] = value_label

        # --- EXCHANGE VISUALIZATION ---
        exchange_frame = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1, border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
        )
        exchange_frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(
            exchange_frame, text=">> ARMOR EXCHANGE PROCESS",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(pady=(8, 4))

        cols = ctk.CTkFrame(exchange_frame, fg_color="transparent")
        cols.pack(fill="x", padx=12, pady=(0, 12))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(2, weight=1)

        # Standard column
        std_frame = ctk.CTkFrame(cols, fg_color=TacticalTheme.BG_DARK,
                                  border_width=1, border_color=TacticalTheme.CYAN_DIM,
                                  corner_radius=4)
        std_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        ctk.CTkLabel(std_frame, text="STANDARD",
                     font=TacticalTheme.FONT_NORMAL,
                     text_color=TacticalTheme.CYAN_PRIMARY).pack(pady=(6, 2))
        for txt in ["> LightArmor...", "> Slope", "> Corner", "> Panel"]:
            ctk.CTkLabel(std_frame, text=txt, font=TacticalTheme.FONT_SMALL,
                         text_color=TacticalTheme.TEXT_GRAY).pack(pady=0)
        self.light_count_label = ctk.CTkLabel(
            std_frame, text="0 BLOCKS",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        )
        self.light_count_label.pack(pady=(4, 8))

        # Arrow
        ctk.CTkLabel(cols, text="\u25B6\u25B6\u25B6",
                     font=TacticalTheme.FONT_TITLE,
                     text_color=TacticalTheme.ORANGE_PRIMARY).grid(row=0, column=1, padx=4)

        # Heavy column
        heavy_frame = ctk.CTkFrame(cols, fg_color=TacticalTheme.BG_DARK,
                                    border_width=2, border_color=TacticalTheme.ORANGE_PRIMARY,
                                    corner_radius=4)
        heavy_frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        ctk.CTkLabel(heavy_frame, text="HEAVY",
                     font=TacticalTheme.FONT_NORMAL,
                     text_color=TacticalTheme.ORANGE_PRIMARY).pack(pady=(6, 2))
        for txt in ["> HeavyArmor...", "> Slope", "> Corner", "> Panel"]:
            ctk.CTkLabel(heavy_frame, text=txt, font=TacticalTheme.FONT_SMALL,
                         text_color=TacticalTheme.ORANGE_DIM).pack(pady=0)
        self.heavy_count_label = ctk.CTkLabel(
            heavy_frame, text="0 BLOCKS",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        )
        self.heavy_count_label.pack(pady=(4, 8))

        # --- CONVERSION MODE ---
        mode_frame = ctk.CTkFrame(container, fg_color="transparent")
        mode_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            mode_frame, text="CONVERSION MODE:",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(anchor="w", padx=4, pady=(0, 4))

        btn_row = ctk.CTkFrame(mode_frame, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        self.mode_lth_btn = ctk.CTkButton(
            btn_row, text="LIGHT \u2192 HEAVY",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            hover_color=TacticalTheme.ORANGE_DIM,
            corner_radius=4, height=30,
            command=lambda: self._set_mode("light_to_heavy"),
        )
        self.mode_lth_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.mode_htl_btn = ctk.CTkButton(
            btn_row, text="HEAVY \u2192 LIGHT",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4, height=30,
            command=lambda: self._set_mode("heavy_to_light"),
        )
        self.mode_htl_btn.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # --- CATEGORY TOGGLES ---
        category_frame = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
        )
        category_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            category_frame,
            text=">> MAPPING CATEGORIES",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self.category_checks_frame = ctk.CTkFrame(category_frame, fg_color="transparent")
        self.category_checks_frame.pack(fill="x", padx=8, pady=(0, 8))

        # --- PROGRESS ---
        self.progress = ProgressRing(container)
        self.progress.pack(fill="x", padx=8)

        # --- CONVERT BUTTON ---
        self.convert_btn = ctk.CTkButton(
            container, text="INITIATE CONVERSION",
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.BG_GLASS,
            border_width=2,
            border_color=TacticalTheme.ORANGE_PRIMARY,
            corner_radius=6, height=48,
            state="disabled",
            command=self._convert,
        )
        self.convert_btn.pack(fill="x", padx=8, pady=(8, 4))

        # --- BATCH BUTTON ---
        self.batch_btn = ctk.CTkButton(
            container, text="BATCH CONVERT SELECTED",
            font=TacticalTheme.FONT_NORMAL,
            fg_color="transparent",
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            corner_radius=6, height=36,
            command=self._batch_convert,
        )
        self.batch_btn.pack(fill="x", padx=8, pady=(0, 8))

        self.undo_btn = ctk.CTkButton(
            container,
            text="UNDO LAST CONVERSION",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            text_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            corner_radius=6,
            height=34,
            command=self._undo,
        )
        self.undo_btn.pack(fill="x", padx=8, pady=(0, 8))

    def _set_mode(self, mode: str):
        if mode == "light_to_heavy":
            self.mode_lth_btn.configure(
                fg_color=TacticalTheme.ORANGE_PRIMARY,
                text_color=TacticalTheme.BG_DARK,
                border_width=0,
            )
            self.mode_htl_btn.configure(
                fg_color=TacticalTheme.BG_DARK,
                text_color=TacticalTheme.CYAN_PRIMARY,
                border_width=1,
            )
            self.convert_btn.configure(
                text="CONVERT TO HEAVY",
                text_color=TacticalTheme.ORANGE_PRIMARY,
                border_color=TacticalTheme.ORANGE_PRIMARY,
            )
        else:
            self.mode_lth_btn.configure(
                fg_color=TacticalTheme.BG_DARK,
                text_color=TacticalTheme.CYAN_PRIMARY,
                border_width=1,
                border_color=TacticalTheme.CYAN_DIM,
            )
            self.mode_htl_btn.configure(
                fg_color=TacticalTheme.CYAN_PRIMARY,
                text_color=TacticalTheme.BG_DARK,
                border_width=0,
            )
            self.convert_btn.configure(
                text="CONVERT TO LIGHT",
                text_color=TacticalTheme.CYAN_PRIMARY,
                border_color=TacticalTheme.CYAN_PRIMARY,
            )
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _convert(self):
        if self._on_convert:
            self._on_convert()

    def _batch_convert(self):
        if self._on_batch_convert:
            self._on_batch_convert()

    def _undo(self):
        if self._on_undo:
            self._on_undo()

    def update_details(self, bp_info):
        """Update detail labels with blueprint info."""
        self.detail_labels['name'].configure(text=bp_info.display_name)
        self.detail_labels['grid'].configure(text=bp_info.grid_size)
        self.detail_labels['blocks'].configure(text=str(bp_info.block_count))
        self.detail_labels['light_armor'].configure(text=str(bp_info.light_armor_count))
        self.detail_labels['heavy_armor'].configure(text=str(bp_info.heavy_armor_count))
        self.detail_labels['mappings'].configure(text=str(len(ArmorBlockReplacer.LIGHT_TO_HEAVY)))

        self.light_count_label.configure(text=f"{bp_info.light_armor_count} BLOCKS")
        self.heavy_count_label.configure(text=f"{bp_info.heavy_armor_count} BLOCKS")

    def clear_details(self):
        """Reset detail labels to defaults."""
        for key in self.detail_labels:
            self.detail_labels[key].configure(text="--")
        self.light_count_label.configure(text="0 BLOCKS")
        self.heavy_count_label.configure(text="0 BLOCKS")

    def set_convert_enabled(self, enabled: bool):
        """Enable or disable the convert button."""
        self.convert_btn.configure(state="normal" if enabled else "disabled")

    def set_category_options(self, categories, enabled_categories):
        """Build category checkbox list dynamically."""
        for child in self.category_checks_frame.winfo_children():
            child.destroy()
        self._category_vars = {}

        enabled_lookup = {name.lower() for name in enabled_categories}
        for idx, category in enumerate(categories):
            var = ctk.BooleanVar(value=category.name.lower() in enabled_lookup)
            self._category_vars[category.name] = var
            checkbox = ctk.CTkCheckBox(
                self.category_checks_frame,
                text=f"{category.name} ({len(category.pairs)})",
                variable=var,
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.TEXT_CYAN,
                border_color=TacticalTheme.CYAN_DIM,
                fg_color=TacticalTheme.CYAN_PRIMARY,
                hover_color=TacticalTheme.CYAN_DIM,
                command=self._emit_category_change,
            )
            checkbox.grid(row=idx // 2, column=idx % 2, sticky="w", padx=4, pady=2)

    def _emit_category_change(self):
        if not self._on_categories_change:
            return
        selected = [name for name, var in self._category_vars.items() if var.get()]
        if not selected and self._category_vars:
            first_name = next(iter(self._category_vars))
            self._category_vars[first_name].set(True)
            selected = [first_name]
        self._on_categories_change(selected)
