"""
Selective Block Exchange Component.
Allows players to selectively choose which individual block subtypes to convert on a grid
with custom targets, per-block checkboxes, and live impact estimation.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Set
import customtkinter as ctk

from ui.theme import TacticalTheme
from blueprint_scanner import BlueprintInfo
from mappings import build_registry


class SelectiveExchangePanel(ctk.CTkFrame):
    """
    Panel providing granular block-by-block exchange configuration.
    """

    def __init__(
        self,
        master,
        on_selective_convert: Optional[Callable[[Dict[str, str], Set[str]], None]] = None,
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
        self.on_selective_convert = on_selective_convert
        self.current_blueprint: Optional[BlueprintInfo] = None
        self.registry = build_registry(include_builtin=True)
        self.default_mapping = self.registry.build_mapping(reverse=False)

        self._row_vars: Dict[str, ctk.BooleanVar] = {}
        self._row_targets: Dict[str, ctk.StringVar] = {}
        self._block_counts: Dict[str, int] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        # Title header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 6))

        title = ctk.CTkLabel(
            header,
            text=">> SELECTIVE BLOCK EXCHANGER",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        title.pack(side="left")

        # Subheader instructions
        subtitle = ctk.CTkLabel(
            self,
            text="Choose specific block types to replace on this grid. Customize replacement targets per-block.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            anchor="w",
        )
        subtitle.pack(fill="x", padx=12, pady=(0, 6))

        # Quick-filter action bar
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkButton(
            btn_bar,
            text="Select All",
            width=80,
            height=26,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            command=self._select_all,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_bar,
            text="Deselect All",
            width=80,
            height=26,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            command=self._deselect_all,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_bar,
            text="Only Armor",
            width=80,
            height=26,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            command=self._select_only_armor,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_bar,
            text="Only Slopes",
            width=80,
            height=26,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            command=self._select_only_slopes,
        ).pack(side="left", padx=4)

        # Scrollable table container
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
            height=220,
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=6)

        # Bottom summary & action button
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=12, pady=(6, 12))

        self.summary_label = ctk.CTkLabel(
            bottom_bar,
            text="0 block types selected (0 total blocks)",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.summary_label.pack(side="left", padx=4)

        self.convert_btn = ctk.CTkButton(
            bottom_bar,
            text="EXCHANGE SELECTED BLOCKS >>",
            font=TacticalTheme.FONT_NORMAL,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            text_color="#000000",
            height=32,
            command=self._on_convert_clicked,
        )
        self.convert_btn.pack(side="right", padx=4)

    def load_blueprint(self, bp: Optional[BlueprintInfo]) -> None:
        """Populate the table with block subtypes from the selected blueprint."""
        self.current_blueprint = bp
        self._row_vars.clear()
        self._row_targets.clear()
        self._block_counts.clear()

        # Clear existing rows in scroll_frame
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if bp is None or not bp.subtype_counts:
            empty_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text="No blueprint selected or no block breakdown available.",
                font=TacticalTheme.FONT_NORMAL,
                text_color=TacticalTheme.TEXT_GRAY,
            )
            empty_lbl.pack(pady=20)
            self._update_summary()
            return

        self._block_counts = dict(bp.subtype_counts)

        # Sort blocks by count descending
        sorted_subtypes = sorted(self._block_counts.items(), key=lambda x: x[1], reverse=True)

        for subtype, count in sorted_subtypes:
            row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=4)

            # Checkbox
            var = ctk.BooleanVar(value=(subtype in self.default_mapping))
            self._row_vars[subtype] = var
            chk = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=24,
                command=self._update_summary,
                fg_color=TacticalTheme.CYAN_PRIMARY,
                hover_color=TacticalTheme.CYAN_DIM,
            )
            chk.pack(side="left", padx=(0, 6))

            # Block Name & Count
            lbl_text = f"{subtype} (x{count})"
            lbl = ctk.CTkLabel(
                row,
                text=lbl_text,
                font=TacticalTheme.FONT_NORMAL,
                text_color=TacticalTheme.TEXT_WHITE if var.get() else TacticalTheme.TEXT_GRAY,
                width=200,
                anchor="w",
            )
            lbl.pack(side="left", padx=4)

            # Arrow indicator
            ctk.CTkLabel(row, text="->", text_color=TacticalTheme.CYAN_DIM).pack(side="left", padx=4)

            # Target subtype entry
            default_target = self.default_mapping.get(subtype, subtype)
            target_var = ctk.StringVar(value=default_target)
            self._row_targets[subtype] = target_var

            entry = ctk.CTkEntry(
                row,
                textvariable=target_var,
                font=TacticalTheme.FONT_SMALL,
                height=24,
                width=180,
                fg_color=TacticalTheme.BG_GLASS,
                border_color=TacticalTheme.CYAN_DIM,
            )
            entry.pack(side="left", fill="x", expand=True, padx=4)

        self._update_summary()

    def _select_all(self) -> None:
        for var in self._row_vars.values():
            var.set(True)
        self._update_summary()

    def _deselect_all(self) -> None:
        for var in self._row_vars.values():
            var.set(False)
        self._update_summary()

    def _select_only_armor(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set("Armor" in subtype)
        self._update_summary()

    def _select_only_slopes(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set("Slope" in subtype or "Corner" in subtype)
        self._update_summary()

    def _update_summary(self) -> None:
        selected_types = [st for st, var in self._row_vars.items() if var.get()]
        total_blocks = sum(self._block_counts.get(st, 0) for st in selected_types)
        self.summary_label.configure(
            text=f"{len(selected_types)} block type(s) selected ({total_blocks} total blocks)"
        )

    def _on_convert_clicked(self) -> None:
        selected_types = {st for st, var in self._row_vars.items() if var.get()}
        if not selected_types:
            return

        custom_mapping = {
            st: self._row_targets[st].get().strip()
            for st in selected_types
            if st in self._row_targets and self._row_targets[st].get().strip()
        }

        if self.on_selective_convert:
            self.on_selective_convert(custom_mapping, selected_types)
