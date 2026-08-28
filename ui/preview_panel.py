"""
Preview Panel Component
Center tabview with Intel, Selective Exchange, XML Source, Preview Diff, Analytics,
PB Doctor Studio, Subgrids 2D/2.5D Map, and SE2 Transition tabs.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Iterable, List, Optional, Set

import customtkinter as ctk

from blueprint_analytics import (
    BlueprintAnalyticsEngine,
    BlueprintAnalyticsResult,
    ConversionComparison,
    HealthIssue,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from mappings.skin_palette_engine import OFFICIAL_SKINS
from pb_doctor import (
    ExtractedPBScript,
    PBScriptReport,
    PBScriptValidator,
    ScriptFixer,
)
from subgrid_engine.hierarchy_parser import MultiGridStructure, SubgridNode
from ui.selective_exchange_panel import SelectiveExchangePanel
from ui.theme import TacticalTheme
from ui.widgets.ship_canvas import ShipCanvas, VoxelBlock


class PreviewPanel(ctk.CTkFrame):
    """Center panel with tabbed views for blueprint information."""

    def __init__(
        self,
        master,
        on_run_preview=None,
        on_export_csv=None,
        on_export_txt=None,
        on_apply_fix=None,
        on_vanillafy=None,
        on_scale_grid=None,
        on_survival_sanity=None,
        on_upgrade_prototech=None,
        on_workshop_sync=None,
        on_selective_convert=None,
        on_migrate_se2=None,
        on_split_subgrids=None,
        on_apply_skin_palette=None,
        on_harden_armor=None,
        on_lightweight_armor=None,
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
        self._on_run_preview = on_run_preview
        self._on_export_csv = on_export_csv
        self._on_export_txt = on_export_txt
        self._on_apply_fix = on_apply_fix
        self._on_vanillafy = on_vanillafy
        self._on_scale_grid = on_scale_grid
        self._on_survival_sanity = on_survival_sanity
        self._on_upgrade_prototech = on_upgrade_prototech
        self._on_workshop_sync = on_workshop_sync
        self._on_selective_convert = on_selective_convert
        self._on_migrate_se2 = on_migrate_se2
        self._on_split_subgrids = on_split_subgrids
        self._on_apply_skin_palette = on_apply_skin_palette
        self._on_harden_armor = on_harden_armor
        self._on_lightweight_armor = on_lightweight_armor
        self._latest_health_issues: List[HealthIssue] = []
        self._latest_analytics_result: Optional[BlueprintAnalyticsResult] = None
        self._latest_structure: Optional[MultiGridStructure] = None

        # PB Doctor active data
        self._pb_scripts: List[ExtractedPBScript] = []
        self._pb_reports: List[PBScriptReport] = []
        self._active_pb_index: int = 0

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=TacticalTheme.BG_DARK,
            segmented_button_fg_color=TacticalTheme.BG_MEDIUM,
            segmented_button_selected_color=TacticalTheme.ORANGE_PRIMARY,
            segmented_button_selected_hover_color=TacticalTheme.ORANGE_DIM,
            segmented_button_unselected_color=TacticalTheme.BG_MEDIUM,
            segmented_button_unselected_hover_color=TacticalTheme.BG_GLASS,
            text_color=TacticalTheme.TEXT_WHITE,
            text_color_disabled=TacticalTheme.TEXT_GRAY,
            corner_radius=6,
        )
        self.tabview.pack(fill="both", expand=True, padx=4, pady=4)

        self._build_intel_tab()
        self._build_selective_tab()
        self._build_survival_tab()
        self._build_fleet_tab()
        self._build_xml_tab()
        self._build_preview_tab()
        self._build_analytics_tab()
        self._build_pb_doctor_tab()
        self._build_subgrids_tab()
        self._build_se2_tab()

    def _build_intel_tab(self):
        self.tab_intel = self.tabview.add("INTEL")
        self.tab_intel.configure(fg_color=TacticalTheme.BG_DARK)

        scroll = ctk.CTkScrollableFrame(self.tab_intel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=10)

        ctk.CTkLabel(
            scroll,
            text=">> BLUEPRINT TACTICAL INTEL",
            font=TacticalTheme.FONT_TITLE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", pady=(4, 8))

        # Main Info Card
        self.intel_info_card = ctk.CTkFrame(
            scroll,
            fg_color=TacticalTheme.BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
        )
        self.intel_info_card.pack(fill="x", pady=6)

        self.intel_text = ctk.CTkLabel(
            self.intel_info_card,
            text="Select a blueprint in the database to review block totals, conversion readiness, and file location.",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
            justify="left",
            anchor="w",
        )
        self.intel_text.pack(fill="both", expand=True, padx=16, pady=14)

    def _build_selective_tab(self):
        self.tab_selective = self.tabview.add("SELECTIVE EXCHANGE")
        self.tab_selective.configure(fg_color=TacticalTheme.BG_DARK)
        self.selective_panel = SelectiveExchangePanel(
            self.tab_selective,
            on_selective_convert=self._on_selective_convert_clicked,
        )
        self.selective_panel.pack(fill="both", expand=True, padx=2, pady=2)

    def _on_selective_convert_clicked(self, custom_mapping: Dict[str, str], selected_subtypes: Set[str]):
        if self._on_selective_convert:
            self._on_selective_convert(custom_mapping, selected_subtypes)

    def _build_survival_tab(self):
        self.tab_survival = self.tabview.add("SURVIVAL & BOM")
        self.tab_survival.configure(fg_color=TacticalTheme.BG_DARK)

        container = ctk.CTkFrame(self.tab_survival, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.columnconfigure(0, weight=1, minsize=380)
        container.columnconfigure(1, weight=1, minsize=420)
        container.rowconfigure(0, weight=1)

        # --- LEFT PANE: Subgrid Projector Decomposer ---
        left_pane = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        ctk.CTkLabel(
            left_pane,
            text="PROJECTOR SUBGRID DECOMPOSER",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.survival_subgrid_status = ctk.CTkLabel(
            left_pane,
            text="Multi-Grid Status: Select blueprint to analyze",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
        )
        self.survival_subgrid_status.pack(anchor="w", padx=12, pady=(0, 6))

        btn_bar = ctk.CTkFrame(left_pane, fg_color="transparent")
        btn_bar.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_split_subgrids = ctk.CTkButton(
            btn_bar,
            text="🚀 SPLIT FOR PROJECTOR PRINTING",
            font=TacticalTheme.FONT_NORMAL,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            text_color=TacticalTheme.BG_DARK,
            height=32,
            command=self._on_split_subgrids_clicked,
        )
        self.btn_split_subgrids.pack(side="left", fill="x", expand=True)

        self.survival_splitter_textbox = ctk.CTkTextbox(
            left_pane,
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color="#080e1a",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.survival_splitter_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._set_textbox_content(
            self.survival_splitter_textbox,
            "In Space Engineers survival mode, standard projector blocks cannot weld subgrids\n"
            "(rotors, hinges, pistons, turrets).\n\n"
            "Click 'SPLIT FOR PROJECTOR PRINTING' to automatically break this vessel into\n"
            "standalone printable modules with step-by-step assembly sequence guides!"
        )

        # --- RIGHT PANE: Survival Bill of Materials & LCD Exporter ---
        right_pane = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        right_top = ctk.CTkFrame(right_pane, fg_color="transparent")
        right_top.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            right_top,
            text="SURVIVAL BILL OF MATERIALS (BOM)",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(side="left")

        # Action Buttons
        right_btns = ctk.CTkFrame(right_pane, fg_color="transparent")
        right_btns.pack(fill="x", padx=10, pady=(0, 6))

        self.btn_copy_tim = ctk.CTkButton(
            right_btns,
            text="📋 COPY TIM LCD",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=28,
            command=self._copy_tim_config,
        )
        self.btn_copy_tim.pack(side="left", padx=2)

        self.btn_copy_isy = ctk.CTkButton(
            right_btns,
            text="📋 COPY ISY (IIM)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=28,
            command=self._copy_isy_config,
        )
        self.btn_copy_isy.pack(side="left", padx=2)

        self.btn_export_bom = ctk.CTkButton(
            right_btns,
            text="💾 EXPORT BOM (.MD)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=28,
            command=self._export_bom_report,
        )
        self.btn_export_bom.pack(side="left", padx=2)

        self.survival_bom_textbox = ctk.CTkTextbox(
            right_pane,
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color="#a5f3fc",
            fg_color="#080e1a",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.survival_bom_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._set_textbox_content(
            self.survival_bom_textbox,
            "Select a blueprint to calculate raw ore extraction demands, ingot refining times,\n"
            "and export automated inventory manager LCD scripts."
        )

    def _build_fleet_tab(self):
        self.tab_fleet = self.tabview.add("FLEET & HARDENING")
        self.tab_fleet.configure(fg_color=TacticalTheme.BG_DARK)

        container = ctk.CTkFrame(self.tab_fleet, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.columnconfigure(0, weight=1, minsize=380)
        container.columnconfigure(1, weight=1, minsize=420)
        container.rowconfigure(0, weight=1)

        # --- LEFT PANE: Batch Armor Reskinning & Color Palette ---
        left_pane = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        ctk.CTkLabel(
            left_pane,
            text="ARMOR SKIN & PALETTE SWAPPER",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Skin picker row
        skin_row = ctk.CTkFrame(left_pane, fg_color="transparent")
        skin_row.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            skin_row,
            text="TARGET SKIN:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            width=90,
            anchor="w",
        ).pack(side="left")

        skin_options = [f"{v.display_name} ({k})" for k, v in OFFICIAL_SKINS.items()]
        self.skin_var = ctk.StringVar(value="Clean Armor (Clean_Armor)")
        self.skin_menu = ctk.CTkOptionMenu(
            skin_row,
            values=skin_options,
            variable=self.skin_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_MEDIUM,
            button_hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_WHITE,
        )
        self.skin_menu.pack(side="left", fill="x", expand=True)

        # Primary Hex Color
        color_row = ctk.CTkFrame(left_pane, fg_color="transparent")
        color_row.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            color_row,
            text="PRIMARY HEX:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            width=90,
            anchor="w",
        ).pack(side="left")

        self.color_hex_var = ctk.StringVar(value="#0284c7")
        self.color_hex_entry = ctk.CTkEntry(
            color_row,
            textvariable=self.color_hex_var,
            font=TacticalTheme.FONT_CODE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_CYAN,
            border_color=TacticalTheme.CYAN_DIM,
            width=120,
        )
        self.color_hex_entry.pack(side="left", padx=(0, 8))

        # Quick Swatches
        swatches = [
            ("Tactical Blue", "#0284c7"),
            ("Stealth Black", "#0f172a"),
            ("Combat Red", "#dc2626"),
            ("Hazard Yellow", "#eab308"),
            ("Titanium", "#f8fafc"),
        ]
        for sname, shex in swatches:
            btn = ctk.CTkButton(
                color_row,
                text="",
                width=22,
                height=22,
                corner_radius=4,
                fg_color=shex,
                hover_color="#ffffff",
                command=lambda h=shex: self.color_hex_var.set(h),
            )
            btn.pack(side="left", padx=2)

        self.armor_only_var = ctk.BooleanVar(value=True)
        self.armor_only_chk = ctk.CTkCheckBox(
            left_pane,
            text="Apply to Armor Blocks Only (Preserve internal functional colors)",
            variable=self.armor_only_var,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.CYAN_DIM,
        )
        self.armor_only_chk.pack(anchor="w", padx=12, pady=6)

        self.btn_apply_skin = ctk.CTkButton(
            left_pane,
            text="🎨 APPLY BATCH RESKIN & PALETTE",
            font=TacticalTheme.FONT_NORMAL,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.BG_DARK,
            height=32,
            command=self._on_apply_skin_palette_clicked,
        )
        self.btn_apply_skin.pack(fill="x", padx=12, pady=(4, 10))

        self.skin_log_textbox = ctk.CTkTextbox(
            left_pane,
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color="#080e1a",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.skin_log_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._set_textbox_content(
            self.skin_log_textbox,
            "1-Click Fleet Reskinning:\n"
            "Select any official Space Engineers armor texture or custom RGB/HSV palette\n"
            "to reskin and recolor whole fleets in seconds without tedious in-game painting."
        )

        # --- RIGHT PANE: Combat Armor Hardening & Lightweighting ---
        right_pane = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        ctk.CTkLabel(
            right_pane,
            text="CORE HARDENING & LIGHTWEIGHTING WIZARD",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        radius_row = ctk.CTkFrame(right_pane, fg_color="transparent")
        radius_row.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            radius_row,
            text="REINFORCE RADIUS:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            width=130,
            anchor="w",
        ).pack(side="left")

        self.radius_slider = ctk.CTkSlider(
            radius_row,
            from_=1,
            to=5,
            number_of_steps=4,
            width=160,
            command=lambda v: self.radius_val_lbl.configure(text=f"{int(v)} BLOCKS"),
        )
        self.radius_slider.set(2)
        self.radius_slider.pack(side="left", padx=4)

        self.radius_val_lbl = ctk.CTkLabel(
            radius_row,
            text="2 BLOCKS",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_CYAN,
        )
        self.radius_val_lbl.pack(side="left", padx=6)

        action_row = ctk.CTkFrame(right_pane, fg_color="transparent")
        action_row.pack(fill="x", padx=12, pady=6)
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)

        self.btn_harden_cores = ctk.CTkButton(
            action_row,
            text="🛡️ HARDEN VITAL CORES",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            text_color=TacticalTheme.BG_DARK,
            height=32,
            command=self._on_harden_armor_clicked,
        )
        self.btn_harden_cores.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_lightweight = ctk.CTkButton(
            action_row,
            text="⚡ LIGHTWEIGHT OUTER HULL",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=32,
            command=self._on_lightweight_armor_clicked,
        )
        self.btn_lightweight.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.hardening_log_textbox = ctk.CTkTextbox(
            right_pane,
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color="#080e1a",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.hardening_log_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._set_textbox_content(
            self.hardening_log_textbox,
            "Combat Armor Optimization:\n"
            "• 'HARDEN VITAL CORES': Automatically detects coordinates of Reactors, Jump Drives,\n"
            "  Fuel Tanks, and Cockpits, reinforcing surrounding light armor with heavy armor.\n"
            "• 'LIGHTWEIGHT OUTER HULL': Strips heavy armor from non-vital peripheral areas to\n"
            "  maximize jump range, thrust acceleration, and maneuverability."
        )

    def _on_split_subgrids_clicked(self):
        if self._on_split_subgrids:
            self._on_split_subgrids()

    def _copy_tim_config(self):
        if not self._latest_analytics_result:
            messagebox.showwarning("Survival BOM", "No blueprint loaded to generate TIM config.")
            return
        cfg = BlueprintAnalyticsEngine.generate_tim_config(self._latest_analytics_result.component_totals)
        self.clipboard_clear()
        self.clipboard_append(cfg)
        messagebox.showinfo("TIM Config", "TIM Inventory Master LCD config copied to clipboard!")

    def _copy_isy_config(self):
        if not self._latest_analytics_result:
            messagebox.showwarning("Survival BOM", "No blueprint loaded to generate Isy config.")
            return
        cfg = BlueprintAnalyticsEngine.generate_isy_config(self._latest_analytics_result.component_totals)
        self.clipboard_clear()
        self.clipboard_append(cfg)
        messagebox.showinfo("Isy Config", "Isy's Inventory Manager (IIM) Custom Data config copied to clipboard!")

    def _export_bom_report(self):
        if not self._latest_analytics_result:
            messagebox.showwarning("Survival BOM", "No blueprint loaded to export BOM.")
            return
        report = BlueprintAnalyticsEngine.generate_survival_bom_report(self._latest_analytics_result)
        path = filedialog.asksaveasfilename(
            title="Export Survival Bill of Materials",
            initialfile=f"BOM_{self._latest_analytics_result.blueprint_name}.md",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(report)
                messagebox.showinfo("Export Successful", f"Survival BOM exported to:\n{path}")
            except Exception as exc:
                messagebox.showerror("Export Failed", f"Could not save BOM: {exc}")

    def _on_apply_skin_palette_clicked(self):
        choice = self.skin_var.get()
        skin_id = "None"
        for k, v in OFFICIAL_SKINS.items():
            if k in choice or v.display_name in choice:
                skin_id = k
                break

        primary_hex = self.color_hex_var.get().strip()
        armor_only = self.armor_only_var.get()

        if self._on_apply_skin_palette:
            self._on_apply_skin_palette(skin_id, primary_hex, None, armor_only)

    def _on_harden_armor_clicked(self):
        radius = int(self.radius_slider.get())
        if self._on_harden_armor:
            self._on_harden_armor(radius)

    def _on_lightweight_armor_clicked(self):
        radius = int(self.radius_slider.get())
        if self._on_lightweight_armor:
            self._on_lightweight_armor(radius)

    def update_survival_bom(self, analytics_result: BlueprintAnalyticsResult, multi_grid_structure: Optional[MultiGridStructure] = None):
        self._latest_analytics_result = analytics_result
        self._latest_structure = multi_grid_structure

        if multi_grid_structure:
            grid_count = multi_grid_structure.total_grids
            subgrid_count = grid_count - 1
            if subgrid_count > 0:
                self.survival_subgrid_status.configure(
                    text=f"Multi-Grid Status: {grid_count} Grids Detected (1 Main Hull + {subgrid_count} Subgrids)",
                    text_color=TacticalTheme.ORANGE_PRIMARY,
                )
                self.btn_split_subgrids.configure(state="normal")
            else:
                self.survival_subgrid_status.configure(
                    text="Multi-Grid Status: Single Unified Grid (No subgrids detected)",
                    text_color=TacticalTheme.GREEN_PRIMARY,
                )
                self.btn_split_subgrids.configure(state="normal")

        # Populate BOM Textbox
        bom_text = BlueprintAnalyticsEngine.generate_survival_bom_report(analytics_result)
        self._set_textbox_content(self.survival_bom_textbox, bom_text)

    def _build_xml_tab(self):
        self.tab_xml = self.tabview.add("XML SOURCE")
        self.tab_xml.configure(fg_color=TacticalTheme.BG_DARK)

        xml_header = ctk.CTkFrame(self.tab_xml, fg_color="transparent")
        xml_header.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            xml_header,
            text=">> XML SOURCE VIEWER",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(side="left")
        self.xml_status = ctk.CTkLabel(
            xml_header,
            text="(No file loaded)",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.xml_status.pack(side="right")
        self.xml_textbox = ctk.CTkTextbox(
            self.tab_xml,
            font=("Consolas", 9),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.xml_textbox.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_preview_tab(self):
        self.tab_preview = self.tabview.add("PREVIEW")
        self.tab_preview.configure(fg_color=TacticalTheme.BG_DARK)

        preview_header = ctk.CTkFrame(self.tab_preview, fg_color="transparent")
        preview_header.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            preview_header,
            text=">> BEFORE / AFTER DIFF",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.GREEN_PRIMARY,
        ).pack(side="left")
        ctk.CTkButton(
            preview_header,
            text="RUN PREVIEW",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_MEDIUM,
            width=120,
            height=28,
            command=self._run_preview,
        ).pack(side="right")

        preview_split = ctk.CTkFrame(self.tab_preview, fg_color="transparent")
        preview_split.pack(fill="both", expand=True, padx=8, pady=8)
        preview_split.columnconfigure(0, weight=1)
        preview_split.columnconfigure(1, weight=1)
        preview_split.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            preview_split,
            text="CURRENT (MATCHING SOURCE BLOCKS)",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            preview_split,
            text="AFTER CONVERSION (TARGET BLOCKS)",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))

        self.preview_before_text = ctk.CTkTextbox(
            preview_split,
            font=("Consolas", 9),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.preview_before_text.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self.preview_after_text = ctk.CTkTextbox(
            preview_split,
            font=("Consolas", 9),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.preview_after_text.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

        self.preview_summary_text = ctk.CTkTextbox(
            self.tab_preview,
            height=120,
            font=("Consolas", 9),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.preview_summary_text.pack(fill="x", padx=8, pady=(0, 8))

    def _build_analytics_tab(self):
        self.tab_analytics = self.tabview.add("ANALYTICS")
        self.tab_analytics.configure(fg_color=TacticalTheme.BG_DARK)

        header = ctk.CTkFrame(self.tab_analytics, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 4))
        ctk.CTkLabel(
            header,
            text=">> BLUEPRINT ANALYTICS",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(side="left")

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.pack(side="right")
        ctk.CTkButton(
            button_row,
            text="EXPORT CSV",
            width=100,
            height=28,
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.BG_MEDIUM,
            command=self._export_csv,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            button_row,
            text="EXPORT TXT",
            width=100,
            height=28,
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_MEDIUM,
            command=self._export_txt,
        ).pack(side="left", padx=3)

        metrics = ctk.CTkFrame(
            self.tab_analytics,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
        )
        metrics.pack(fill="x", padx=8, pady=(0, 6))
        metrics.columnconfigure((0, 1, 2, 3), weight=1)
        self.metric_labels = {}
        metric_defs = [
            ("Blocks", "0"),
            ("PCU", "0"),
            ("Mass", "0"),
            ("Convertible", "0"),
        ]
        for idx, (name, value) in enumerate(metric_defs):
            cell = ctk.CTkFrame(metrics, fg_color="transparent")
            cell.grid(row=0, column=idx, sticky="ew", padx=8, pady=8)
            ctk.CTkLabel(
                cell,
                text=name.upper(),
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.TEXT_GRAY,
            ).pack(anchor="w")
            label = ctk.CTkLabel(
                cell,
                text=value,
                font=TacticalTheme.FONT_LARGE,
                text_color=TacticalTheme.TEXT_CYAN,
            )
            label.pack(anchor="w")
            self.metric_labels[name] = label

        body = ctk.CTkFrame(self.tab_analytics, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        body.columnconfigure(0, weight=1, uniform="analytics")
        body.columnconfigure(1, weight=1, uniform="analytics")
        body.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            body,
            text="CATEGORY DISTRIBUTION",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            body,
            text="ORES -> INGOTS -> COMPONENTS -> BLOCKS",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))

        self.chart_canvas = tk.Canvas(
            body,
            bg="#0c1220",
            highlightthickness=1,
            highlightbackground=TacticalTheme.BG_MEDIUM,
        )
        self.chart_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))

        self.resource_tree = ctk.CTkTextbox(
            body,
            font=("Consolas", 9),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.resource_tree.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))

        self.issues_frame = ctk.CTkFrame(
            self.tab_analytics,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=6,
        )
        self.issues_frame.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            self.issues_frame,
            text="HEALTH AUDIT",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self.issues_container = ctk.CTkFrame(self.issues_frame, fg_color="transparent")
        self.issues_container.pack(fill="x", padx=8, pady=(0, 8))

    def _run_preview(self):
        if self._on_run_preview:
            self._on_run_preview()

    def _export_csv(self):
        if self._on_export_csv:
            self._on_export_csv()

    def _export_txt(self):
        if self._on_export_txt:
            self._on_export_txt()

    def update_intel(self, bp_info, conversion_mode: str):
        convertible = (
            bp_info.light_armor_count
            if conversion_mode == "light_to_heavy"
            else bp_info.heavy_armor_count
        )
        source = "LIGHT" if conversion_mode == "light_to_heavy" else "HEAVY"
        target = "HEAVY" if conversion_mode == "light_to_heavy" else "LIGHT"
        lines = [
            f"BLUEPRINT: {bp_info.display_name}",
            f"GRID SIZE: {bp_info.grid_size}",
            f"TOTAL BLOCKS: {bp_info.block_count:,}",
            f"LIGHT ARMOR: {bp_info.light_armor_count:,}",
            f"HEAVY ARMOR: {bp_info.heavy_armor_count:,}",
            "",
            f"Current mode: {source} -> {target}",
            f"Convertible armor blocks available: {convertible:,}",
            "",
            f"Blueprint path: {bp_info.path}",
        ]
        if bp_info.category_counts:
            lines.extend(["", "Category matches:"])
            for name, count in sorted(bp_info.category_counts.items()):
                lines.append(f"  {name}: {count}")
        self.intel_text.configure(text="\n".join(lines))
        if hasattr(self, "selective_panel"):
            self.selective_panel.load_blueprint(bp_info)

    def clear_intel(self):
        self.intel_text.configure(
            text="Select a blueprint to review block totals, conversion readiness, and file location."
        )
        self.clear_analytics()
        self.show_preview_diff({}, {}, "Select a blueprint and run preview.")
        if hasattr(self, "selective_panel"):
            self.selective_panel.load_blueprint(None)

    def load_xml(self, file_path, status_text: str):
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.xml_textbox.configure(state="normal")
            self.xml_textbox.delete("1.0", "end")
            self.xml_textbox.insert("end", content)
            self.xml_textbox.configure(state="disabled")
            self.xml_status.configure(text=status_text)
        except Exception as exc:
            self.xml_textbox.configure(state="normal")
            self.xml_textbox.delete("1.0", "end")
            self.xml_textbox.insert("end", f"Error reading file: {exc}")
            self.xml_textbox.configure(state="disabled")

    def show_preview_report(self, bp_name: str, mode: str, report: str):
        """
        Backward-compatible API with richer rendering.
        """
        self.show_preview_diff({}, {}, f"DRY-RUN PREVIEW: {bp_name}\nMode: {mode}\n\n{report}")
        self.tabview.set("PREVIEW")

    def show_preview_diff(
        self,
        before_counts: Dict[str, int],
        after_counts: Dict[str, int],
        summary_text: str,
    ):
        self._set_textbox_content(
            self.preview_before_text,
            self._format_counts(before_counts, "No matching source blocks found."),
        )
        self._set_textbox_content(
            self.preview_after_text,
            self._format_counts(after_counts, "No resulting target blocks."),
        )
        self._set_textbox_content(self.preview_summary_text, summary_text or "No changes.")
        self.tabview.set("PREVIEW")

    def update_analytics(self, analytics_result, comparison: Optional[ConversionComparison] = None):
        self.metric_labels["Blocks"].configure(text=f"{analytics_result.block_count:,}")
        self.metric_labels["PCU"].configure(text=f"{analytics_result.pcu_total:,}")
        self.metric_labels["Mass"].configure(text=f"{analytics_result.mass_total:,.2f}")

        convertible = 0
        if comparison:
            convertible = sum(comparison.block_changes.values())
        self.metric_labels["Convertible"].configure(text=f"{convertible:,}")

        self._draw_category_chart(analytics_result.category_counts)
        self._set_textbox_content(
            self.resource_tree,
            self._build_resource_tree_text(analytics_result, comparison),
        )
        self._populate_health_issues(analytics_result.health_issues)

    def clear_analytics(self):
        for label in self.metric_labels.values():
            label.configure(text="0")
        self.chart_canvas.delete("all")
        self._set_textbox_content(self.resource_tree, "Select a blueprint to analyze.")
        self._populate_health_issues([])
        self.clear_se2_transition()

    def _populate_health_issues(self, issues: Iterable[HealthIssue]):
        self._latest_health_issues = list(issues)
        for child in self.issues_container.winfo_children():
            child.destroy()

        if not self._latest_health_issues:
            ctk.CTkLabel(
                self.issues_container,
                text="No health issues detected.",
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.GREEN_PRIMARY,
            ).pack(anchor="w", pady=2)
            return

        for issue in self._latest_health_issues:
            color = {
                SEVERITY_INFO: TacticalTheme.CYAN_PRIMARY,
                SEVERITY_WARNING: TacticalTheme.ORANGE_PRIMARY,
                SEVERITY_ERROR: TacticalTheme.RED_PRIMARY,
            }.get(issue.severity, TacticalTheme.CYAN_PRIMARY)
            row = ctk.CTkFrame(self.issues_container, fg_color=TacticalTheme.BG_DARK, corner_radius=4)
            row.pack(fill="x", pady=2)
            text = f"[{issue.severity}] {issue.message}\nSuggestion: {issue.suggestion}"
            ctk.CTkLabel(
                row,
                text=text,
                justify="left",
                anchor="w",
                wraplength=700,
                text_color=color,
                font=TacticalTheme.FONT_SMALL,
            ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
            if issue.fix_id:
                ctk.CTkButton(
                    row,
                    text="APPLY FIX",
                    width=90,
                    height=26,
                    font=TacticalTheme.FONT_SMALL,
                    fg_color="transparent",
                    border_width=1,
                    border_color=TacticalTheme.GREEN_PRIMARY,
                    text_color=TacticalTheme.GREEN_PRIMARY,
                    hover_color=TacticalTheme.BG_MEDIUM,
                    command=lambda fix=issue.fix_id: self._emit_fix(fix),
                ).pack(side="right", padx=6, pady=6)

    def _emit_fix(self, fix_id: str):
        if self._on_apply_fix:
            self._on_apply_fix(fix_id)

    def _draw_category_chart(self, category_counts: Dict[str, int]):
        self.chart_canvas.delete("all")
        if not category_counts:
            self.chart_canvas.create_text(
                10,
                20,
                text="No category data available.",
                fill=TacticalTheme.TEXT_GRAY,
                anchor="w",
            )
            return

        width = max(self.chart_canvas.winfo_width(), 320)
        height = max(self.chart_canvas.winfo_height(), 220)
        self.chart_canvas.config(scrollregion=(0, 0, width, height))
        max_value = max(category_counts.values()) if category_counts else 1

        bar_h = max(18, min(30, int((height - 20) / max(len(category_counts), 1))))
        y = 12
        palette = [
            TacticalTheme.CYAN_PRIMARY,
            TacticalTheme.ORANGE_PRIMARY,
            TacticalTheme.GREEN_PRIMARY,
            "#38bdf8",
            "#f97316",
            "#14b8a6",
        ]
        for idx, (name, value) in enumerate(sorted(category_counts.items(), key=lambda item: item[1], reverse=True)):
            ratio = value / max_value if max_value else 0
            bar_w = int((width - 180) * ratio)
            color = palette[idx % len(palette)]
            self.chart_canvas.create_rectangle(150, y, 150 + bar_w, y + bar_h, fill=color, outline="")
            self.chart_canvas.create_text(10, y + (bar_h / 2), text=name, fill=TacticalTheme.TEXT_CYAN, anchor="w")
            self.chart_canvas.create_text(
                160 + bar_w,
                y + (bar_h / 2),
                text=str(value),
                fill=TacticalTheme.TEXT_WHITE,
                anchor="w",
            )
            y += bar_h + 8

    @staticmethod
    def _set_textbox_content(textbox: ctk.CTkTextbox, text: str):
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("end", text)
        textbox.configure(state="disabled")

    @staticmethod
    def _format_counts(counts: Dict[str, int], empty_text: str) -> str:
        if not counts:
            return empty_text
        lines = []
        for subtype, qty in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"{subtype:45} x{qty}")
        return "\n".join(lines)

    @staticmethod
    def _build_resource_tree_text(analytics_result, comparison: Optional[ConversionComparison]) -> str:
        lines: List[str] = []
        lines.append("ORES")
        for ore, qty in analytics_result.ore_totals.items():
            lines.append(f"  - {ore}: {qty:,.2f}")
        lines.append("")
        lines.append("INGOTS")
        for ingot, qty in analytics_result.ingot_totals.items():
            lines.append(f"  - {ingot}: {qty:,.2f}")
        lines.append("")
        lines.append("COMPONENTS")
        for component, qty in analytics_result.component_totals.items():
            lines.append(f"  - {component}: {qty:,}")
        lines.append("")
        lines.append("TOP BLOCKS")
        for subtype, qty in list(analytics_result.block_counts.items())[:15]:
            lines.append(f"  - {subtype}: {qty:,}")

        if comparison:
            lines.append("")
            lines.append("CONVERSION DELTAS")
            lines.append(f"  - PCU: {comparison.pcu_delta:+d}")
            lines.append(f"  - Mass: {comparison.mass_delta:+.2f}")
            for component, delta in sorted(comparison.component_delta.items()):
                if delta:
                    lines.append(f"  - {component}: {delta:+d}")
        return "\n".join(lines)

    def switch_to_xml(self):
        self.tabview.set("XML SOURCE")

    def _build_se2_tab(self):
        self.tab_se2 = self.tabview.add("SE2 TRANSITION")
        self.tab_se2.configure(fg_color=TacticalTheme.BG_DARK)
        
        scroll_frame = ctk.CTkScrollableFrame(self.tab_se2, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        header_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            header_frame,
            text=">> VRAGE3 & SE2 READINESS CENTER",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(side="left")
        
        self.se2_score_frame = ctk.CTkFrame(
            scroll_frame,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=2,
            border_color=TacticalTheme.CYAN_PRIMARY,
            corner_radius=10,
        )
        self.se2_score_frame.pack(fill="x", pady=10)
        
        score_layout = ctk.CTkFrame(self.se2_score_frame, fg_color="transparent")
        score_layout.pack(fill="x", padx=18, pady=12)
        
        self.se2_score_label = ctk.CTkLabel(
            score_layout,
            text="--",
            font=("Courier New", 36, "bold"),
            text_color=TacticalTheme.GREEN_PRIMARY,
        )
        self.se2_score_label.pack(side="left", padx=(0, 15))
        
        score_details = ctk.CTkFrame(score_layout, fg_color="transparent")
        score_details.pack(side="left", fill="both", expand=True)
        
        self.se2_status_title = ctk.CTkLabel(
            score_details,
            text="SELECT BLUEPRINT TO COMMENCE SCAN",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.CYAN_PRIMARY,
            anchor="w",
        )
        self.se2_status_title.pack(anchor="w")
        
        self.se2_status_desc = ctk.CTkLabel(
            score_details,
            text="The blueprint will be thoroughly audited across DLC constraints, mechanical hierarchies, and programmable subsystems for VRage3 (SE2) compatibility.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
            wraplength=520,
            justify="left",
            anchor="w",
        )
        self.se2_status_desc.pack(anchor="w", pady=(2, 0))
        
        actions_frame = ctk.CTkFrame(
            scroll_frame,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=8,
        )
        actions_frame.pack(fill="x", pady=8)
        
        ctk.CTkLabel(
            actions_frame,
            text=">> TRANSITION UTILITIES",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        
        btn_layout = ctk.CTkFrame(actions_frame, fg_color="transparent")
        btn_layout.pack(fill="x", padx=12, pady=(4, 12))
        btn_layout.columnconfigure((0, 1), weight=1)
        
        self.btn_vanillafy = ctk.CTkButton(
            btn_layout,
            text="DLC TO BASE CONVERT (VANILLA-FY)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.BG_GLASS,
            height=34,
            command=self._vanillafy_clicked,
            state="disabled",
        )
        self.btn_vanillafy.grid(row=0, column=0, padx=(0, 6), pady=(0, 6), sticky="ew")
        
        self.btn_gridsizer = ctk.CTkButton(
            btn_layout,
            text="RESCALE GRID SIZE (LARGE <-> SMALL)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.CYAN_PRIMARY,
            hover_color=TacticalTheme.BG_GLASS,
            height=34,
            command=self._gridsizer_clicked,
            state="disabled",
        )
        self.btn_gridsizer.grid(row=0, column=1, padx=(6, 0), pady=(0, 6), sticky="ew")

        self.btn_survival_sanity = ctk.CTkButton(
            btn_layout,
            text="SURVIVAL SANITY (STRIP PROTOTECH)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.ORANGE_DIM,
            text_color=TacticalTheme.ORANGE_DIM,
            hover_color=TacticalTheme.BG_GLASS,
            height=34,
            command=self._survival_sanity_clicked,
            state="disabled",
        )
        self.btn_survival_sanity.grid(row=1, column=0, padx=(0, 6), pady=(4, 0), sticky="ew")

        self.btn_upgrade_prototech = ctk.CTkButton(
            btn_layout,
            text="UPGRADE TO PROTOTECH (FACTORUM)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.CYAN_DIM,
            hover_color=TacticalTheme.BG_GLASS,
            height=34,
            command=self._upgrade_prototech_clicked,
            state="disabled",
        )
        self.btn_upgrade_prototech.grid(row=1, column=1, padx=(6, 0), pady=(4, 0), sticky="ew")

        self.btn_export_se2 = ctk.CTkButton(
            btn_layout,
            text="EXPORT TO SPACE ENGINEERS 2 (VRAGE3 JSON)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_GLASS,
            height=34,
            command=self._export_se2_clicked,
            state="disabled",
        )
        self.btn_export_se2.grid(row=2, column=0, columnspan=2, pady=(6, 0), sticky="ew")
        
        self.se2_audit_frame = ctk.CTkFrame(
            scroll_frame,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=8,
        )
        self.se2_audit_frame.pack(fill="both", expand=True, pady=8)
        
        ctk.CTkLabel(
            self.se2_audit_frame,
            text=">> TRANSITION ANALYSIS LOG",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        
        self.se2_audit_textbox = ctk.CTkTextbox(
            self.se2_audit_frame,
            height=200,
            font=("Consolas", 10),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_width=0,
        )
        self.se2_audit_textbox.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._set_textbox_content(
            self.se2_audit_textbox,
            "Select a blueprint to begin VRage3 Transition Scanning...\n"
        )

    def _build_pb_doctor_tab(self):
        self.tab_pb_doctor = self.tabview.add("PB DOCTOR")
        self.tab_pb_doctor.configure(fg_color=TacticalTheme.BG_DARK)

        # Header toolbar with PB Selector and Health Status
        top_bar = ctk.CTkFrame(self.tab_pb_doctor, fg_color=TacticalTheme.BG_GLASS, corner_radius=6)
        top_bar.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            top_bar,
            text="PROGRAMMABLE BLOCK:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(side="left", padx=(12, 6), pady=8)

        self.pb_selector_var = ctk.StringVar(value="No PB Blocks Found")
        self.pb_selector_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["No PB Blocks Found"],
            variable=self.pb_selector_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_MEDIUM,
            button_hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_WHITE,
            width=260,
            command=self._on_pb_selection_changed,
        )
        self.pb_selector_menu.pack(side="left", padx=4, pady=8)

        self.pb_status_label = ctk.CTkLabel(
            top_bar,
            text="NO BLUEPRINT LOADED",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.pb_status_label.pack(side="right", padx=12, pady=8)

        # Main Split Workspace
        workspace = ctk.CTkFrame(self.tab_pb_doctor, fg_color="transparent")
        workspace.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        workspace.columnconfigure(0, weight=4, minsize=300)
        workspace.columnconfigure(1, weight=6, minsize=420)
        workspace.rowconfigure(0, weight=1)

        # --- LEFT PANE: Diagnostics & Health Gauges ---
        left_pane = ctk.CTkScrollableFrame(
            workspace,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(
            left_pane,
            text="DIAGNOSTIC METRICS & COMPLIANCE",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=8, pady=(8, 4))

        self.pb_score_lbl = ctk.CTkLabel(
            left_pane,
            text="Compliance Score: --",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_CYAN,
        )
        self.pb_score_lbl.pack(anchor="w", padx=8, pady=2)

        self.pb_instr_lbl = ctk.CTkLabel(
            left_pane,
            text="Est. Instructions: -- / tick",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.pb_instr_lbl.pack(anchor="w", padx=8, pady=2)

        # Char limit progress
        ctk.CTkLabel(
            left_pane,
            text="SCRIPT SIZE (100,000 CHAR LIMIT):",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", padx=8, pady=(8, 2))

        self.pb_char_progress = ctk.CTkProgressBar(
            left_pane,
            height=12,
            progress_color=TacticalTheme.GREEN_PRIMARY,
        )
        self.pb_char_progress.pack(fill="x", padx=8, pady=2)
        self.pb_char_progress.set(0)

        self.pb_char_lbl = ctk.CTkLabel(
            left_pane,
            text="0 / 100,000 chars (0%)",
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
        )
        self.pb_char_lbl.pack(anchor="w", padx=8, pady=(0, 6))

        # Method signatures checklist
        self.pb_methods_lbl = ctk.CTkLabel(
            left_pane,
            text="Program() -  |  Main() -  |  Save() -",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
        )
        self.pb_methods_lbl.pack(anchor="w", padx=8, pady=(4, 8))

        ctk.CTkLabel(
            left_pane,
            text="COMPILER & WHITELIST ISSUES:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(anchor="w", padx=8, pady=(8, 4))

        self.pb_diagnostics_textbox = ctk.CTkTextbox(
            left_pane,
            height=180,
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color="#080e1a",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.pb_diagnostics_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # --- RIGHT PANE: C# Code Inspector & Studio ---
        right_pane = ctk.CTkFrame(
            workspace,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        code_toolbar = ctk.CTkFrame(right_pane, fg_color="transparent")
        code_toolbar.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            code_toolbar,
            text="C# INGAME SCRIPT SOURCE",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(side="left")

        # Action Buttons
        self.btn_pb_autofix = ctk.CTkButton(
            code_toolbar,
            text="🛠️ APPLY AUTO-FIX",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.GREEN_DIM,
            text_color="#000000",
            height=28,
            command=self._apply_pb_autofix,
        )
        self.btn_pb_autofix.pack(side="right", padx=3)

        self.btn_pb_copy = ctk.CTkButton(
            code_toolbar,
            text="📋 COPY CODE",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=28,
            command=self._copy_pb_script,
        )
        self.btn_pb_copy.pack(side="right", padx=3)

        self.btn_pb_export = ctk.CTkButton(
            code_toolbar,
            text="💾 EXPORT .CS",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_CYAN,
            height=28,
            command=self._export_pb_script,
        )
        self.btn_pb_export.pack(side="right", padx=3)

        self.pb_code_textbox = ctk.CTkTextbox(
            right_pane,
            font=TacticalTheme.FONT_CODE,
            text_color="#a5f3fc",
            fg_color="#070d19",
            border_width=1,
            border_color=TacticalTheme.CYAN_DIM,
            corner_radius=4,
        )
        self.pb_code_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_pb_doctor(self, scripts: List[ExtractedPBScript], reports: List[PBScriptReport]) -> None:
        """Populate the interactive PB Doctor Studio with scripts and reports."""
        self._pb_scripts = list(scripts)
        self._pb_reports = list(reports)
        self._active_pb_index = 0

        if not self._pb_scripts:
            self.pb_status_label.configure(text="0 PB SCRIPTS DETECTED", text_color=TacticalTheme.TEXT_GRAY)
            self.pb_selector_menu.configure(values=["No Programmable Blocks Detected"])
            self.pb_selector_var.set("No Programmable Blocks Detected")
            self.pb_score_lbl.configure(text="Compliance Score: N/A")
            self.pb_instr_lbl.configure(text="Est. Instructions: 0 / tick")
            self.pb_char_progress.set(0)
            self.pb_char_lbl.configure(text="0 / 100,000 chars (0%)")
            self.pb_methods_lbl.configure(text="Program() -  |  Main() -  |  Save() -")
            self._set_textbox_content(
                self.pb_diagnostics_textbox,
                "No Programmable Blocks with embedded scripts found in this blueprint.\n\n"
                "Tip: You can use PB Doctor to inspect, clean, and fix in-game scripts on any PB vessel."
            )
            self._set_textbox_content(
                self.pb_code_textbox,
                "// No Programmable Block scripts detected on this vessel."
            )
            self.btn_pb_autofix.configure(state="disabled")
            self.btn_pb_copy.configure(state="disabled")
            self.btn_pb_export.configure(state="disabled")
            return

        # Build options for selector menu
        menu_items = []
        for idx, (script, report) in enumerate(zip(self._pb_scripts, self._pb_reports), 1):
            name = script.custom_name or f"PB_{idx}"
            menu_items.append(f"[{idx}] {name} ({report.compliance_score}%)")

        self.pb_selector_menu.configure(values=menu_items)
        self.pb_selector_var.set(menu_items[0])
        self.btn_pb_autofix.configure(state="normal")
        self.btn_pb_copy.configure(state="normal")
        self.btn_pb_export.configure(state="normal")

        self._render_active_pb()

    def _on_pb_selection_changed(self, choice: str) -> None:
        values = self.pb_selector_menu.cget("values")
        if choice in values:
            self._active_pb_index = values.index(choice)
            self._render_active_pb()

    def _render_active_pb(self) -> None:
        if not self._pb_scripts or self._active_pb_index >= len(self._pb_scripts):
            return

        script = self._pb_scripts[self._active_pb_index]
        report = self._pb_reports[self._active_pb_index]

        # Overall Status Badge
        if report.error_count == 0:
            if report.warning_count > 0:
                status_text = f"{report.warning_count} WARNING(S)"
                status_color = TacticalTheme.ORANGE_PRIMARY
            else:
                status_text = "100% COMPLIANT ✓"
                status_color = TacticalTheme.GREEN_PRIMARY
        else:
            status_text = f"{report.error_count} COMPILER ERROR(S) ✗"
            status_color = TacticalTheme.RED_PRIMARY

        self.pb_status_label.configure(text=status_text, text_color=status_color)
        self.pb_score_lbl.configure(text=f"Compliance Score: {report.compliance_score}%", text_color=status_color)
        self.pb_instr_lbl.configure(text=f"Est. Instructions: ~{report.estimated_instructions:,} / 50,000 per tick")

        # Size progress
        chars = len(script.program_code)
        pct = min(1.0, chars / 100000.0)
        self.pb_char_progress.set(pct)
        if pct >= 0.9:
            self.pb_char_progress.configure(progress_color=TacticalTheme.RED_PRIMARY)
        elif pct >= 0.7:
            self.pb_char_progress.configure(progress_color=TacticalTheme.ORANGE_PRIMARY)
        else:
            self.pb_char_progress.configure(progress_color=TacticalTheme.GREEN_PRIMARY)
        self.pb_char_lbl.configure(text=f"{chars:,} / 100,000 chars ({pct*100:.1f}%)")

        prog_chk = "✓" if report.has_program_constructor else "✗"
        main_chk = "✓" if report.has_main_method else "✗"
        save_chk = "✓" if report.has_save_method else "✗"
        self.pb_methods_lbl.configure(text=f"Program() {prog_chk}  |  Main() {main_chk}  |  Save() {save_chk}")

        # Diagnostics details
        diag_lines = []
        if not report.diagnostics:
            diag_lines.append("[+] Script passes all Space Engineers in-game whitelist checks!")
            diag_lines.append("[+] No prohibited reflection, file I/O, or threading detected.")
        else:
            for d in report.diagnostics:
                line_str = f"L{d.line_number}: " if d.line_number else ""
                diag_lines.append(f"[{d.severity.upper()}] {line_str}{d.rule_id}")
                diag_lines.append(f"  -> {d.message}")
                diag_lines.append(f"  -> Solution: {d.suggestion}\n")

        self._set_textbox_content(self.pb_diagnostics_textbox, "\n".join(diag_lines))
        self._set_textbox_content(self.pb_code_textbox, script.program_code)

    def _apply_pb_autofix(self) -> None:
        if not self._pb_scripts or self._active_pb_index >= len(self._pb_scripts):
            return

        script = self._pb_scripts[self._active_pb_index]
        fixed_code, fixes = ScriptFixer.fix_script(script.program_code)

        # Update in-memory script and re-validate
        script.program_code = fixed_code
        script.character_count = len(fixed_code)
        script.line_count = len(fixed_code.splitlines())

        new_report = PBScriptValidator.validate_script(script.custom_name, fixed_code)
        self._pb_reports[self._active_pb_index] = new_report

        self._render_active_pb()

        fix_summary = "\n• " + "\n• ".join(fixes) if fixes else "No modifications required."
        messagebox.showinfo(
            "Auto-Fix Applied",
            f"Successfully applied auto-fixes to '{script.custom_name}':{fix_summary}\n\n"
            "The updated script has been loaded into the editor!",
        )

    def _copy_pb_script(self) -> None:
        if not self._pb_scripts or self._active_pb_index >= len(self._pb_scripts):
            return
        code = self._pb_scripts[self._active_pb_index].program_code
        self.clipboard_clear()
        self.clipboard_append(code)
        messagebox.showinfo("Clipboard", "C# Script copied to clipboard! You can paste it directly into Space Engineers.")

    def _export_pb_script(self) -> None:
        if not self._pb_scripts or self._active_pb_index >= len(self._pb_scripts):
            return
        script = self._pb_scripts[self._active_pb_index]
        default_name = f"{script.custom_name.replace(' ', '_')}.cs"
        path = filedialog.asksaveasfilename(
            title="Export C# Script",
            initialfile=default_name,
            defaultextension=".cs",
            filetypes=[("C# Script", "*.cs"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(script.program_code)
                messagebox.showinfo("Export Successful", f"Script exported to:\n{path}")
            except Exception as exc:
                messagebox.showerror("Export Failed", f"Could not save script: {exc}")

    def _build_subgrids_tab(self):
        self.tab_subgrids = self.tabview.add("SUBGRIDS & MAP")
        self.tab_subgrids.configure(fg_color=TacticalTheme.BG_DARK)

        container = ctk.CTkFrame(self.tab_subgrids, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.columnconfigure(0, weight=3, minsize=260)
        container.columnconfigure(1, weight=7, minsize=480)
        container.rowconfigure(0, weight=1)

        # Left Column: Mechanical Hierarchy Tree
        left_box = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_CARD,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=6,
        )
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        ctk.CTkLabel(
            left_box,
            text="MECHANICAL HIERARCHY TREE",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self.subgrid_tree_scroll = ctk.CTkScrollableFrame(left_box, fg_color="transparent")
        self.subgrid_tree_scroll.pack(fill="both", expand=True, padx=6, pady=4)

        # Right Column: Interactive 2D/2.5D Graphical Ship Blueprint Canvas
        self.ship_canvas = ShipCanvas(container)
        self.ship_canvas.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

    def update_subgrids(self, structure: MultiGridStructure, matrix_summaries, voxels: Optional[List[dict]] = None):
        """Update mechanical tree cards and load voxel blocks into the 2D/2.5D Ship Canvas."""
        for child in self.subgrid_tree_scroll.winfo_children():
            child.destroy()

        # Build "All Grids" filter button
        btn_all = ctk.CTkButton(
            self.subgrid_tree_scroll,
            text=f"■ ALL GRIDS ({structure.total_grids} Grids | {structure.total_blocks:,} Blocks)",
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_GLASS,
            hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_WHITE,
            anchor="w",
            command=lambda: self.ship_canvas.filter_by_grid(None),
        )
        btn_all.pack(fill="x", pady=2)

        def add_node_card(node: SubgridNode, depth: int = 0):
            indent = "    " * depth
            prefix = "└── " if depth > 0 else "■ "
            link_desc = f" [{node.attachment_via}]" if node.attachment_via else ""

            card = ctk.CTkFrame(self.subgrid_tree_scroll, fg_color=TacticalTheme.BG_GLASS, corner_radius=4)
            card.pack(fill="x", pady=2)

            lbl_text = f"{indent}{prefix}{node.grid_name}\n{indent}   ({node.grid_size} Grid, {node.block_count:,} blks){link_desc}"
            btn = ctk.CTkButton(
                card,
                text=lbl_text,
                font=TacticalTheme.FONT_SMALL,
                fg_color="transparent",
                hover_color=TacticalTheme.BG_MEDIUM,
                text_color=TacticalTheme.TEXT_CYAN if depth == 0 else TacticalTheme.TEXT_GRAY,
                anchor="w",
                justify="left",
                command=lambda g=node.grid_name: self.ship_canvas.filter_by_grid(g),
            )
            btn.pack(fill="x", padx=4, pady=4)

            for child in node.children:
                add_node_card(child, depth + 1)

        if structure.root_node:
            add_node_card(structure.root_node)

        for orphan in structure.orphaned_grids:
            add_node_card(orphan, depth=0)

        # Load voxels into ShipCanvas
        if voxels:
            voxel_blocks = [
                VoxelBlock(
                    x=v["x"],
                    y=v["y"],
                    z=v["z"],
                    subtype=v["subtype"],
                    grid_name=v["grid_name"],
                    grid_size=v.get("grid_size", "Large"),
                    is_subgrid=v.get("is_subgrid", False),
                )
                for v in voxels
            ]
            self.ship_canvas.load_structure_data(voxel_blocks)

    def _vanillafy_clicked(self):
        if self._on_vanillafy:
            self._on_vanillafy()

    def _gridsizer_clicked(self):
        if self._on_scale_grid:
            self._on_scale_grid()

    def _survival_sanity_clicked(self):
        if self._on_survival_sanity:
            self._on_survival_sanity()

    def _upgrade_prototech_clicked(self):
        if self._on_upgrade_prototech:
            self._on_upgrade_prototech()

    def _export_se2_clicked(self):
        if self._on_migrate_se2:
            self._on_migrate_se2()

    def update_se2_transition(self, info, dlc_count: int, script_count: int, subgrid_count: int):
        self.btn_vanillafy.configure(state="normal")
        self.btn_gridsizer.configure(state="normal")
        self.btn_survival_sanity.configure(state="normal")
        self.btn_upgrade_prototech.configure(state="normal")
        self.btn_export_se2.configure(state="normal")
        
        score = 100
        score -= min(25, dlc_count * 5)
        score -= min(25, script_count * 10)
        score -= min(30, subgrid_count * 15)
        score = max(20, score)
        
        self.se2_score_label.configure(text=f"{score}%")
        
        if score >= 90:
            status = "OPTIMAL"
            color = TacticalTheme.GREEN_PRIMARY
        elif score >= 60:
            status = "STABLE"
            color = TacticalTheme.CYAN_PRIMARY
        elif score >= 40:
            status = "COMPLEX"
            color = TacticalTheme.ORANGE_PRIMARY
        else:
            status = "FRAGILE"
            color = TacticalTheme.RED_PRIMARY
            
        self.se2_status_title.configure(text=f"TRANSITION COMPATIBILITY: {status}", text_color=color)
        self.se2_score_label.configure(text_color=color)
        
        desc = (
            "This blueprint has been evaluated for the upcoming VRage3 engine (Space Engineers 2). "
            f"It was rated {status} based on custom script complexity, subgrids, and DLC usage. "
            "Use the utilities below to clean, convert or scale this blueprint."
        )
        self.se2_status_desc.configure(text=desc)
        
        log_text = []
        log_text.append("=== VRAGE3 (SE2) TRANSITION ASSESSMENT ===")
        log_text.append(f"Blueprint: {info.display_name}")
        log_text.append(f"Grid Size: {info.grid_size}")
        log_text.append(f"Total Blocks: {info.block_count}")
        log_text.append("")
        
        if dlc_count > 0:
            log_text.append(f"[!] DLC FOOTPRINT DETECTED: {dlc_count} block(s) require active expansions.")
            log_text.append("    -> VRage3 conversion will require owning matching expansion packs.")
            log_text.append("    -> Tip: Use 'DLC TO BASE CONVERT' below to make this a vanilla build!")
        else:
            log_text.append("[+] NO DLC DETECTED: Clean base-game (Vanilla) build.")
            log_text.append("    -> Exceptional compatibility and highly shareable!")
            
        if script_count > 0:
            log_text.append(f"[!] SCRIPTS DETECTED: {script_count} programmable script host(s) found.")
            log_text.append("    -> VRage3 uses an updated, highly multi-threaded behavior/logic layout.")
            log_text.append("    -> Some older C# scripts might require manual code updates or transitions.")
        else:
            log_text.append("[+] NO SCRIPTS DETECTED: Pure stateful engineering.")
            
        if subgrid_count > 0:
            log_text.append(f"[!] COMPLEX SUBGRIDS DETECTED: {subgrid_count} mechanical rotor/hinge/piston chain(s).")
            log_text.append("    -> Physical clearances and rotor torque settings differ in VRage3.")
            log_text.append("    -> Test integrity carefully after spawning in Space Engineers 2.")
        else:
            log_text.append("[+] NO SUBGRIDS: Single grid layout with optimal structural physics.")
            
        log_text.append("")
        log_text.append("=== RECOMMENDATION ===")
        if score >= 90:
            log_text.append("Ready for seamless transition. Fully compatible with vanilla servers and public sharing!")
        elif score >= 60:
            log_text.append("Good candidate. Ensure any required DLCs are enabled or vanilla-fy the blueprint.")
        else:
            log_text.append("Highly complex. We recommend standardizing blocks and verifying program logic prior to transition.")
            
        self._set_textbox_content(self.se2_audit_textbox, "\n".join(log_text))

    def clear_se2_transition(self):
        self.se2_score_label.configure(text="--", text_color=TacticalTheme.GREEN_PRIMARY)
        self.se2_status_title.configure(text="SELECT BLUEPRINT TO COMMENCE SCAN", text_color=TacticalTheme.CYAN_PRIMARY)
        self.se2_status_desc.configure(text="The blueprint will be thoroughly audited across DLC constraints, mechanical hierarchies, and programmable subsystems for VRage3 (SE2) compatibility.")
        self._set_textbox_content(self.se2_audit_textbox, "Select a blueprint to begin VRage3 Transition Scanning...\n")
        self.btn_vanillafy.configure(state="disabled")
        self.btn_gridsizer.configure(state="disabled")
        self.btn_survival_sanity.configure(state="disabled")
        self.btn_upgrade_prototech.configure(state="disabled")
        self.btn_export_se2.configure(state="disabled")


