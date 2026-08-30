"""
Preview Panel Component
Center tabview with Intel, XML Source, Preview Diff, and Analytics tabs.
"""

from __future__ import annotations

import threading
import tkinter as tk
from queue import Empty, SimpleQueue
from typing import Dict, Iterable, List, Optional

import customtkinter as ctk

from blueprint_analytics import (
    ConversionComparison,
    HealthIssue,
    SE2Readiness,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from subgrid_engine.hierarchy_parser import MultiGridStructure
from ui.labels import category_label
from ui.theme import TacticalTheme
from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.scene_graph import PreviewScene
from ui.widgets.grid_tree import GridHierarchyView
from blueprint_document import subgrids_ui_applies


def subgrids_same_ship_is_noop(
    *,
    path,
    current_path,
    scene,
    pending_scene,
    structure,
    pending_structure,
    rendered_for,
    revision,
) -> bool:
    """Same-ship Subgrids tab revisit must not bump revision or rebuild 3D."""
    if path is None or current_path is None:
        return False
    if str(path) != str(current_path):
        return False
    if scene is not pending_scene or structure is not pending_structure:
        return False
    if rendered_for is None:
        return False
    return int(rendered_for) == int(revision)


def subgrids_voxels_for_ui(will_show_3d: bool, load_voxels=None):
    """Skip voxels_from_scene on Tk when 3D will draw the scene."""
    if will_show_3d:
        return None
    if load_voxels is None:
        return None
    return load_voxels()
from ui.widgets.ship_canvas import voxels_to_blocks
from ui.widgets.ship_preview import ShipPreviewHost


def xml_reload_required(loaded_path, path) -> bool:
    """True when the XML tab must re-read disk (path changed or cache cleared)."""
    return loaded_path != path


def pending_catalog_for(catalog, meshes=None):
    """None catalog clears a queued catalog so File→Clear cannot resurrect it."""
    if catalog is None:
        return None
    return (catalog, meshes)


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
        on_locate_space_engineers=None,
        on_need_subgrids=None,
        on_toast=None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_DARK,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=12,
            **kwargs,
        )
        self._on_run_preview = on_run_preview
        self._on_export_csv = on_export_csv
        self._on_export_txt = on_export_txt
        self._on_apply_fix = on_apply_fix
        self._on_vanillafy = on_vanillafy
        self._on_scale_grid = on_scale_grid
        self._on_locate_space_engineers = on_locate_space_engineers
        self._on_need_subgrids = on_need_subgrids
        self._on_toast = on_toast
        self._subgrids_built = False
        self.ship_preview = None
        self.hierarchy_view = None
        self.ship_canvas = None
        self._pending_se_state = None
        self._pending_catalog = None
        self._pending_source_path = None
        self._latest_health_issues: List[HealthIssue] = []
        self._pending_scene = None
        self._xml_path = None
        self._xml_loaded_path = None
        self._xml_status_text = ""
        self._pending_structure = None
        self._pending_voxels: List[dict] = []
        self._subgrids_rendered_for = None
        self._subgrids_revision = 0
        self._subgrids_generation = 0
        self._subgrids_path = None
        self._subgrids_ship_name = ""
        self._catalog_in_flight = False
        self._catalog_failed = False
        self._install_cleared = False
        self._render_job = None
        self._pending_analytics = None
        self._pending_se2 = None
        self._pending_preview = None
        self._applied_preview_key = None
        self._applied_analytics = None
        self._applied_se2 = None
        self._ui_queue: SimpleQueue = SimpleQueue()

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=TacticalTheme.BG_DARK,
            segmented_button_fg_color=TacticalTheme.BG_MEDIUM,
            segmented_button_selected_color=TacticalTheme.ORANGE_PRIMARY,
            segmented_button_selected_hover_color=TacticalTheme.ORANGE_DIM,
            segmented_button_unselected_color=TacticalTheme.BG_MEDIUM,
            segmented_button_unselected_hover_color=TacticalTheme.BG_GLASS,
            text_color=TacticalTheme.TEXT_GRAY,
            text_color_disabled=TacticalTheme.TEXT_GRAY,
            corner_radius=6,
        )
        self.tabview.pack(fill="both", expand=True, padx=4, pady=4)

        self._build_intel_tab()
        self._build_preview_tab()
        self._build_subgrids_tab()
        self._build_analytics_tab()
        self._build_se2_tab()
        self._build_xml_tab()
        self.tabview.configure(command=self._on_tab_changed)
        self.after(16, self._pump_ui_queue)

    def _ui(self, callback) -> None:
        """Queue a callback for the Tk main thread. Safe to call from workers."""
        self._ui_queue.put(callback)

    def _pump_ui_queue(self) -> None:
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception:
                    pass  # widget may already be destroyed
        except Empty:
            pass  # queue drained
        try:
            self.after(16, self._pump_ui_queue)
        except Exception:
            pass  # panel is gone

    def _build_intel_tab(self):
        self.tab_intel = self.tabview.add("Overview")
        self.tab_intel.configure(fg_color=TacticalTheme.BG_DARK)
        ctk.CTkLabel(
            self.tab_intel,
            text="Ship overview",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(anchor="w", padx=20, pady=(12, 4))
        self.intel_text = ctk.CTkLabel(
            self.tab_intel,
            text="Select a blueprint on the left. We'll show block totals, conversion readiness, and where the file lives — no XML editing required.",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=760,
            anchor="nw",
            justify="left",
        )
        self.intel_text.pack(fill="both", expand=True, padx=20, pady=10)

    def _build_xml_tab(self):
        self.tab_xml = self.tabview.add("XML")
        self.tab_xml.configure(fg_color=TacticalTheme.BG_DARK)

        xml_header = ctk.CTkFrame(self.tab_xml, fg_color="transparent")
        xml_header.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            xml_header,
            text="Blueprint XML",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(side="left")
        self.xml_status = ctk.CTkLabel(
            xml_header,
            text="No file loaded",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.xml_status.pack(side="right")
        self.xml_textbox = ctk.CTkTextbox(
            self.tab_xml,
            font=TacticalTheme.code_font(16),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.xml_textbox.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_preview_tab(self):
        self.tab_preview = self.tabview.add("Preview")
        self.tab_preview.configure(fg_color=TacticalTheme.BG_DARK)

        preview_header = ctk.CTkFrame(self.tab_preview, fg_color="transparent")
        preview_header.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            preview_header,
            text="Before / after",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(side="left")
        ctk.CTkButton(
            preview_header,
            text="Refresh preview",
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            hover_color=TacticalTheme.BG_MEDIUM,
            width=130,
            height=28,
            corner_radius=8,
            command=self._run_preview,
        ).pack(side="right")

        preview_split = ctk.CTkFrame(self.tab_preview, fg_color="transparent")
        preview_split.pack(fill="both", expand=True, padx=8, pady=8)
        preview_split.columnconfigure(0, weight=1)
        preview_split.columnconfigure(1, weight=1)
        preview_split.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            preview_split,
            text="Current blocks",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            preview_split,
            text="After conversion",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))

        self.preview_before_text = ctk.CTkTextbox(
            preview_split,
            font=TacticalTheme.code_font(16),
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
            font=TacticalTheme.code_font(16),
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
            height=140,
            font=TacticalTheme.code_font(16),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=4,
            state="disabled",
        )
        self.preview_summary_text.pack(fill="x", padx=8, pady=(0, 8))

    def _build_subgrids_tab(self):
        self.tab_subgrids = self.tabview.add("Subgrids")
        self.tab_subgrids.configure(fg_color=TacticalTheme.BG_DARK)

    def _ensure_subgrids_widgets(self):
        if self._subgrids_built:
            return
        self._subgrids_built = True
        container = ctk.CTkFrame(self.tab_subgrids, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.columnconfigure(0, weight=2, minsize=260)
        container.columnconfigure(1, weight=5, minsize=420)
        container.rowconfigure(0, weight=1)

        left_box = ctk.CTkFrame(
            container,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=TacticalTheme.BORDER_SUBTLE,
            corner_radius=10,
        )
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(
            left_box,
            text="Grid hierarchy",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(
            left_box,
            text="Main hull first, then rotors, hinges, and pistons. Click a row to isolate it in the preview.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=240,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.hierarchy_view = GridHierarchyView(
            left_box,
            on_select=self._on_hierarchy_select,
        )
        self.hierarchy_view.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.hierarchy_view.render(None)

        self.ship_preview = ShipPreviewHost(
            container,
            on_locate=self._on_locate_space_engineers,
            on_toast=self._on_toast,
        )
        self.ship_preview.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.ship_canvas = self.ship_preview.ship_canvas
        if self._pending_se_state is not None:
            valid, path_text, message = self._pending_se_state[:3]
            cleared = self._pending_se_state[3] if len(self._pending_se_state) > 3 else self._install_cleared
            self.ship_preview.set_install_state(valid, path_text, message, cleared=cleared)
            if valid and not cleared:
                self.ship_preview.prewarm_gl()
        if self._catalog_in_flight:
            self.ship_preview.set_catalog_in_flight(True)
        if self._pending_catalog is not None:
            catalog, meshes = self._pending_catalog
            self.ship_preview.set_catalog(catalog, meshes)
        if self._pending_source_path is not None:
            self.ship_preview.set_blueprint_source(self._pending_source_path)

    def prewarm_subgrids(self) -> None:
        """Build Subgrids chrome after the list first paints so first tab open skips Tk construct."""
        self._ensure_subgrids_widgets()
        self.prewarm_gl()

    def prewarm_gl(self) -> None:
        """Retry try_init once install is valid. No-ops after File→Clear."""
        if self._install_cleared or self.ship_preview is None:
            return
        self.ship_preview.prewarm_gl()

    def current_tab(self) -> str:
        try:
            return self.tabview.get()
        except Exception:
            return "Overview"  # tabview not built yet or already destroyed

    def _on_tab_changed(self):
        name = self.current_tab()
        if name == "Subgrids":
            self._ensure_subgrids_widgets()
            if self._on_need_subgrids:
                self._on_need_subgrids()
            if self._subgrids_rendered_for != self._subgrids_revision:
                self._render_subgrids()
            elif self.ship_preview is not None:
                self.ship_preview.refresh()
        elif name == "XML":
            self._ensure_xml_loaded()
        elif name == "Analytics":
            self._apply_pending_analytics()
        elif name == "SE2":
            self._apply_pending_se2()
        elif name == "Preview":
            self._apply_pending_preview()

    def _on_hierarchy_select(self, grid_name: Optional[str], entity_id: Optional[str] = None):
        if self.ship_preview is not None:
            self.ship_preview.filter_by_grid(grid_name, entity_id)

    def set_se_preview_state(
        self,
        valid: bool,
        path_text: str = "",
        message: str = "",
        *,
        cleared: bool = False,
    ) -> None:
        self._install_cleared = bool(cleared)
        self._pending_se_state = (valid, path_text, message, self._install_cleared)
        if self.ship_preview is not None:
            self.ship_preview.set_install_state(valid, path_text, message, cleared=cleared)
            if valid and not cleared:
                self.ship_preview.prewarm_gl()

    def set_catalog_in_flight(self, pending: bool, *, failed: bool = False) -> None:
        self._catalog_in_flight = bool(pending)
        if pending:
            self._catalog_failed = False
        elif failed:
            self._catalog_failed = True
        if self.ship_preview is not None:
            self.ship_preview.set_catalog_in_flight(pending, failed=failed)

    def set_se_catalog(self, catalog: Optional[CubeBlockCatalog], meshes: Optional[MeshLibrary] = None) -> None:
        if catalog is not None:
            self._catalog_in_flight = False
            self._catalog_failed = False
        self._pending_catalog = pending_catalog_for(catalog, meshes)
        if self.ship_preview is not None:
            if catalog is None:
                self.ship_preview.set_catalog_in_flight(self._catalog_in_flight, failed=self._catalog_failed)
            self.ship_preview.set_catalog(catalog, meshes)

    def begin_blueprint_switch(self, path, ship_name: str = "") -> int:
        """Cancel in-flight Subgrids/3D work for A→B. Keep last shell on screen."""
        if (
            path is not None
            and self._subgrids_path is not None
            and str(self._subgrids_path) == str(path)
            and self.ship_preview is not None
            and getattr(self.ship_preview, "_mesh_ready", False)
            and not getattr(self.ship_preview, "_switching", False)
        ):
            return self._subgrids_generation
        self._subgrids_generation += 1
        self._subgrids_path = path
        self._subgrids_ship_name = ship_name or ""
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None
        if self.ship_preview is not None:
            self.ship_preview.begin_switch(ship_name)
        return self._subgrids_generation

    @property
    def subgrids_generation(self) -> int:
        return self._subgrids_generation

    def update_subgrids(
        self,
        structure: MultiGridStructure,
        matrix_summaries=None,
        voxels: Optional[List[dict]] = None,
        scene: Optional[PreviewScene] = None,
        path=None,
        generation: Optional[int] = None,
        ship_name: str = "",
        defer: bool = True,
    ):
        if generation is not None and not subgrids_ui_applies(
            self._subgrids_generation,
            generation,
            self._subgrids_path,
            path,
        ):
            return
        if path is not None and self._subgrids_path is not None:
            if str(self._subgrids_path) != str(path):
                return
        if subgrids_same_ship_is_noop(
            path=path,
            current_path=self._subgrids_path,
            scene=scene,
            pending_scene=self._pending_scene,
            structure=structure,
            pending_structure=self._pending_structure,
            rendered_for=self._subgrids_rendered_for,
            revision=self._subgrids_revision,
        ):
            return
        if (
            self.ship_preview is not None
            and self.ship_preview.will_show_3d()
            and scene is not None
        ):
            voxels = None
        self._pending_structure = structure
        self._pending_voxels = voxels or []
        self._pending_scene = scene
        if ship_name:
            self._subgrids_ship_name = ship_name
        self._subgrids_revision += 1
        self._subgrids_rendered_for = None
        revision = self._subgrids_revision
        if self.ship_preview is not None:
            self.ship_preview.set_declared_total(getattr(structure, "total_blocks", 0) or 0)
            if self._subgrids_ship_name:
                self.ship_preview._ship_name = self._subgrids_ship_name
        if self.current_tab() != "Subgrids":
            return
        if defer:
            if self._render_job is not None:
                try:
                    self.after_cancel(self._render_job)
                except Exception:
                    pass
            self._render_job = self.after(1, lambda r=revision: self._render_subgrids_if(r))
            return
        self._render_subgrids()

    def _render_subgrids_if(self, revision: int) -> None:
        self._render_job = None
        if revision != self._subgrids_revision:
            return
        self._render_subgrids()

    def _subgrids_render_key(self):
        return self._subgrids_revision

    def _render_subgrids(self):
        self._ensure_subgrids_widgets()
        structure = self._pending_structure
        voxels = self._pending_voxels
        scene = self._pending_scene
        render_key = self._subgrids_render_key()
        if self._subgrids_rendered_for == render_key:
            if self.ship_preview is not None and self.ship_preview._mode == "3d":
                self.ship_preview.refresh()
            return
        self.hierarchy_view.render(structure if structure and getattr(structure, "total_grids", 0) else None)
        if scene is None and not voxels:
            if self.ship_preview is not None and not self.ship_preview._switching:
                self.ship_preview.clear()
            self._subgrids_rendered_for = render_key
            return
        want_3d = self.ship_preview.will_show_3d() and scene is not None
        if want_3d:
            self.ship_preview.load_scene(scene, voxels=None)
        else:
            self.ship_preview.load_structure_data(voxels_to_blocks(voxels), scene=scene)
        self._subgrids_rendered_for = render_key

    def clear_subgrids(self):
        self._pending_structure = None
        self._pending_voxels = []
        self._pending_scene = None
        self._subgrids_revision += 1
        self._subgrids_rendered_for = None
        if self.hierarchy_view is not None:
            self.hierarchy_view.render(None)
        if self.ship_preview is not None:
            self.ship_preview.clear()

    def _build_analytics_tab(self):
        self.tab_analytics = self.tabview.add("Analytics")
        self.tab_analytics.configure(fg_color=TacticalTheme.BG_DARK)

        header = ctk.CTkFrame(self.tab_analytics, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 4))
        ctk.CTkLabel(
            header,
            text="Blueprint analytics",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(side="left")

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.pack(side="right")
        ctk.CTkButton(
            button_row,
            text="Export CSV",
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
            text="Export TXT",
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
                text=name,
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
            text="Block categories",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            body,
            text="Ores → ingots → components",
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
            font=TacticalTheme.code_font(16),
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
            text="Health check",
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
        source = "light" if conversion_mode == "light_to_heavy" else "heavy"
        target = "heavy" if conversion_mode == "light_to_heavy" else "light"
        ready = sum((bp_info.convertible_counts or {}).values())
        lines = [
            f"{bp_info.display_name}",
            f"{bp_info.grid_size} grid  ·  {bp_info.block_count:,} blocks",
            f"{bp_info.light_armor_count:,} light armor  ·  {bp_info.heavy_armor_count:,} heavy armor",
            "",
            f"Direction: {source} → {target}",
            f"{ready:,} blocks will convert with the current settings",
            f"{convertible:,} armor blocks match this direction",
            "",
            f"File: {bp_info.path}",
        ]
        if bp_info.category_counts:
            lines.extend(["", "Blocks by category:"])
            for name, count in sorted(bp_info.category_counts.items()):
                lines.append(f"  {category_label(name)}: {count}")
        self.intel_text.configure(text="\n".join(lines), text_color=TacticalTheme.TEXT_WHITE)

    def clear_intel(self):
        self.intel_text.configure(
            text="Select a blueprint on the left. We'll show block totals, conversion readiness, and where the file lives — no XML editing required.",
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.clear_analytics()
        self.clear_subgrids()
        self._applied_preview_key = None
        self.show_preview_diff(
            {},
            {},
            "Select a blueprint. A live before/after preview appears automatically.",
            switch_tab=False,
        )

    def invalidate_xml(self, file_path=None) -> None:
        """Force the XML tab to re-read disk even when the path is unchanged."""
        path = str(file_path) if file_path is not None else None
        if path is None or self._xml_loaded_path == path:
            self._xml_loaded_path = None

    def load_xml(self, file_path, status_text: str):
        self._xml_path = str(file_path)
        self._xml_status_text = status_text
        self._pending_source_path = file_path
        if self.ship_preview is not None:
            self.ship_preview.set_blueprint_source(file_path)
        if self._xml_loaded_path != self._xml_path:
            self.xml_status.configure(text="Ready — open the XML tab to view it")
        if self.current_tab() == "XML":
            self._ensure_xml_loaded()

    def _ensure_xml_loaded(self):
        path = self._xml_path
        if not path:
            return
        if not xml_reload_required(self._xml_loaded_path, path):
            return
        self.xml_status.configure(text="Opening…")
        XML_PREVIEW_LIMIT = 120000
        status_text = getattr(self, "_xml_status_text", "Blueprint XML")

        def task():
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    chunk = handle.read(XML_PREVIEW_LIMIT + 1)
                truncated = len(chunk) > XML_PREVIEW_LIMIT
                content = chunk[:XML_PREVIEW_LIMIT]
                if truncated:
                    content += "\n\n… truncated so the UI stays responsive. Open the .sbc file in an editor for the full XML."
                header = status_text
            except Exception as exc:
                content = f"Error reading file: {exc}"
                header = f"Could not open XML: {exc}"
            self._ui(lambda c=content, h=header, p=path: self._apply_xml(c, h, p))

        threading.Thread(target=task, daemon=True).start()

    def _apply_xml(self, content: str, status_text: str, path: str):
        if self._xml_path != path:
            return
        self._xml_loaded_path = path
        self._set_textbox_content(self.xml_textbox, content)
        self.xml_status.configure(text=status_text)

    def show_preview_report(self, bp_name: str, mode: str, report: str):
        """
        Backward-compatible API with richer rendering.
        """
        self.show_preview_diff({}, {}, f"Preview: {bp_name}\nDirection: {mode}\n\n{report}")

    def show_preview_diff(
        self,
        before_counts: Dict[str, int],
        after_counts: Dict[str, int],
        summary_text: str,
        switch_tab: bool = False,
    ):
        self._pending_preview = (before_counts, after_counts, summary_text or "")
        if switch_tab:
            self.tabview.set("Preview")
        if self.current_tab() == "Preview" or switch_tab:
            self._apply_pending_preview()

    def _preview_key(self, pending) -> tuple:
        before_counts, after_counts, summary_text = pending
        return (
            tuple(sorted((before_counts or {}).items())),
            tuple(sorted((after_counts or {}).items())),
            summary_text or "",
        )

    def _apply_pending_preview(self):
        pending = self._pending_preview
        if pending is None:
            return
        key = self._preview_key(pending)
        if key == self._applied_preview_key:
            return
        before_counts, after_counts, summary_text = pending
        self._set_textbox_content(
            self.preview_before_text,
            self._format_counts(before_counts, "No matching blocks in this ship."),
        )
        self._set_textbox_content(
            self.preview_after_text,
            self._format_counts(after_counts, "Nothing would change."),
        )
        self._set_textbox_content(self.preview_summary_text, summary_text or "No changes with the current settings.")
        self._applied_preview_key = key

    def update_analytics(self, analytics_result, comparison: Optional[ConversionComparison] = None):
        self._pending_analytics = (analytics_result, comparison)
        if self.current_tab() == "Analytics":
            self._apply_pending_analytics()

    def _apply_pending_analytics(self):
        pending = self._pending_analytics
        if not pending:
            return
        if pending is self._applied_analytics:
            return
        self._applied_analytics = pending
        analytics_result, comparison = pending
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
        self._set_textbox_content(self.resource_tree, "Select a blueprint to see ore, ingot, and component totals.")
        self._populate_health_issues([])
        self._applied_analytics = None
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
                    text="Apply fix",
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
                font=TacticalTheme.FONT_NORMAL,
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
            self.chart_canvas.create_text(10, y + (bar_h / 2), text=category_label(name), fill=TacticalTheme.TEXT_CYAN, anchor="w", font=TacticalTheme.FONT_SMALL)
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
        self.tabview.set("XML")

    def _build_se2_tab(self):
        self.tab_se2 = self.tabview.add("SE2")
        self.tab_se2.configure(fg_color=TacticalTheme.BG_DARK)
        
        scroll_frame = ctk.CTkScrollableFrame(self.tab_se2, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        header_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            header_frame,
            text="Space Engineers 2 readiness",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
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
            font=(TacticalTheme.FONT_FAMILY, 36, "bold"),
            text_color=TacticalTheme.GREEN_PRIMARY,
        )
        self.se2_score_label.pack(side="left", padx=(0, 15))
        
        score_details = ctk.CTkFrame(score_layout, fg_color="transparent")
        score_details.pack(side="left", fill="both", expand=True)
        
        self.se2_status_title = ctk.CTkLabel(
            score_details,
            text="Select a blueprint to score it",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.CYAN_PRIMARY,
            anchor="w",
        )
        self.se2_status_title.pack(anchor="w")
        
        self.se2_status_desc = ctk.CTkLabel(
            score_details,
            text="We'll check DLC usage, scripts, and subgrids so you know how shareable this ship is for Space Engineers 2.",
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
            text="Cleanup tools",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        
        btn_layout = ctk.CTkFrame(actions_frame, fg_color="transparent")
        btn_layout.pack(fill="x", padx=12, pady=(4, 12))
        btn_layout.columnconfigure((0, 1), weight=1)
        
        self.btn_vanillafy = ctk.CTkButton(
            btn_layout,
            text="Replace DLC with vanilla",
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
        self.btn_vanillafy.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        
        self.btn_gridsizer = ctk.CTkButton(
            btn_layout,
            text="Switch large ↔ small grid",
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
        self.btn_gridsizer.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        
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
            text="Readiness notes",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        
        self.se2_audit_textbox = ctk.CTkTextbox(
            self.se2_audit_frame,
            height=220,
            font=TacticalTheme.code_font(16),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_width=0,
        )
        self.se2_audit_textbox.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._set_textbox_content(
            self.se2_audit_textbox,
            "Select a blueprint to see Space Engineers 2 readiness.\n"
        )

    def _vanillafy_clicked(self):
        if self._on_vanillafy:
            self._on_vanillafy()

    def _gridsizer_clicked(self):
        if self._on_scale_grid:
            self._on_scale_grid()

    def update_se2_transition(self, info, readiness: SE2Readiness):
        self._pending_se2 = (info, readiness)
        if self.current_tab() == "SE2":
            self._apply_pending_se2()

    def _apply_pending_se2(self):
        pending = self._pending_se2
        if not pending:
            return
        if pending is self._applied_se2:
            return
        self._applied_se2 = pending
        info, readiness = pending
        self.btn_vanillafy.configure(state="normal")
        self.btn_gridsizer.configure(state="normal")

        score = readiness.score
        status = readiness.status
        dlc_count = readiness.dlc_count
        script_count = readiness.script_count
        subgrid_count = readiness.subgrid_count

        self.se2_score_label.configure(text=f"{score}%")

        if status == "OPTIMAL":
            color = TacticalTheme.GREEN_PRIMARY
        elif status == "STABLE":
            color = TacticalTheme.CYAN_PRIMARY
        elif status == "COMPLEX":
            color = TacticalTheme.ORANGE_PRIMARY
        else:
            color = TacticalTheme.RED_PRIMARY
            
        status_title = {
            "OPTIMAL": "Ready to share",
            "STABLE": "Mostly ready",
            "COMPLEX": "Needs cleanup",
        }.get(status, "High complexity")
        self.se2_status_title.configure(text=status_title, text_color=color)
        self.se2_score_label.configure(text_color=color)
        
        desc = (
            f"Scored {status.lower()} from DLC usage, scripts, and subgrids. "
            "Use the tools below to make a vanilla copy or switch grid size — originals stay untouched."
        )
        self.se2_status_desc.configure(text=desc)
        
        log_text = []
        log_text.append(f"SE2 readiness — {info.display_name}")
        log_text.append(f"{info.grid_size} grid  ·  {info.block_count} blocks")
        log_text.append("")
        
        if dlc_count > 0:
            log_text.append(f"DLC: {dlc_count} block(s) need expansion packs.")
            log_text.append("    Tip: Replace DLC with vanilla to make this freely shareable.")
        else:
            log_text.append("DLC: none — this is a vanilla build.")
            
        if script_count > 0:
            log_text.append(f"Scripts: {script_count} programmable block(s). Some C# may need updates in SE2.")
        else:
            log_text.append("Scripts: none.")
            
        if subgrid_count > 0:
            log_text.append(f"Subgrids: {subgrid_count} rotor/hinge/piston chain(s). Test physics after spawning in SE2.")
        else:
            log_text.append("Subgrids: none — single grid.")
            
        log_text.append("")
        if score >= 90:
            log_text.append("Recommendation: ready to share on vanilla servers.")
        elif score >= 60:
            log_text.append("Recommendation: replace DLC or confirm expansion packs before sharing.")
        else:
            log_text.append("Recommendation: simplify scripts and standardise blocks before transitioning.")
            
        self._set_textbox_content(self.se2_audit_textbox, "\n".join(log_text))

    def clear_se2_transition(self):
        self.se2_score_label.configure(text="--", text_color=TacticalTheme.GREEN_PRIMARY)
        self.se2_status_title.configure(text="Select a blueprint to score it", text_color=TacticalTheme.CYAN_PRIMARY)
        self.se2_status_desc.configure(text="We'll check DLC usage, scripts, and subgrids so you know how shareable this ship is for Space Engineers 2.")
        self._set_textbox_content(self.se2_audit_textbox, "Select a blueprint to see Space Engineers 2 readiness.\n")
        self.btn_vanillafy.configure(state="disabled")
        self.btn_gridsizer.configure(state="disabled")
        self._applied_se2 = None
        self._pending_se2 = None

