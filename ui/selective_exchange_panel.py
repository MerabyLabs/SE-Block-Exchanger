"""
Selective Block Exchange Component.
Allows players to selectively choose which individual block subtypes to convert on a grid
with custom targets, smart dropdowns, category filters, live search, and visual impact preview.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
import customtkinter as ctk

from ui.theme import TacticalTheme
from blueprint_scanner import BlueprintInfo
from mappings import build_registry


TABLE_ROW_CHUNK = 12


def table_build_progress(done: int, total: int) -> str:
    total_n = max(0, int(total))
    done_n = max(0, min(int(done), total_n))
    if total_n <= 0:
        return "Building table…"
    if done_n < total_n:
        return f"Building table… {done_n} of {total_n}"
    return ""


def chunk_table_rows(rows: Sequence, start: int, chunk: int = TABLE_ROW_CHUNK) -> Tuple[list, int]:
    """Return (slice, next_start). Never drops rows; caller loops until next_start == len."""
    begin = max(0, int(start))
    size = max(1, int(chunk))
    end = min(len(rows), begin + size)
    return list(rows[begin:end]), end


class SelectiveExchangePanel(ctk.CTkFrame):
    """
    Tactical data table providing granular block-by-block exchange configuration.
    """

    CATEGORIES = ("ALL", "ARMOR", "PROPULSION", "DLC", "POWER", "WEAPONS", "UTILITY")

    def __init__(
        self,
        master,
        on_selective_convert: Optional[Callable[[Dict[str, str], Set[str]], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_DARK,
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
        self._row_combos: Dict[str, ctk.CTkComboBox] = {}
        self._row_frames: Dict[str, ctk.CTkFrame] = {}
        self._block_counts: Dict[str, int] = {}
        self._block_categories: Dict[str, str] = {}
        self._search_query: str = ""
        self._active_category_filter: str = "ALL"
        self._table_generation = 0
        self._pending_rows: List[Tuple[str, int]] = []
        self._row_build_index = 0
        self._build_job = None

        self._build_ui()

    def _build_ui(self) -> None:
        # Header banner
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        title = ctk.CTkLabel(
            header,
            text=">> SELECTIVE BLOCK EXCHANGER",
            font=TacticalTheme.FONT_TITLE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        )
        title.pack(side="left")

        subtitle = ctk.CTkLabel(
            header,
            text="Pick & choose specific blocks to replace on this grid with custom target overrides.",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        subtitle.pack(side="left", padx=(12, 0))

        # Search & Filter Toolbar
        toolbar = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, corner_radius=6)
        toolbar.pack(fill="x", padx=16, pady=(4, 6))

        # Search input
        search_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        search_frame.pack(side="left", fill="x", expand=True, padx=8, pady=6)

        search_icon = ctk.CTkLabel(
            search_frame,
            text="SEARCH:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        search_icon.pack(side="left", padx=(4, 6))

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Filter blocks by name (e.g. Slope, Thrust, Battery)...",
            font=TacticalTheme.FONT_NORMAL,
            height=30,
            fg_color=TacticalTheme.BG_DARK,
            border_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_WHITE,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Category Filter Pills
        cat_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        cat_frame.pack(side="right", padx=8, pady=6)

        self._cat_buttons: Dict[str, ctk.CTkButton] = {}
        for cat in self.CATEGORIES:
            btn = ctk.CTkButton(
                cat_frame,
                text=cat,
                width=65,
                height=28,
                font=TacticalTheme.FONT_SMALL,
                fg_color=TacticalTheme.CYAN_PRIMARY if cat == "ALL" else TacticalTheme.BG_DARK,
                text_color=TacticalTheme.BG_DARK if cat == "ALL" else TacticalTheme.TEXT_GRAY,
                hover_color=TacticalTheme.CYAN_DIM,
                command=lambda c=cat: self._set_category_filter(c),
            )
            btn.pack(side="left", padx=2)
            self._cat_buttons[cat] = btn

        # Batch Selection Bar
        batch_bar = ctk.CTkFrame(self, fg_color="transparent")
        batch_bar.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(
            batch_bar,
            text="QUICK SELECT:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_MUTED,
        ).pack(side="left", padx=(4, 6))

        quick_actions = [
            ("Select All", self._select_all),
            ("Deselect All", self._deselect_all),
            ("Invert", self._invert_selection),
            ("Only Armor", self._select_only_armor),
            ("Only Slopes", self._select_only_slopes),
            ("Only DLC", self._select_only_dlc),
            ("Only Propulsion", self._select_only_propulsion),
        ]

        for label, cmd in quick_actions:
            ctk.CTkButton(
                batch_bar,
                text=label,
                height=26,
                font=TacticalTheme.FONT_SMALL,
                fg_color=TacticalTheme.BG_GLASS,
                text_color=TacticalTheme.TEXT_CYAN,
                hover_color=TacticalTheme.CYAN_DIM,
                command=cmd,
            ).pack(side="left", padx=3)

        # Table Column Header
        col_header = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_MEDIUM, height=30, corner_radius=4)
        col_header.pack(fill="x", padx=16, pady=(4, 0))

        ctk.CTkLabel(col_header, text="USE", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY, width=45).pack(side="left", padx=4)
        ctk.CTkLabel(col_header, text="CATEGORY", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY, width=100, anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(col_header, text="CURRENT BLOCK (ON GRID)", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY, width=280, anchor="w").pack(side="left", padx=8)
        ctk.CTkLabel(col_header, text="->", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.CYAN_DIM, width=24).pack(side="left")
        ctk.CTkLabel(col_header, text="TARGET REPLACEMENT SUBTYPE", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY, anchor="w").pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkLabel(col_header, text="QUICK ACTION", font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY, width=120).pack(side="right", padx=10)

        # Scrollable table body
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # Bottom summary & action dock
        bottom_dock = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, corner_radius=8)
        bottom_dock.pack(fill="x", padx=16, pady=(4, 12))

        summary_box = ctk.CTkFrame(bottom_dock, fg_color="transparent")
        summary_box.pack(side="left", padx=16, pady=10)

        self.summary_title = ctk.CTkLabel(
            summary_box,
            text="0 Block Types Selected (0 Total Blocks)",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
            anchor="w",
        )
        self.summary_title.pack(anchor="w")

        self.summary_sub = ctk.CTkLabel(
            summary_box,
            text="Target: Custom Converted Blueprint with selected block substitutions.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            anchor="w",
        )
        self.summary_sub.pack(anchor="w")

        self.convert_btn = ctk.CTkButton(
            bottom_dock,
            text="EXCHANGE SELECTED BLOCKS >>",
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            text_color="#000000",
            height=42,
            width=260,
            command=self._on_convert_clicked,
        )
        self.convert_btn.pack(side="right", padx=16, pady=10)

    # ------------------------------------------------------------------
    # Category Identification & Smart Replacement Suggestion
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_subtype(subtype: str) -> str:
        s = subtype.lower()
        if "armor" in s or "panel" in s:
            return "ARMOR"
        if "thrust" in s:
            return "PROPULSION"
        if any(k in s for k in ("industrial", "scifi", "contact", "signal", "warfare", "wasteland", "decorative", "cab", "buggy")):
            return "DLC"
        if any(k in s for k in ("generator", "reactor", "battery", "solar", "gyro", "jumpdrive", "tank", "conveyor", "cargo")):
            return "POWER"
        if any(k in s for k in ("turret", "missile", "gatling", "cannon", "railgun", "warhead", "rocket")):
            return "WEAPONS"
        return "UTILITY"

    @staticmethod
    def _get_category_color(cat: str) -> str:
        colors = {
            "ARMOR": TacticalTheme.COLOR_ARMOR,
            "PROPULSION": TacticalTheme.COLOR_PROPULSION,
            "DLC": TacticalTheme.COLOR_DLC,
            "POWER": TacticalTheme.COLOR_POWER,
            "WEAPONS": TacticalTheme.COLOR_WEAPONS,
            "UTILITY": TacticalTheme.COLOR_UTILITY,
        }
        return colors.get(cat, TacticalTheme.TEXT_GRAY)

    def _get_smart_suggestions(self, subtype: str) -> List[str]:
        suggestions = []
        default_target = self.default_mapping.get(subtype)
        if default_target and default_target != subtype:
            suggestions.append(default_target)

        # Light <-> Heavy suggestions
        if "Heavy" in subtype:
            light_equiv = subtype.replace("HeavyBlock", "Block").replace("Heavy", "")
            if light_equiv not in suggestions and light_equiv != subtype:
                suggestions.append(light_equiv)
        elif "Armor" in subtype and "Heavy" not in subtype:
            heavy_equiv = subtype.replace("BlockArmor", "HeavyBlockArmor").replace("Armor", "HeavyArmor")
            if heavy_equiv not in suggestions and heavy_equiv != subtype:
                suggestions.append(heavy_equiv)

        # DLC substitutions
        if "Industrial" in subtype:
            vanilla = subtype.replace("Industrial", "")
            if vanilla not in suggestions:
                suggestions.append(vanilla)
        if "SciFi" in subtype:
            vanilla = subtype.replace("SciFi", "")
            if vanilla not in suggestions:
                suggestions.append(vanilla)

        # Prototech variants
        if "Prototech" not in subtype:
            if "Reactor" in subtype or "Generator" in subtype:
                suggestions.append("LargePrototechReactor" if "Large" in subtype else "SmallPrototechReactor")
            elif "Thrust" in subtype:
                suggestions.append("LargeBlockLargePrototechThrust" if "Large" in subtype else "SmallBlockLargePrototechThrust")
            elif "JumpDrive" in subtype:
                suggestions.append("LargePrototechJumpDrive")
            elif "Gyro" in subtype:
                suggestions.append("LargePrototechGyro" if "Large" in subtype else "SmallPrototechGyro")

        if not suggestions:
            suggestions.append(subtype)

        return suggestions

    # ------------------------------------------------------------------
    # Data Loading & Rendering
    # ------------------------------------------------------------------

    def load_blueprint(self, bp: Optional[BlueprintInfo]) -> None:
        """Populate the tactical table with block subtypes from the selected blueprint."""
        self.current_blueprint = bp
        self._table_generation += 1
        generation = self._table_generation
        if self._build_job is not None:
            try:
                self.after_cancel(self._build_job)
            except Exception:
                pass
            self._build_job = None
        self._row_vars.clear()
        self._row_targets.clear()
        self._row_combos.clear()
        self._row_frames.clear()
        self._block_counts.clear()
        self._block_categories.clear()

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if bp is None or not bp.subtype_counts:
            empty_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text="No blueprint selected or no block breakdown available.",
                font=TacticalTheme.FONT_NORMAL,
                text_color=TacticalTheme.TEXT_GRAY,
            )
            empty_lbl.pack(pady=40)
            self._update_summary()
            return

        self._block_counts = dict(bp.subtype_counts)
        self._pending_rows = sorted(self._block_counts.items(), key=lambda x: x[1], reverse=True)
        self._row_build_index = 0
        self.summary_title.configure(text=table_build_progress(0, len(self._pending_rows)))
        self.convert_btn.configure(state="disabled")
        self._build_table_chunk(generation)

    def _build_table_chunk(self, generation: int) -> None:
        self._build_job = None
        if generation != self._table_generation:
            return
        chunk, nxt = chunk_table_rows(self._pending_rows, self._row_build_index, TABLE_ROW_CHUNK)
        for subtype, count in chunk:
            self._add_subtype_row(subtype, count)
        self._row_build_index = nxt
        total = len(self._pending_rows)
        if nxt < total:
            self.summary_title.configure(text=table_build_progress(nxt, total))
            self._build_job = self.after(1, lambda: self._build_table_chunk(generation))
            return
        self._filter_rows()
        self._update_summary()

    def _add_subtype_row(self, subtype: str, count: int) -> None:
            cat = self._classify_subtype(subtype)
            self._block_categories[subtype] = cat

            row = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=TacticalTheme.BG_CARD,
                border_width=1,
                border_color=TacticalTheme.BORDER_SUBTLE,
                corner_radius=6,
                height=40,
            )
            row.pack(fill="x", pady=2, padx=4)
            self._row_frames[subtype] = row

            # 1. Checkbox
            var = ctk.BooleanVar(value=(subtype in self.default_mapping))
            self._row_vars[subtype] = var
            chk = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=30,
                command=self._update_summary,
                fg_color=TacticalTheme.CYAN_PRIMARY,
                hover_color=TacticalTheme.CYAN_DIM,
            )
            chk.pack(side="left", padx=(10, 4))

            # 2. Category badge
            cat_badge = ctk.CTkLabel(
                row,
                text=cat,
                font=TacticalTheme.FONT_CODE_SMALL,
                fg_color=self._get_category_color(cat),
                text_color=TacticalTheme.TEXT_WHITE,
                corner_radius=4,
                width=90,
                height=22,
            )
            cat_badge.pack(side="left", padx=4)

            # 3. Source subtype label & count badge
            name_frame = ctk.CTkFrame(row, fg_color="transparent", width=270)
            name_frame.pack(side="left", padx=(8, 4))

            name_lbl = ctk.CTkLabel(
                name_frame,
                text=subtype,
                font=TacticalTheme.FONT_NORMAL,
                text_color=TacticalTheme.TEXT_WHITE,
                anchor="w",
            )
            name_lbl.pack(side="left", padx=(0, 6))

            count_badge = ctk.CTkLabel(
                name_frame,
                text=f"{count:,}x",
                font=TacticalTheme.FONT_CODE_SMALL,
                text_color=TacticalTheme.TEXT_CYAN,
                fg_color=TacticalTheme.BG_GLASS,
                corner_radius=4,
                padx=6,
            )
            count_badge.pack(side="left")

            # 4. Arrow
            ctk.CTkLabel(row, text="->", font=TacticalTheme.FONT_CODE_BOLD, text_color=TacticalTheme.CYAN_DIM, width=24).pack(side="left")

            # 5. Smart Target Suggestion ComboBox
            suggestions = self._get_smart_suggestions(subtype)
            default_target = suggestions[0] if suggestions else subtype
            target_var = ctk.StringVar(value=default_target)
            self._row_targets[subtype] = target_var

            combo = ctk.CTkComboBox(
                row,
                values=suggestions,
                variable=target_var,
                font=TacticalTheme.FONT_NORMAL,
                dropdown_font=TacticalTheme.FONT_NORMAL,
                fg_color=TacticalTheme.BG_DARK,
                border_color=TacticalTheme.CYAN_DIM,
                button_color=TacticalTheme.BG_GLASS,
                button_hover_color=TacticalTheme.CYAN_DIM,
                dropdown_fg_color=TacticalTheme.BG_MEDIUM,
                dropdown_hover_color=TacticalTheme.BG_GLASS,
                text_color=TacticalTheme.TEXT_WHITE,
                height=30,
            )
            combo.pack(side="left", fill="x", expand=True, padx=(8, 6))
            self._row_combos[subtype] = combo

            # 6. Quick Action Button
            quick_btn = ctk.CTkButton(
                row,
                text="Quick Swap",
                width=100,
                height=26,
                font=TacticalTheme.FONT_SMALL,
                fg_color=TacticalTheme.BG_GLASS,
                text_color=TacticalTheme.TEXT_CYAN,
                hover_color=TacticalTheme.CYAN_DIM,
                command=lambda st=subtype: self._quick_swap_row(st),
            )
            quick_btn.pack(side="right", padx=10)

    def _quick_swap_row(self, subtype: str) -> None:
        """Cycle through smart replacement suggestions on click."""
        combo = self._row_combos.get(subtype)
        target_var = self._row_targets.get(subtype)
        if not combo or not target_var:
            return

        values = combo.cget("values")
        if not values:
            return

        current = target_var.get()
        if current in values:
            idx = (values.index(current) + 1) % len(values)
            target_var.set(values[idx])
        else:
            target_var.set(values[0])

        # Automatically check the row if changed
        if subtype in self._row_vars:
            self._row_vars[subtype].set(True)
            self._update_summary()

    # ------------------------------------------------------------------
    # Filtering & Search
    # ------------------------------------------------------------------

    def _on_search_changed(self, event=None) -> None:
        self._search_query = self.search_entry.get().strip().lower()
        self._filter_rows()

    def _set_category_filter(self, category: str) -> None:
        self._active_category_filter = category
        for cat, btn in self._cat_buttons.items():
            if cat == category:
                btn.configure(fg_color=TacticalTheme.CYAN_PRIMARY, text_color=TacticalTheme.BG_DARK)
            else:
                btn.configure(fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_GRAY)
        self._filter_rows()

    def _filter_rows(self) -> None:
        """Show or hide rows based on active search query and category filter."""
        for subtype, row_frame in self._row_frames.items():
            matches_search = (not self._search_query) or (self._search_query in subtype.lower())
            cat = self._block_categories.get(subtype, "UTILITY")
            matches_cat = (self._active_category_filter == "ALL") or (cat == self._active_category_filter)

            if matches_search and matches_cat:
                row_frame.pack(fill="x", pady=2, padx=4)
            else:
                row_frame.pack_forget()

    # ------------------------------------------------------------------
    # Batch Selection Helpers
    # ------------------------------------------------------------------

    def _select_all(self) -> None:
        for var in self._row_vars.values():
            var.set(True)
        self._update_summary()

    def _deselect_all(self) -> None:
        for var in self._row_vars.values():
            var.set(False)
        self._update_summary()

    def _invert_selection(self) -> None:
        for var in self._row_vars.values():
            var.set(not var.get())
        self._update_summary()

    def _select_only_armor(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set(self._block_categories.get(subtype) == "ARMOR")
        self._update_summary()

    def _select_only_slopes(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set("Slope" in subtype or "Corner" in subtype)
        self._update_summary()

    def _select_only_dlc(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set(self._block_categories.get(subtype) == "DLC")
        self._update_summary()

    def _select_only_propulsion(self) -> None:
        for subtype, var in self._row_vars.items():
            var.set(self._block_categories.get(subtype) == "PROPULSION")
        self._update_summary()

    def _update_summary(self) -> None:
        selected_types = [st for st, var in self._row_vars.items() if var.get()]
        total_blocks = sum(self._block_counts.get(st, 0) for st in selected_types)
        self.summary_title.configure(
            text=f"{len(selected_types):,} Block Type(s) Selected ({total_blocks:,} Total Blocks)"
        )
        if len(selected_types) > 0:
            self.convert_btn.configure(state="normal")
        else:
            self.convert_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

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

