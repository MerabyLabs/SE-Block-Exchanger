"""Right panel: selected ship, conversion options, and the primary Convert action."""

from __future__ import annotations

import customtkinter as ctk

from ui.labels import (
    armor_convertible_total,
    category_label,
    convert_button_text,
    convertible_total,
    grouped_category_ids,
)
from ui.theme import TacticalTheme
from ui.widgets.progress_ring import ProgressRing


class ControlPanel(ctk.CTkFrame):
    """Right panel with details, live conversion preview, and convert controls."""

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
            **TacticalTheme.panel_kwargs(),
            **kwargs,
        )
        self._on_convert = on_convert
        self._on_batch_convert = on_batch_convert
        self._on_mode_change = on_mode_change
        self._on_categories_change = on_categories_change
        self._on_undo = on_undo
        self._category_vars = {}
        self._blueprint = None
        self._reverse = False
        self._counts_stale = False

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=2, pady=2)

        details_frame = ctk.CTkFrame(container, **TacticalTheme.card_kwargs())
        details_frame.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(
            details_frame,
            text="Selected ship",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", padx=14, pady=(12, 0))

        self.ship_name_label = ctk.CTkLabel(
            details_frame,
            text="Pick a blueprint",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self.ship_name_label.pack(fill="x", padx=14, pady=(2, 8))

        chips = ctk.CTkFrame(details_frame, fg_color="transparent")
        chips.pack(fill="x", padx=14, pady=(0, 12))
        self.grid_chip = self._stat_chip(chips, "Grid", "--")
        self.blocks_chip = self._stat_chip(chips, "Blocks", "--")
        self.ready_chip = self._stat_chip(chips, "Will convert", "--")
        self.grid_chip.pack(side="left", padx=(0, 8))
        self.blocks_chip.pack(side="left", padx=(0, 8))
        self.ready_chip.pack(side="left")

        preview_frame = ctk.CTkFrame(container, **TacticalTheme.card_kwargs())
        preview_frame.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            preview_frame,
            text="What the copy will look like",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", padx=14, pady=(12, 6))

        cols = ctk.CTkFrame(preview_frame, fg_color="transparent")
        cols.pack(fill="x", padx=12, pady=(0, 8))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(2, weight=1)

        before_box = ctk.CTkFrame(
            cols,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=8,
        )
        before_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ctk.CTkLabel(
            before_box, text="Now",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(pady=(8, 0))
        self.before_label = ctk.CTkLabel(
            before_box,
            text="—",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
            justify="center",
        )
        self.before_label.pack(pady=(2, 10))

        ctk.CTkLabel(
            cols,
            text="→",
            font=TacticalTheme.FONT_TITLE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).grid(row=0, column=1, padx=6)

        after_box = ctk.CTkFrame(
            cols,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.ORANGE_PRIMARY,
            corner_radius=8,
        )
        after_box.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        ctk.CTkLabel(
            after_box, text="After",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(pady=(8, 0))
        self.after_label = ctk.CTkLabel(
            after_box,
            text="—",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
            justify="center",
        )
        self.after_label.pack(pady=(2, 10))

        self.change_summary = ctk.CTkLabel(
            preview_frame,
            text="Select a blueprint to see how many blocks will change.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=280,
            justify="left",
            anchor="w",
        )
        self.change_summary.pack(fill="x", padx=14, pady=(0, 12))

        mode_frame = ctk.CTkFrame(container, fg_color="transparent")
        mode_frame.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            mode_frame,
            text="Direction",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", padx=4, pady=(0, 6))

        btn_row = ctk.CTkFrame(mode_frame, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        self.mode_lth_btn = ctk.CTkButton(
            btn_row, text="Light → Heavy",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            hover_color=TacticalTheme.ORANGE_DIM,
            corner_radius=8, height=34,
            command=lambda: self._set_mode("light_to_heavy"),
        )
        self.mode_lth_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.mode_htl_btn = ctk.CTkButton(
            btn_row, text="Heavy → Light",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            hover_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=8, height=34,
            command=lambda: self._set_mode("heavy_to_light"),
        )
        self.mode_htl_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        category_frame = ctk.CTkFrame(container, **TacticalTheme.card_kwargs())
        category_frame.pack(fill="x", padx=10, pady=(8, 6))

        ctk.CTkLabel(
            category_frame,
            text="What to convert",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            category_frame,
            text="Armor is the usual starting point. Add more only if you want those blocks swapped too.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=280,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))

        self.category_checks_frame = ctk.CTkFrame(category_frame, fg_color="transparent")
        self.category_checks_frame.pack(fill="x", padx=10, pady=(0, 12))

        self.progress = ProgressRing(container)
        self.progress.pack(fill="x", padx=10)

        self.convert_btn = ctk.CTkButton(
            container,
            text="Select a blueprint to convert",
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            text_color=TacticalTheme.BG_DARK,
            corner_radius=10,
            height=50,
            state="disabled",
            command=self._convert,
        )
        self.convert_btn.pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(
            container,
            text="Creates a new copy. Your original blueprint stays untouched — Undo removes the copy.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=300,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 10))

        secondary = ctk.CTkFrame(container, fg_color="transparent")
        secondary.pack(fill="x", padx=10, pady=(0, 12))
        secondary.columnconfigure(0, weight=1)
        secondary.columnconfigure(1, weight=1)

        self.undo_btn = ctk.CTkButton(
            secondary,
            text="Undo last copy",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            text_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            corner_radius=8,
            height=34,
            command=self._undo,
        )
        self.undo_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.batch_btn = ctk.CTkButton(
            secondary,
            text="Convert selected",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            corner_radius=8,
            height=34,
            command=self._batch_convert,
        )
        self.batch_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Kept for callers that still look up the old detail_labels mapping.
        self.detail_labels = {
            "name": self.ship_name_label,
            "grid": self.grid_chip,
            "blocks": self.blocks_chip,
            "light_armor": self.before_label,
            "heavy_armor": self.after_label,
            "mappings": self.ready_chip,
        }

    def _stat_chip(self, parent, caption: str, value: str) -> ctk.CTkFrame:
        chip = ctk.CTkFrame(
            parent,
            fg_color=TacticalTheme.BG_DARK,
            corner_radius=8,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
        )
        ctk.CTkLabel(
            chip, text=caption,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(padx=10, pady=(6, 0))
        value_label = ctk.CTkLabel(
            chip, text=value,
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
        )
        value_label.pack(padx=10, pady=(0, 6))
        chip.value_label = value_label  # type: ignore[attr-defined]
        return chip

    def _set_mode(self, mode: str):
        self._reverse = mode == "heavy_to_light"
        if mode == "light_to_heavy":
            self.mode_lth_btn.configure(
                fg_color=TacticalTheme.ORANGE_PRIMARY,
                text_color=TacticalTheme.BG_DARK,
                border_width=0,
            )
            self.mode_htl_btn.configure(
                fg_color=TacticalTheme.BG_DARK,
                text_color=TacticalTheme.TEXT_WHITE,
                border_width=1,
                border_color=TacticalTheme.BORDER_SUBTLE,
            )
        else:
            self.mode_lth_btn.configure(
                fg_color=TacticalTheme.BG_DARK,
                text_color=TacticalTheme.TEXT_WHITE,
                border_width=1,
                border_color=TacticalTheme.BORDER_SUBTLE,
            )
            self.mode_htl_btn.configure(
                fg_color=TacticalTheme.CYAN_PRIMARY,
                text_color=TacticalTheme.BG_DARK,
                border_width=0,
            )
        self._refresh_cta()
        self._refresh_live_preview()
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _convert(self):
        if self._counts_stale:
            return
        if self._on_convert:
            self._on_convert()

    def _batch_convert(self):
        if self._on_batch_convert:
            self._on_batch_convert()

    def _undo(self):
        if self._on_undo:
            self._on_undo()

    def update_details(self, bp_info):
        """Update the selected-ship summary from blueprint info."""
        self._blueprint = bp_info
        self.ship_name_label.configure(text=bp_info.display_name)
        self.grid_chip.value_label.configure(text=bp_info.grid_size or "—")
        self.blocks_chip.value_label.configure(text=f"{bp_info.block_count:,}")
        self._refresh_live_preview()
        self._refresh_cta()

    def clear_details(self):
        """Reset the selected-ship summary."""
        self._blueprint = None
        self._counts_stale = False
        self.ship_name_label.configure(text="Pick a blueprint")
        self.grid_chip.value_label.configure(text="--")
        self.blocks_chip.value_label.configure(text="--")
        self.ready_chip.value_label.configure(text="--")
        self.before_label.configure(text="—")
        self.after_label.configure(text="—")
        self.change_summary.configure(
            text="Select a blueprint to see how many blocks will change."
        )
        self._refresh_cta()

    def _selected_category_ids(self) -> list[str]:
        return [name for name, var in self._category_vars.items() if var.get()]

    def mark_counts_stale(self):
        """Disable Convert until a rescan or dry-run refresh replaces stale totals."""
        self._counts_stale = True
        self.convert_btn.configure(state="disabled", text="Updating conversion counts…")
        self.ready_chip.value_label.configure(text="…")
        self.change_summary.configure(
            text="Updating conversion counts for the selected categories…"
        )

    @property
    def counts_are_stale(self) -> bool:
        return self._counts_stale

    def set_convert_enabled(self, enabled: bool):
        """Enable or disable the convert button (legacy API)."""
        if not enabled:
            self.convert_btn.configure(
                state="disabled",
                text=convert_button_text(
                    count=0,
                    reverse=self._reverse,
                    enabled=False,
                    has_blueprint=self._blueprint is not None,
                    category_ids=self._selected_category_ids(),
                ),
            )
            return
        self._refresh_cta()

    def set_convert_ready(self, *, enabled: bool, count: int, reverse: bool, has_blueprint: bool):
        """Update the primary CTA copy and enabled state together."""
        self._counts_stale = False
        self._reverse = reverse
        self.convert_btn.configure(
            state="normal" if enabled else "disabled",
            text=convert_button_text(
                count=count,
                reverse=reverse,
                enabled=enabled,
                has_blueprint=has_blueprint,
                category_ids=self._selected_category_ids(),
            ),
        )
        self.ready_chip.value_label.configure(text=str(count) if has_blueprint else "--")

    def set_pending_change_count(self, count: int):
        """Accurate rewrite total from a dry-run, before the folder rescan finishes."""
        if count <= 0:
            self.change_summary.configure(
                text="Nothing to convert with the current direction and categories."
            )
            return
        block_word = "block" if count == 1 else "blocks"
        self.change_summary.configure(
            text=f"{count} {block_word} will be rewritten in a new copy with the selected categories."
        )

    def _refresh_cta(self):
        if self._counts_stale:
            return
        count = convertible_total(self._blueprint) if self._blueprint else 0
        has_blueprint = self._blueprint is not None
        enabled = has_blueprint and count > 0
        self.convert_btn.configure(
            state="normal" if enabled else "disabled",
            text=convert_button_text(
                count=count,
                reverse=self._reverse,
                enabled=enabled,
                has_blueprint=has_blueprint,
                category_ids=self._selected_category_ids(),
            ),
        )
        self.ready_chip.value_label.configure(text=str(count) if has_blueprint else "--")

    def _refresh_live_preview(self):
        bp = self._blueprint
        if bp is None:
            return
        light = bp.light_armor_count
        heavy = bp.heavy_armor_count
        ready = convertible_total(bp)
        armor_ready = armor_convertible_total(bp)
        if self._reverse:
            after_light = light + armor_ready
            after_heavy = max(0, heavy - armor_ready)
        else:
            after_light = max(0, light - armor_ready)
            after_heavy = heavy + armor_ready
        self.before_label.configure(text=f"{light} light\n{heavy} heavy")
        self.after_label.configure(text=f"{after_light} light\n{after_heavy} heavy")
        if ready <= 0:
            self.change_summary.configure(
                text="Nothing to convert with the current direction and categories."
            )
            return
        block_word = "block" if ready == 1 else "blocks"
        direction = "heavy" if not self._reverse else "light"
        if armor_ready == ready:
            summary = (
                f"{ready} {block_word} will be rewritten in a new copy toward {direction} armor."
            )
        elif armor_ready == 0:
            summary = f"{ready} {block_word} will be rewritten using the selected categories."
        else:
            other = ready - armor_ready
            summary = (
                f"{ready} {block_word} will be rewritten "
                f"({armor_ready} armor toward {direction}, {other} other)."
            )
        self.change_summary.configure(text=summary)

    def set_category_options(self, categories, enabled_categories):
        """Build grouped category checkboxes with human-readable labels."""
        for child in self.category_checks_frame.winfo_children():
            child.destroy()
        self._category_vars = {}

        enabled_lookup = {name.lower() for name in enabled_categories}
        by_name = {category.name: category for category in categories}
        groups = grouped_category_ids([category.name for category in categories])

        row = 0
        for group_title, ids in groups:
            header = ctk.CTkLabel(
                self.category_checks_frame,
                text=group_title,
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.CYAN_PRIMARY,
                anchor="w",
            )
            header.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2))
            row += 1
            col = 0
            for category_id in ids:
                category = by_name[category_id]
                var = ctk.BooleanVar(value=category.name.lower() in enabled_lookup)
                self._category_vars[category.name] = var
                pair_count = len(category.pairs)
                checkbox = ctk.CTkCheckBox(
                    self.category_checks_frame,
                    text=f"{category_label(category.name)}  ·  {pair_count}",
                    variable=var,
                    font=TacticalTheme.FONT_SMALL,
                    text_color=TacticalTheme.TEXT_WHITE,
                    border_color=TacticalTheme.CYAN_DIM,
                    fg_color=TacticalTheme.CYAN_PRIMARY,
                    hover_color=TacticalTheme.CYAN_DIM,
                    command=self._emit_category_change,
                )
                checkbox.grid(row=row, column=col, sticky="w", padx=4, pady=2)
                col += 1
                if col > 1:
                    col = 0
                    row += 1
            if col != 0:
                row += 1

    def _emit_category_change(self):
        if not self._on_categories_change:
            return
        selected = [name for name, var in self._category_vars.items() if var.get()]
        if not selected and self._category_vars:
            first_name = next(iter(self._category_vars))
            self._category_vars[first_name].set(True)
            selected = [first_name]
        self._on_categories_change(selected)
