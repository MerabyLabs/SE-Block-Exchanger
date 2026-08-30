"""Subgrids right pane: 3D ModernGL preview when possible, else the 2D map."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional, Set
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from blueprint_edit import (
    GridEditSession,
    nudge_block_instance,
    resolve_blueprint_dir,
    save_blueprint_as,
    unique_edited_dir,
)
from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.camera import wheel_zoom_inward, zoom_factor_for_distance
from se_render.gl_backend import last_gl_error
from se_render.dissection import (
    DISSECT_DECKS,
    DISSECT_PEEL,
    DISSECT_RADIAL,
    pick_identity,
    selection_caption,
)
from se_render.preview_build import (
    STAGE_FULL,
    STAGE_MESHES,
    STAGE_SHELL,
    BuildGeneration,
    PreviewCpuScene,
    apply_dissect_mode,
    build_preview_cpu,
    ensure_exploded_batches,
    pending_mwm_definitions,
    refine_mwm_cpu,
)
from se_render.preview_style import (
    INSPECT_CATEGORIES,
    MWM_REFINE_CHUNK,
    PROGRESSIVE_BLOCK_THRESHOLD,
    UPLOAD_BATCH_CHUNK,
    render_target_size,
)
from se_render.scene_graph import PreviewScene
from se_render.viewport import GLPreviewRenderer, scene_bounds_caption
from ui.theme import TacticalTheme
from ui.widgets.ship_canvas import ShipCanvas, VoxelBlock

_CATEGORY_LABELS = {
    "armor": "Armor",
    "functional": "Func",
    "power": "Power",
    "thrust": "Thrust",
    "weapon": "Wpn",
    "cockpit": "Seat",
    "mechanical": "Mech",
    "conveyor": "Conv",
}

_MODE_LABELS = {
    DISSECT_PEEL: "Peel",
    DISSECT_DECKS: "Decks",
    DISSECT_RADIAL: "Radial",
}
_MODE_VALUES = {label: key for key, label in _MODE_LABELS.items()}


class ShipPreviewHost(ctk.CTkFrame):
    """
    Hosts the 2D map always, and a 3D blit canvas when OpenGL and a valid
    Space Engineers install are available.
    """

    _session_explode = 0.0
    _session_dissect_on = False
    _session_dissect_mode = DISSECT_PEEL

    def __init__(
        self,
        master,
        on_locate: Optional[Callable[[], None]] = None,
        on_clear_install: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str, str], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=TacticalTheme.BG_DARK, corner_radius=8, **kwargs)
        self._on_locate = on_locate
        self._on_clear_install = on_clear_install
        self._on_toast = on_toast
        self._mode = "2d"
        self._scene: Optional[PreviewScene] = None
        self._catalog: Optional[CubeBlockCatalog] = None
        self._meshes = MeshLibrary()
        self._grid_filter: Optional[str] = None
        self._grid_entity_id: Optional[str] = None
        self._grid_isolate_key: Optional[str] = None
        self._upload_chunk_job = None
        self._declared_total = 0
        self._renderer: Optional[GLPreviewRenderer] = None
        self._photo = None
        self._photo_size = (0, 0)
        self._canvas_image_id = None
        self._redraw_job = None
        self._redraw_pending = False
        self._interactive = False
        self._drag_x = 0
        self._drag_y = 0
        self._drag_origin = (0, 0)
        self._drag_moved = False
        self._install_valid = False
        self._gl_failed = False
        self._mesh_ready = False
        self._building = False
        self._cpu_stage = ""
        self._simplified = False
        self._shown_count = 0
        self._cpu_scene: Optional[PreviewCpuScene] = None
        self._dissect_preparing = False
        self._wheel_grabbed = False
        self._wheel_grab_warned = False
        self._job = BuildGeneration()
        self._explode = float(self._session_explode)
        self._dissect_mode = str(self._session_dissect_mode or DISSECT_PEEL)
        if self._dissect_mode not in _MODE_LABELS:
            self._dissect_mode = DISSECT_PEEL
        self._selected_label = ""
        self._selected_rec = None
        self._isolated = False
        self._hide_armor = False
        self._hide_layers = 0
        self._hidden_categories: Set[str] = set()
        self._edits = GridEditSession()
        self._source_path: Optional[Path] = None
        self._idle_job = None
        self._save_generation = 0

        self._banner = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, corner_radius=8)
        self._banner.pack(fill="x", padx=8, pady=(8, 0))
        self._banner_label = ctk.CTkLabel(
            self._banner,
            text="3D preview uses your local Space Engineers files. The 2D map stays available.",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            wraplength=520,
            justify="left",
            anchor="w",
        )
        self._banner_label.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self._locate_btn = ctk.CTkButton(
            self._banner,
            text="Locate Space Engineers…",
            width=190,
            height=28,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            command=self._emit_locate,
        )
        self._locate_btn.pack(side="right", padx=8, pady=8)

        self._stack = ctk.CTkFrame(self, fg_color="transparent")
        self._stack.pack(fill="both", expand=True)

        self.ship_canvas = ShipCanvas(self._stack)
        self.ship_canvas.pack(fill="both", expand=True)

        self._gl_frame = ctk.CTkFrame(self._stack, fg_color=TacticalTheme.BG_DARK, corner_radius=8)
        toolbar = ctk.CTkFrame(self._gl_frame, fg_color=TacticalTheme.BG_GLASS, height=40, corner_radius=8)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            toolbar,
            text="3D",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(10, 6))
        self._gl_status = ctk.CTkLabel(
            toolbar,
            text="No ship loaded",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        self._gl_status.pack(side="left", padx=8)

        self._focus_btn = ctk.CTkButton(
            toolbar,
            text="Focus",
            width=64,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._focus_selection,
        )
        self._focus_btn.pack(side="right", padx=4)
        ctk.CTkButton(
            toolbar,
            text="Fit",
            width=70,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            command=self.fit_to_view,
        ).pack(side="right", padx=8)
        ctk.CTkButton(
            toolbar,
            text="+",
            width=36,
            height=30,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=lambda: self._zoom(0.85),
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            toolbar,
            text="−",
            width=36,
            height=30,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=lambda: self._zoom(1.15),
        ).pack(side="right", padx=2)
        dissect_bar = ctk.CTkFrame(self._gl_frame, fg_color=TacticalTheme.BG_GLASS, height=40, corner_radius=8)
        dissect_bar.pack(fill="x", padx=8, pady=(0, 4))
        self._hide_armor_btn = ctk.CTkButton(
            dissect_bar,
            text="Hide armor",
            width=96,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._toggle_hide_armor,
        )
        self._hide_armor_btn.pack(side="left", padx=(8, 4), pady=5)
        self._isolate_btn = ctk.CTkButton(
            dissect_bar,
            text="Isolate",
            width=72,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._toggle_isolate,
        )
        self._isolate_btn.pack(side="left", padx=4, pady=5)
        self._reset_btn = ctk.CTkButton(
            dissect_bar,
            text="Reset",
            width=56,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._reset_dissect,
        )
        self._reset_btn.pack(side="right", padx=4, pady=5)
        self._dissect_slider = ctk.CTkSlider(
            dissect_bar,
            from_=0,
            to=100,
            width=110,
            command=self._on_dissect_slider,
        )
        self._dissect_slider.set(self._explode * 100.0)
        self._dissect_slider.pack(side="right", padx=4, pady=5)
        self._dissect_btn = ctk.CTkButton(
            dissect_bar,
            text="Dissect",
            width=72,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._toggle_dissect,
        )
        self._dissect_btn.pack(side="right", padx=4, pady=5)
        self._mode_menu = ctk.CTkOptionMenu(
            dissect_bar,
            values=["Peel", "Decks", "Radial"],
            width=88,
            height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._on_dissect_mode,
        )
        self._mode_menu.set(_MODE_LABELS.get(self._dissect_mode, "Peel"))
        self._mode_menu.pack(side="right", padx=4, pady=5)

        inspect_bar = ctk.CTkFrame(self._gl_frame, fg_color=TacticalTheme.BG_GLASS, height=40, corner_radius=8)
        inspect_bar.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkLabel(
            inspect_bar,
            text="Inspect",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(8, 4), pady=5)
        ctk.CTkLabel(
            inspect_bar,
            text="Outer",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(4, 2), pady=5)
        self._layer_slider = ctk.CTkSlider(
            inspect_bar,
            from_=0,
            to=8,
            number_of_steps=8,
            width=90,
            command=self._on_layer_slider,
        )
        self._layer_slider.set(0)
        self._layer_slider.pack(side="left", padx=2, pady=5)
        self._layer_label = ctk.CTkLabel(
            inspect_bar,
            text="0",
            width=18,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_WHITE,
        )
        self._layer_label.pack(side="left", padx=2, pady=5)
        self._reset_vis_btn = ctk.CTkButton(
            inspect_bar,
            text="Reset vis",
            width=72,
            height=28,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._reset_visibility,
        )
        self._reset_vis_btn.pack(side="left", padx=4, pady=5)
        self._cat_buttons = {}
        for key in INSPECT_CATEGORIES:
            btn = ctk.CTkButton(
                inspect_bar,
                text=_CATEGORY_LABELS.get(key, key),
                width=46,
                height=28,
                font=TacticalTheme.FONT_SMALL,
                fg_color=TacticalTheme.BG_DARK,
                text_color=TacticalTheme.TEXT_WHITE,
                command=lambda k=key: self._toggle_category(k),
            )
            btn.pack(side="left", padx=1, pady=5)
            self._cat_buttons[key] = btn
        self._hide_type_btn = ctk.CTkButton(
            inspect_bar,
            text="Hide type",
            width=78,
            height=28,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=self._hide_selected_type,
        )
        self._hide_type_btn.pack(side="right", padx=4, pady=5)

        edit_bar = ctk.CTkFrame(self._gl_frame, fg_color=TacticalTheme.BG_GLASS, height=36, corner_radius=8)
        edit_bar.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkLabel(
            edit_bar,
            text="Edit",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(8, 4), pady=4)
        self._delete_btn = ctk.CTkButton(
            edit_bar, text="Delete", width=64, height=28, font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_WHITE,
            command=self._delete_selected,
        )
        self._delete_btn.pack(side="left", padx=2, pady=4)
        self._hide_sel_btn = ctk.CTkButton(
            edit_bar, text="Hide", width=52, height=28, font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_WHITE,
            command=self._hide_selected,
        )
        self._hide_sel_btn.pack(side="left", padx=2, pady=4)
        for label, delta in (("←", (-1, 0, 0)), ("→", (1, 0, 0)), ("↑", (0, 1, 0)), ("↓", (0, -1, 0))):
            ctk.CTkButton(
                edit_bar, text=label, width=32, height=28, font=TacticalTheme.FONT_SMALL,
                fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_WHITE,
                command=lambda d=delta: self._nudge_selected(d),
            ).pack(side="left", padx=1, pady=4)
        self._undo_btn = ctk.CTkButton(
            edit_bar, text="Undo", width=52, height=28, font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_WHITE,
            command=self._undo_edit,
        )
        self._undo_btn.pack(side="left", padx=4, pady=4)
        self._save_btn = ctk.CTkButton(
            edit_bar, text="Save as new…", width=100, height=28, font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.CYAN_PRIMARY, text_color=TacticalTheme.BG_DARK,
            command=self._save_as_new,
        )
        self._save_btn.pack(side="right", padx=8, pady=4)
        self._set_dissect_enabled(False)

        canvas_box = ctk.CTkFrame(self._gl_frame, fg_color="#080e1a", corner_radius=8)
        canvas_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._gl_canvas = tk.Canvas(canvas_box, bg="#070c18", highlightthickness=0, bd=0)
        self._gl_canvas.pack(fill="both", expand=True)
        self._gl_canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._gl_canvas.bind("<B1-Motion>", self._on_orbit)
        self._gl_canvas.bind("<ButtonRelease-1>", lambda e: self._on_drag_end(e, pick=True))
        self._gl_canvas.bind("<ButtonPress-3>", self._on_drag_start)
        self._gl_canvas.bind("<B3-Motion>", self._on_pan)
        self._gl_canvas.bind("<ButtonRelease-3>", lambda e: self._on_drag_end(e, pick=False))
        self._gl_canvas.bind("<MouseWheel>", self._on_wheel)
        self._gl_canvas.bind("<Button-4>", self._on_wheel)
        self._gl_canvas.bind("<Button-5>", self._on_wheel)
        self._gl_frame.bind("<MouseWheel>", self._on_wheel)
        self._gl_frame.bind("<Button-4>", self._on_wheel)
        self._gl_frame.bind("<Button-5>", self._on_wheel)
        self._gl_canvas.bind("<Configure>", lambda _e: self._schedule_redraw())
        self._gl_canvas.bind("<Enter>", self._on_gl_enter)
        self._gl_frame.bind("<Enter>", self._on_gl_enter)
        self._gl_frame.bind("<Leave>", self._on_gl_leave)
        self._bind_slider_wheel_passthrough()
        self._gl_canvas.bind("<KeyPress-bracketleft>", self._on_bracket_left)
        self._gl_canvas.bind("<KeyPress-bracketright>", self._on_bracket_right)
        self._gl_canvas.bind("<KeyPress-f>", lambda _e: self._focus_selection())
        self._gl_canvas.bind("<KeyPress-F>", lambda _e: self._focus_selection())
        self._gl_canvas.bind("<KeyPress-Escape>", lambda _e: self._clear_and_fit())
        self._gl_canvas.bind("<KeyPress-Delete>", lambda _e: self._delete_selected())
        self._gl_canvas.bind("<Left>", lambda _e: self._nudge_selected((-1, 0, 0)))
        self._gl_canvas.bind("<Right>", lambda _e: self._nudge_selected((1, 0, 0)))
        self._gl_canvas.bind("<Up>", lambda _e: self._nudge_selected((0, 1, 0)))
        self._gl_canvas.bind("<Down>", lambda _e: self._nudge_selected((0, -1, 0)))
        self._gl_canvas.bind("<Double-Button-1>", self._on_double_click)

    def _emit_locate(self) -> None:
        if self._on_locate:
            self._on_locate()

    def set_declared_total(self, total: int) -> None:
        self._declared_total = max(0, int(total))

    def set_install_state(self, valid: bool, path_text: str = "", message: str = "") -> None:
        self._install_valid = bool(valid)
        if valid:
            shown = path_text or "Space Engineers install"
            self._banner_label.configure(
                text=f"Using official models from {shown}",
                text_color=TacticalTheme.TEXT_CYAN,
            )
            self._locate_btn.configure(text="Change folder…")
            if self._scene is not None and not self._mesh_ready:
                self._start_build()
        else:
            self._cancel_build()
            self._mesh_ready = False
            if self._renderer is not None:
                self._renderer.clear_scene()
            self._set_dissect_enabled(False)
            self._banner_label.configure(
                text=message or "Space Engineers was not found. Locate the game folder for the 3D preview, or use the 2D map.",
                text_color=TacticalTheme.TEXT_GRAY,
            )
            self._locate_btn.configure(text="Locate Space Engineers…")
        self._apply_mode()

    def set_catalog(self, catalog: Optional[CubeBlockCatalog], meshes: Optional[MeshLibrary] = None) -> None:
        self._catalog = catalog
        if meshes is not None:
            self._meshes = meshes
        elif catalog is not None and catalog.install is not None:
            self._meshes.set_install(catalog.install)
        if self._scene is not None and self._install_valid:
            self._start_build()

    def load_structure_data(self, blocks: List[VoxelBlock], scene: Optional[PreviewScene] = None) -> None:
        self._scene = scene
        self._grid_filter = None
        self._grid_entity_id = None
        self._grid_isolate_key = None
        self._mesh_ready = False
        self._building = False
        self._cpu_stage = ""
        self._simplified = False
        self._shown_count = 0
        self._cpu_scene = None
        self._dissect_preparing = False
        self._edits = GridEditSession(source_path=self._source_path)
        self._hide_armor = False
        self._hide_layers = 0
        self._hidden_categories.clear()
        self._clear_selection()
        if self._renderer is not None:
            self._renderer.camera_user_moved = False
            self._renderer.hide_armor = False
            self._renderer.hide_layers = 0
            self._renderer.category_mask = 0
        want_3d = bool(self._install_valid and scene is not None)
        self.ship_canvas.load_structure_data(blocks, draw=not want_3d)
        self._apply_mode()
        if want_3d:
            self._start_build()

    def filter_by_grid(
        self,
        grid_name: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
    ) -> None:
        self.isolate_grid(grid_name, grid_entity_id)

    def isolate_grid(
        self,
        grid_name: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
    ) -> None:
        """Isolate one CubeGrid by entity id. Fit if already isolated — no remesh."""
        key = grid_entity_id or grid_name
        already = key == self._grid_isolate_key
        self._grid_filter = grid_name
        self._grid_entity_id = grid_entity_id
        self._grid_isolate_key = key
        self.ship_canvas.filter_by_grid(grid_name, grid_entity_id)
        if self._mode == "2d" or not self._mesh_ready or self._renderer is None:
            return
        if already:
            self.fit_to_view()
            return
        self._sync_user_hidden()
        self._renderer.refit_to_visible()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def clear(self) -> None:
        self._cancel_build()
        self._scene = None
        self._grid_filter = None
        self._grid_entity_id = None
        self._grid_isolate_key = None
        self._mesh_ready = False
        self._building = False
        self._cpu_stage = ""
        self._simplified = False
        self._shown_count = 0
        self._cpu_scene = None
        self._dissect_preparing = False
        self._clear_selection()
        self.ship_canvas.clear()
        self._hide_armor = False
        self._hide_layers = 0
        self._hidden_categories.clear()
        self._edits = GridEditSession(source_path=self._source_path)
        if self._renderer is not None:
            self._renderer.clear_scene()
            self._renderer.select(None)
            self._renderer.hide_armor = False
            self._renderer.hide_layers = 0
            self._renderer.category_mask = 0
            self._renderer.hidden_subtypes = set()
            self._renderer.hidden_ids = set()
        self._gl_status.configure(text="No ship loaded")
        self._gl_canvas.delete("all")
        self._photo = None
        self._photo_size = (0, 0)
        self._canvas_image_id = None
        self._set_dissect_enabled(False)
        self._apply_mode()

    def refresh(self) -> None:
        if self._mode == "3d":
            self._schedule_redraw()
        else:
            self.ship_canvas.refresh()

    def fit_to_view(self) -> None:
        if self._mode == "3d" and self._renderer is not None:
            self._renderer.refit_to_visible()
            self._schedule_redraw(interactive=False)
        else:
            self.ship_canvas.fit_to_view()

    def _cancel_chunk_job(self) -> None:
        if self._upload_chunk_job is not None:
            try:
                self.after_cancel(self._upload_chunk_job)
            except Exception:
                pass
            self._upload_chunk_job = None
        if self._renderer is not None:
            self._renderer.cancel_chunked_upload()

    def _cancel_build(self) -> None:
        self._job.cancel()
        self._cancel_chunk_job()

    def _start_build(self) -> None:
        if not self._install_valid or self._gl_failed or self._scene is None:
            return
        gen = self._job.begin()
        self._building = True
        self._mesh_ready = False
        self._cpu_stage = ""
        n = len(self._scene.blocks)
        progressive = n > PROGRESSIVE_BLOCK_THRESHOLD
        self._gl_status.configure(
            text=f"Building 3D preview…  ({n:,} blocks)" if n else "Building 3D preview…"
        )
        self._apply_mode()
        scene = self._scene
        catalog = self._catalog
        library = self._meshes
        install = None
        if catalog is not None and catalog.install is not None:
            install = catalog.install
        elif library.install is not None:
            install = library.install
        if install is not None and library.install != install:
            library.set_install(install)
        first_stage = STAGE_SHELL if progressive else STAGE_FULL

        def task() -> None:
            try:
                cpu = build_preview_cpu(
                    scene, catalog, library, generation=gen, stage=first_stage, cancel=self._job
                )
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_build_failed(gen, message))
                return
            self.after(0, lambda: self._on_build_ready(gen, cpu, refine=progressive))

        threading.Thread(target=task, daemon=True).start()

    def _on_build_failed(self, generation: int, message: str) -> None:
        if not self._job.is_current(generation):
            return
        self._building = False
        self._mesh_ready = False
        self._gl_status.configure(text=f"3D preview failed: {message}")
        self._toast(f"3D preview failed: {message}", "error")
        renderer = self._renderer
        if renderer is None or not renderer.available:
            self._gl_failed = True
        self._apply_mode()

    def _on_build_ready(self, generation: int, cpu: PreviewCpuScene, refine: bool = False) -> None:
        if not self._job.is_current(generation) or not self._install_valid:
            return
        renderer = self._ensure_renderer()
        if renderer is None:
            self._building = False
            self._apply_mode()
            return
        if not self._upload_cpu(cpu):
            return
        self._mesh_ready = True
        self._cpu_scene = cpu
        self._cpu_stage = cpu.stage
        self._simplified = bool(cpu.simplified)
        self._shown_count = int(cpu.shown_count or 0)
        self._set_dissect_enabled(True)
        self._apply_dissect_chrome()
        self._sync_user_hidden()
        self._apply_mode()
        self._refresh_status()
        self._schedule_redraw(interactive=False)
        more = False
        if refine and cpu.has_functional_mwm:
            more = True
            self.after(16, lambda: self._start_mwm_refine(generation))
        elif refine:
            more = True
            self.after(16, lambda: self._start_interior_fill(generation))
        elif cpu.huge and cpu.stage == STAGE_FULL and cpu.exploded:
            self.after(16, lambda: self._finish_secondary_upload(generation))
        self._building = more

    def _start_refine(self, generation: int, stage: str) -> None:
        if not self._job.is_current(generation) or not self._install_valid:
            return
        if self._scene is None:
            return
        scene = self._scene
        catalog = self._catalog
        library = self._meshes
        prior = self._cpu_scene

        def task() -> None:
            try:
                cpu = build_preview_cpu(
                    scene, catalog, library, generation=generation, stage=stage,
                    cancel=self._job, prior=prior,
                )
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_refine_failed(generation, message))
                return
            self.after(0, lambda: self._on_refine_ready(generation, cpu))

        threading.Thread(target=task, daemon=True).start()

    def _start_mwm_refine(self, generation: int, remaining=None) -> None:
        if not self._job.is_current(generation) or not self._install_valid or self._scene is None:
            return
        catalog = self._catalog
        library = self._meshes
        pending = remaining
        if pending is None:
            pending = pending_mwm_definitions(self._scene.blocks, catalog, library)
        if not pending:
            self.after(16, lambda: self._start_interior_fill(generation))
            return
        chunk = pending[:MWM_REFINE_CHUNK]
        leftover = pending[MWM_REFINE_CHUNK:]
        scene = self._scene
        prior = self._cpu_scene

        def task() -> None:
            try:
                for definition in chunk:
                    library.mesh_for(definition, skip_mwm=False)
                if prior is None:
                    cpu = build_preview_cpu(
                        scene, catalog, library, generation=generation, stage=STAGE_MESHES,
                        cancel=self._job, prior=prior,
                    )
                else:
                    cpu = refine_mwm_cpu(prior, catalog, library, chunk)
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_refine_failed(generation, message))
                return
            self.after(0, lambda: self._on_mwm_chunk(generation, cpu, leftover))

        threading.Thread(target=task, daemon=True).start()

    def _on_mwm_chunk(self, generation: int, cpu: PreviewCpuScene, leftover) -> None:
        if not self._job.is_current(generation) or not self._install_valid:
            return
        if self._renderer is None or not self._mesh_ready:
            return
        if not self._upload_cpu(cpu, refit=False, patch=True):
            self._building = False
            return
        self._cpu_scene = cpu
        self._cpu_stage = cpu.stage
        self._simplified = bool(cpu.simplified)
        self._shown_count = int(cpu.shown_count or 0)
        self._refresh_status()
        self._schedule_redraw(interactive=False)
        if leftover:
            self._building = True
            self.after(16, lambda: self._start_mwm_refine(generation, leftover))
        else:
            self._building = True
            self.after(16, lambda: self._start_interior_fill(generation))

    def _start_interior_fill(self, generation: int) -> None:
        if not self._job.is_current(generation) or self._cpu_scene is None:
            return
        cpu = self._cpu_scene
        if cpu.exploded:
            if self._explode > 1e-4:
                self._start_dissect_prepare(generation)
            else:
                try:
                    if self._renderer is not None:
                        self._renderer._cpu = cpu
                        self._renderer.upload_secondary_sets()
                except Exception:
                    pass
                self._building = False
                self._refresh_status()
            return
        catalog = self._catalog
        library = self._meshes

        def task() -> None:
            try:
                ensure_exploded_batches(cpu, catalog, library)
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_refine_failed(generation, message))
                return
            self.after(0, lambda: self._on_interior_filled(generation))

        threading.Thread(target=task, daemon=True).start()

    def _on_interior_filled(self, generation: int) -> None:
        if not self._job.is_current(generation) or self._cpu_scene is None:
            return
        cpu = self._cpu_scene
        if self._renderer is not None and cpu.exploded:
            try:
                self._renderer._cpu = cpu
                self._renderer.upload_secondary_sets()
            except Exception:
                pass
        if self._explode > 1e-4:
            self._start_dissect_prepare(generation)
        else:
            self._building = False
            self._refresh_status()

    def _start_dissect_prepare(self, generation: int, mode: Optional[str] = None) -> None:
        if not self._job.is_current(generation) or self._cpu_scene is None:
            return
        if self._dissect_preparing:
            return
        self._dissect_preparing = True
        cpu = self._cpu_scene
        catalog = self._catalog
        library = self._meshes
        wanted = mode or self._dissect_mode

        def task() -> None:
            try:
                ensure_exploded_batches(cpu, catalog, library)
                apply_dissect_mode(cpu, wanted, catalog)
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_refine_failed(generation, message))
                self._dissect_preparing = False
                return
            self.after(0, lambda: self._on_dissect_ready(generation, wanted))

        threading.Thread(target=task, daemon=True).start()

    def _on_dissect_ready(self, generation: int, mode: str) -> None:
        self._dissect_preparing = False
        if not self._job.is_current(generation) or self._renderer is None or self._cpu_scene is None:
            return
        cpu = self._cpu_scene
        try:
            if cpu.exploded:
                self._renderer._cpu = cpu
                self._renderer.upload_secondary_sets()
            offsets = None
            if mode == DISSECT_DECKS:
                offsets = cpu.offset_decks
            elif mode == DISSECT_RADIAL:
                offsets = cpu.offset_radial
            else:
                offsets = cpu.offset_peel
            if offsets is not None:
                self._renderer.write_dissect_offsets(mode, offsets)
        except Exception:
            pass
        self._building = False
        self._refresh_status()
        if self._explode > 1e-4:
            self._schedule_redraw(interactive=False)

    def _on_refine_failed(self, generation: int, message: str) -> None:
        if not self._job.is_current(generation):
            return
        self._building = False
        self._dissect_preparing = False
        self._toast(f"3D refine failed: {message}", "warning")
        self._refresh_status()

    def _on_refine_ready(self, generation: int, cpu: PreviewCpuScene) -> None:
        if not self._job.is_current(generation) or not self._install_valid:
            return
        if self._renderer is None or not self._mesh_ready:
            return
        if not self._upload_cpu(cpu, refit=False):
            self._building = False
            return
        self._cpu_scene = cpu
        self._cpu_stage = cpu.stage
        self._simplified = bool(cpu.simplified)
        self._shown_count = int(cpu.shown_count or 0)
        self._building = False
        self._refresh_status()
        self._schedule_redraw(interactive=False)
        if cpu.huge and cpu.exploded:
            self.after(16, lambda: self._finish_secondary_upload(generation))

    def _upload_cpu(
        self,
        cpu: PreviewCpuScene,
        *,
        refit: bool = True,
        chunked: bool = True,
        patch: bool = False,
    ) -> bool:
        renderer = self._ensure_renderer()
        if renderer is None:
            self._gl_status.configure(text=last_gl_error() or "OpenGL preview is unavailable.")
            self._gl_failed = True
            self._building = False
            self._apply_mode()
            return False
        try:
            if patch:
                self._cancel_chunk_job()
                renderer.patch_assembled(cpu)
            elif chunked and len(cpu.assembled) > UPLOAD_BATCH_CHUNK:
                more = renderer.begin_cpu_upload(
                    cpu,
                    grid_filter=self._grid_filter,
                    grid_entity_id=self._grid_entity_id,
                    defer_secondary=cpu.huge or cpu.stage != STAGE_FULL,
                    refit=refit,
                )
                if more:
                    gen = self._job.generation
                    self._upload_chunk_job = self.after_idle(lambda: self._continue_gl_upload(gen))
            else:
                renderer.upload_cpu_scene(
                    cpu,
                    grid_filter=self._grid_filter,
                    defer_secondary=cpu.huge or cpu.stage != STAGE_FULL,
                    refit=refit,
                )
            renderer.explode = self._explode
            renderer.dissect_mode = self._dissect_mode
            renderer.hide_armor = self._hide_armor
            if refit and not patch:
                self._clear_selection()
                renderer.select(None)
            return True
        except Exception as exc:
            reason = last_gl_error() or str(exc)
            self._toast(f"3D upload failed: {reason}", "error")
            self._gl_status.configure(text=f"3D preview failed: {reason}")
            if not renderer.available:
                self._gl_failed = True
                self._mesh_ready = False
                self._building = False
                self._apply_mode()
            return False

    def _continue_gl_upload(self, generation: int) -> None:
        self._upload_chunk_job = None
        if not self._job.is_current(generation) or self._renderer is None:
            return
        try:
            more = self._renderer.continue_cpu_upload()
        except Exception:
            return
        self._sync_user_hidden()
        self._refresh_status()
        self._schedule_redraw(interactive=False)
        if more:
            self._upload_chunk_job = self.after_idle(lambda: self._continue_gl_upload(generation))

    def _finish_secondary_upload(self, generation: int) -> None:
        if not self._job.is_current(generation) or not self._install_valid:
            return
        if self._renderer is None or not self._mesh_ready:
            return
        try:
            self._renderer.upload_secondary_sets()
        except Exception:
            return
        if self._explode > 1e-4:
            self._schedule_redraw(interactive=False)

    def _ensure_renderer(self) -> Optional[GLPreviewRenderer]:
        if self._gl_failed:
            return None
        if self._renderer is not None:
            return self._renderer if self._renderer.available else None
        renderer = GLPreviewRenderer()
        if not renderer.available:
            self._gl_failed = True
            return None
        self._renderer = renderer
        return renderer

    def _apply_mode(self) -> None:
        want_3d = self._install_valid and not self._gl_failed and (self._mesh_ready or self._building)
        if want_3d:
            renderer = self._ensure_renderer()
            if renderer is None:
                want_3d = False
        new_mode = "3d" if want_3d else "2d"
        if new_mode == self._mode and self._gl_frame.winfo_ismapped() == (new_mode == "3d"):
            return
        self._mode = new_mode
        if new_mode == "3d":
            self.ship_canvas.pack_forget()
            self._gl_frame.pack(fill="both", expand=True)
        else:
            self._gl_frame.pack_forget()
            self.ship_canvas.pack(fill="both", expand=True)
            if self.ship_canvas.blocks:
                self.ship_canvas.refresh()

    def _refresh_status(self) -> None:
        if self._scene is None:
            self._gl_status.configure(text="No ship loaded")
            return
        uploading = self._renderer is not None and self._renderer.upload_pending()
        uploaded = self._renderer.uploaded_instance_count() if self._renderer is not None else 0
        if uploading:
            shown = uploaded
        elif self._simplified:
            shown = self._shown_count
        else:
            shown = None
        text = scene_bounds_caption(
            self._scene,
            self._grid_filter,
            self._declared_total,
            shown=shown,
            simplified=self._simplified,
            grid_entity_id=self._grid_entity_id,
            uploading=uploading,
        )
        if self._building and not self._mesh_ready:
            text = "Building 3D preview…"
        elif self._building:
            text += "  ·  refining"
        if self._explode > 1e-4:
            mode = _MODE_LABELS.get(self._dissect_mode, "Peel")
            text += f"  ·  {mode} {int(round(self._explode * 100))}%"
        if self._hide_armor:
            text += "  ·  armor hidden"
        if self._hide_layers:
            text += f"  ·  hide {self._hide_layers} shell"
        if self._selected_label:
            text += f"  ·  {self._selected_label}"
        if self._isolated:
            text += "  ·  isolated"
        self._gl_status.configure(text=text)

    def _set_dissect_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (
            self._dissect_btn,
            self._dissect_slider,
            self._reset_btn,
            self._mode_menu,
            self._hide_armor_btn,
            self._isolate_btn,
            self._layer_slider,
            self._reset_vis_btn,
            self._hide_type_btn,
            self._delete_btn,
            self._hide_sel_btn,
            self._undo_btn,
            self._save_btn,
            self._focus_btn,
        ):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        for btn in getattr(self, "_cat_buttons", {}).values():
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _apply_dissect_chrome(self) -> None:
        on = self._explode > 1e-4
        ShipPreviewHost._session_dissect_on = on
        ShipPreviewHost._session_explode = self._explode
        ShipPreviewHost._session_dissect_mode = self._dissect_mode
        try:
            self._dissect_slider.set(self._explode * 100.0)
        except Exception:
            pass
        wanted = _MODE_LABELS.get(self._dissect_mode, "Peel")
        try:
            if str(self._mode_menu.get()) != wanted:
                self._mode_menu.set(wanted)
        except Exception:
            pass
        self._dissect_btn.configure(
            fg_color=TacticalTheme.CYAN_PRIMARY if on else TacticalTheme.BG_DARK,
            text_color=TacticalTheme.BG_DARK if on else TacticalTheme.TEXT_WHITE,
        )
        self._hide_armor_btn.configure(
            fg_color=TacticalTheme.CYAN_PRIMARY if self._hide_armor else TacticalTheme.BG_DARK,
            text_color=TacticalTheme.BG_DARK if self._hide_armor else TacticalTheme.TEXT_WHITE,
            text="Show armor" if self._hide_armor else "Hide armor",
        )
        self._isolate_btn.configure(
            fg_color=TacticalTheme.CYAN_PRIMARY if self._isolated else TacticalTheme.BG_DARK,
            text_color=TacticalTheme.BG_DARK if self._isolated else TacticalTheme.TEXT_WHITE,
        )
        if self._renderer is not None:
            self._renderer.explode = self._explode
            self._renderer.dissect_mode = self._dissect_mode
            self._renderer.hide_armor = self._hide_armor
            self._renderer.isolate_id = (
                float(self._selected_rec.instance_id) if self._isolated and self._selected_rec else -1.0
            )
            self._renderer.hide_layers = self._hide_layers
            self._renderer.category_mask = self._category_mask()

    def _toggle_dissect(self) -> None:
        if not self._mesh_ready:
            return
        if self._explode > 1e-4:
            self._set_explode(0.0)
        else:
            self._set_explode(0.55)

    def _reset_dissect(self) -> None:
        self._clear_selection()
        if self._renderer is not None:
            self._renderer.select(None)
        self._set_explode(0.0)

    def _on_dissect_mode(self, label: str) -> None:
        self._dissect_mode = _MODE_VALUES.get(str(label), DISSECT_PEEL)
        self._apply_dissect_chrome()
        self._refresh_status()
        if self._mesh_ready and self._explode > 1e-4:
            self._ensure_dissect_ready()
        if self._mesh_ready:
            self._schedule_redraw(interactive=True)
            self._arm_idle_redraw()

    def _toggle_hide_armor(self) -> None:
        if not self._mesh_ready:
            return
        self._hide_armor = not self._hide_armor
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _toggle_isolate(self) -> None:
        if not self._mesh_ready or self._selected_rec is None:
            return
        self._isolated = not self._isolated
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _clear_selection(self) -> None:
        self._selected_label = ""
        self._selected_rec = None
        self._isolated = False
        if self._renderer is not None:
            self._renderer.isolate_id = -1.0

    def _on_dissect_slider(self, value) -> None:
        if not self._mesh_ready:
            return
        self._set_explode(float(value) / 100.0)

    def _nudge_explode(self, delta: float) -> None:
        if not self._mesh_ready:
            return
        self._set_explode(self._explode + delta)

    def _set_explode(self, amount: float) -> None:
        self._explode = max(0.0, min(1.0, float(amount)))
        if self._explode > 1e-4:
            self._ensure_dissect_ready()
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=True)
        self._arm_idle_redraw()

    def _ensure_dissect_ready(self) -> None:
        cpu = self._cpu_scene
        if cpu is None or not self._mesh_ready:
            return
        mode = self._dissect_mode
        have_offsets = mode in (cpu.dissect_modes or ())
        have_exploded = bool(cpu.exploded)
        if have_offsets and have_exploded:
            if self._renderer is not None and self._renderer._secondary_pending:
                try:
                    self._renderer.upload_secondary_sets()
                except Exception:
                    pass
            return
        self._start_dissect_prepare(self._job.generation, mode)

    def _arm_idle_redraw(self) -> None:
        if self._idle_job is not None:
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
        self._idle_job = self.after(160, self._idle_redraw)

    def _idle_redraw(self) -> None:
        self._idle_job = None
        self._schedule_redraw(interactive=False)

    def _schedule_redraw(self, interactive: Optional[bool] = None) -> None:
        if interactive is not None:
            self._interactive = interactive
        if self._redraw_pending:
            return
        self._redraw_pending = True
        self._redraw_job = self.after(1, self._blit)

    def _blit(self) -> None:
        self._redraw_job = None
        self._redraw_pending = False
        if self._mode != "3d" or self._renderer is None:
            return
        w = max(self._gl_canvas.winfo_width(), 64)
        h = max(self._gl_canvas.winfo_height(), 64)
        if w < 40 or h < 40:
            self.after(80, self._schedule_redraw)
            return
        try:
            raw = self._renderer.render(w, h, interactive=self._interactive)
        except Exception as exc:
            self._gl_failed = True
            self._mesh_ready = False
            self._apply_mode()
            self._gl_status.configure(text=last_gl_error() or str(exc))
            return
        if raw is None:
            return
        rw, rh = self._renderer.framebuffer_size
        if rw < 8 or rh < 8:
            rw, rh = render_target_size(w, h, self._interactive, block_count=self._renderer.block_count)
        image = Image.frombytes("RGB", (rw, rh), raw)
        if (rw, rh) != (w, h):
            image = image.resize((w, h), Image.Resampling.BILINEAR)
        if self._photo is not None and self._photo_size == image.size:
            self._photo.paste(image)
        else:
            self._photo = ImageTk.PhotoImage(image)
            self._photo_size = image.size
            if self._canvas_image_id is None:
                self._canvas_image_id = self._gl_canvas.create_image(0, 0, image=self._photo, anchor="nw")
            else:
                self._gl_canvas.itemconfig(self._canvas_image_id, image=self._photo)

    def _on_drag_start(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y
        self._drag_origin = (event.x, event.y)
        self._drag_moved = False
        try:
            self._gl_canvas.focus_set()
        except Exception:
            pass

    def _on_orbit(self, event) -> None:
        if self._renderer is None:
            return
        if abs(event.x - self._drag_origin[0]) + abs(event.y - self._drag_origin[1]) > 5:
            self._drag_moved = True
        dx = (event.x - self._drag_x) * 0.01
        dy = (event.y - self._drag_y) * 0.01
        self._drag_x = event.x
        self._drag_y = event.y
        self._renderer.camera.orbit(dx, dy)
        self._renderer.camera_user_moved = True
        self._schedule_redraw(interactive=True)

    def _on_pan(self, event) -> None:
        if self._renderer is None:
            return
        self._drag_moved = True
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        self._drag_x = event.x
        self._drag_y = event.y
        self._renderer.camera.pan(dx, dy)
        self._renderer.camera_user_moved = True
        self._schedule_redraw(interactive=True)

    def _on_drag_end(self, event, pick: bool = False) -> None:
        if pick and not self._drag_moved and self._mesh_ready and self._renderer is not None:
            self._pick_at(event.x, event.y)
        self._schedule_redraw(interactive=False)

    def _pick_at(self, x: float, y: float) -> None:
        if self._renderer is None:
            return
        w = max(self._gl_canvas.winfo_width(), 64)
        h = max(self._gl_canvas.winfo_height(), 64)
        hit = self._renderer.pick(x, y, w, h)
        if hit is None:
            self._renderer.select(None)
            self._clear_selection()
            self._apply_dissect_chrome()
        else:
            same = self._selected_rec is not None and hit.instance_id == self._selected_rec.instance_id
            if same:
                self._isolated = not self._isolated
            else:
                self._isolated = False
            self._renderer.select(hit.instance_id)
            self._selected_rec = hit
            self._selected_label = selection_caption(hit)
            self._apply_dissect_chrome()
        self._refresh_status()

    def _on_gl_enter(self, _event=None) -> None:
        self._grab_wheel()

    def _on_gl_leave(self, _event=None) -> None:
        self.after(1, self._maybe_release_wheel)

    def _grab_wheel(self) -> None:
        """Focus the Tk canvas so wheel zooms. Never call CTk bind_all."""
        if self._wheel_grabbed:
            return
        try:
            self._gl_canvas.focus_set()
            self._wheel_grabbed = True
        except Exception as exc:
            if not self._wheel_grab_warned:
                self._wheel_grab_warned = True
                print(f"3D preview wheel focus failed: {exc}")

    def _maybe_release_wheel(self) -> None:
        if self._pointer_over_preview():
            return
        self._wheel_grabbed = False

    def _pointer_over_preview(self) -> bool:
        try:
            widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        except Exception:
            return False
        return self._is_under(widget, self._gl_frame)

    def _is_under(self, widget, ancestor) -> bool:
        current = widget
        while current is not None:
            if current is ancestor or current is self._gl_canvas:
                return True
            try:
                current = current.master
            except Exception:
                return False
        return False

    def _bind_slider_wheel_passthrough(self) -> None:
        """Wheel over inspect/dissect sliders zooms the camera — never nudges layers."""
        for slider in (self._layer_slider, self._dissect_slider):
            self._bind_widget_tree_wheel(slider)

    def _bind_widget_tree_wheel(self, widget) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                widget.bind(sequence, self._on_wheel, add="+")
            except Exception:
                pass
        try:
            children = widget.winfo_children()
        except Exception:
            return
        for child in children:
            self._bind_widget_tree_wheel(child)

    def _on_wheel_global(self, event) -> Optional[str]:
        if self._mode != "3d":
            return None
        if not self._pointer_over_preview():
            return None
        self._apply_wheel_zoom(event)
        return "break"

    def _on_wheel(self, event) -> Optional[str]:
        self._apply_wheel_zoom(event)
        return "break"

    def _apply_wheel_zoom(self, event) -> None:
        """Unmodified wheel always zooms. Inspect/dissect stay on sliders and [ ]."""
        inward = wheel_zoom_inward(
            getattr(event, "delta", None),
            getattr(event, "num", None),
        )
        if inward is None:
            return
        if self._renderer is None:
            return
        factor = zoom_factor_for_distance(self._renderer.camera.distance, inward)
        try:
            x = self._gl_canvas.winfo_pointerx() - self._gl_canvas.winfo_rootx()
            y = self._gl_canvas.winfo_pointery() - self._gl_canvas.winfo_rooty()
        except Exception:
            x = getattr(event, "x", 0)
            y = getattr(event, "y", 0)
        w = max(self._gl_canvas.winfo_width(), 1)
        h = max(self._gl_canvas.winfo_height(), 1)
        if 0 <= x <= w and 0 <= y <= h:
            self._zoom_to_cursor(factor, x, y)
        else:
            self._zoom(factor)

    def _zoom(self, factor: float) -> None:
        if self._renderer is None:
            return
        point = None
        if self._selected_rec is not None:
            point = self._selected_rec.center
        self._renderer.camera.zoom_toward(factor, point)
        self._renderer.camera_user_moved = True
        self._schedule_redraw(interactive=True)
        self._arm_idle_redraw()

    def _zoom_to_cursor(self, factor: float, x: float, y: float) -> None:
        if self._renderer is None:
            return
        point = self._selected_rec.center if self._selected_rec is not None else self._point_under_cursor(x, y)
        self._renderer.camera.zoom_toward(factor, point)
        self._renderer.camera_user_moved = True
        self._schedule_redraw(interactive=True)
        self._arm_idle_redraw()

    def _point_under_cursor(self, x: float, y: float):
        renderer = self._renderer
        if renderer is None:
            return None
        w = max(self._gl_canvas.winfo_width(), 64)
        h = max(self._gl_canvas.winfo_height(), 64)
        from se_render.camera import perspective
        aspect = max(w, 1) / max(h, 1)
        near, far = renderer._clip_planes()
        proj = perspective(50.0, aspect, near, far, flip_y=True)
        origin, direction = renderer.camera.screen_ray(x, y, w, h, proj)
        # Intersect the view ray with the plane through the current pivot.
        target = renderer.camera.target
        denom = direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2
        if denom < 1e-8:
            return tuple(target)
        # Plane facing the camera through target.
        eye = renderer.camera.eye()
        normal = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
        nd = normal[0] * direction[0] + normal[1] * direction[1] + normal[2] * direction[2]
        if abs(nd) < 1e-8:
            return tuple(target)
        t = (
            normal[0] * (target[0] - origin[0])
            + normal[1] * (target[1] - origin[1])
            + normal[2] * (target[2] - origin[2])
        ) / nd
        return (
            origin[0] + direction[0] * t,
            origin[1] + direction[1] * t,
            origin[2] + direction[2] * t,
        )

    def set_blueprint_source(self, path) -> None:
        try:
            self._source_path = resolve_blueprint_dir(Path(path)) if path else None
        except Exception:
            self._source_path = Path(path) if path else None
        self._edits.source_path = self._source_path

    def _toast(self, message: str, level: str = "info") -> None:
        if self._on_toast:
            self._on_toast(message, level)

    def _category_mask(self) -> int:
        mask = 0
        for i, name in enumerate(INSPECT_CATEGORIES):
            if name in self._hidden_categories:
                mask |= 1 << i
        return mask

    def _sync_user_hidden(self) -> None:
        if self._renderer is None:
            return
        hidden_ids = set()
        if self._scene is not None:
            for i, block in enumerate(self._scene.blocks):
                ident = pick_identity(block)
                if self._edits.is_inspect_hidden(ident):
                    hidden_ids.add(i)
        self._renderer.hidden_subtypes = set(getattr(self._renderer, "hidden_subtypes", set()))
        self._renderer.isolate_grid_instances(
            self._grid_entity_id,
            self._grid_filter,
            extra_hidden=hidden_ids,
        )

    def _on_layer_slider(self, value) -> None:
        self._set_hide_layers(int(round(float(value))))

    def _set_hide_layers(self, layers: int) -> None:
        self._hide_layers = max(0, min(8, int(layers)))
        try:
            self._layer_slider.set(self._hide_layers)
            self._layer_label.configure(text=str(self._hide_layers))
        except Exception:
            pass
        if self._renderer is not None:
            self._renderer.hide_layers = self._hide_layers
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _nudge_layers(self, delta: int) -> None:
        self._set_hide_layers(self._hide_layers + delta)

    def _on_bracket_left(self, event) -> None:
        if int(getattr(event, "state", 0)) & 0x20000:
            self._nudge_layers(-1)
            return
        self._nudge_explode(-0.08)

    def _on_bracket_right(self, event) -> None:
        if int(getattr(event, "state", 0)) & 0x20000:
            self._nudge_layers(1)
            return
        self._nudge_explode(0.08)

    def _toggle_category(self, key: str) -> None:
        if key in self._hidden_categories:
            self._hidden_categories.discard(key)
        else:
            self._hidden_categories.add(key)
        btn = self._cat_buttons.get(key)
        on = key in self._hidden_categories
        if btn is not None:
            btn.configure(
                fg_color=TacticalTheme.CYAN_PRIMARY if on else TacticalTheme.BG_DARK,
                text_color=TacticalTheme.BG_DARK if on else TacticalTheme.TEXT_WHITE,
            )
        if self._renderer is not None:
            self._renderer.category_mask = self._category_mask()
        self._schedule_redraw(interactive=False)

    def _reset_visibility(self) -> None:
        self._hide_layers = 0
        self._hidden_categories.clear()
        self._hide_armor = False
        self._isolated = False
        if self._renderer is not None:
            self._renderer.hidden_subtypes = set()
            self._renderer.hide_armor = False
            self._renderer.isolate_id = -1.0
            self._sync_user_hidden()
        try:
            self._layer_slider.set(0)
            self._layer_label.configure(text="0")
        except Exception:
            pass
        for key, btn in self._cat_buttons.items():
            btn.configure(fg_color=TacticalTheme.BG_DARK, text_color=TacticalTheme.TEXT_WHITE)
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _hide_selected_type(self) -> None:
        if self._selected_rec is None or self._renderer is None:
            return
        self._renderer.hidden_subtypes.add(self._selected_rec.subtype)
        self._sync_user_hidden()
        self._schedule_redraw(interactive=False)

    def _hide_selected(self) -> None:
        rec = self._selected_rec
        if rec is None:
            return
        self._edits.hide(pick_identity(rec))
        self._sync_user_hidden()
        self._schedule_redraw(interactive=False)

    def _delete_selected(self) -> None:
        rec = self._selected_rec
        if rec is None:
            return
        self._edits.delete(pick_identity(rec))
        self._sync_user_hidden()
        self._clear_selection()
        if self._renderer is not None:
            self._renderer.select(None)
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _nudge_selected(self, delta) -> None:
        rec = self._selected_rec
        if rec is None or self._scene is None:
            return
        ident = pick_identity(rec)
        if self._edits.is_removed(ident):
            return
        idx = rec.instance_id
        if idx < 0 or idx >= len(self._scene.blocks):
            return
        block = self._scene.blocks[idx]
        new_min = self._edits.move(ident, block.local_min, delta)
        # Session move is absolute; align the instance to that Min.
        step = (
            new_min[0] - block.local_min[0],
            new_min[1] - block.local_min[1],
            new_min[2] - block.local_min[2],
        )
        if step != (0, 0, 0):
            nudge_block_instance(block, step)
        self._rebuild_after_edit(keep_id=ident)

    def _undo_edit(self) -> None:
        if not self._edits.undo():
            return
        self._rebuild_after_edit()

    def _rebuild_after_edit(self, keep_id=None) -> None:
        if self._scene is None or not self._install_valid:
            self._sync_user_hidden()
            self._schedule_redraw(interactive=False)
            return
        gen = self._job.begin()
        scene = self._scene
        catalog = self._catalog

        def task() -> None:
            try:
                cpu = build_preview_cpu(
                    scene, catalog, self._meshes, generation=gen, stage=STAGE_FULL, cancel=self._job
                )
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._on_edit_rebuild_failed(message))
                return
            self.after(0, lambda: self._on_edit_rebuild(gen, cpu, keep_id))

        threading.Thread(target=task, daemon=True).start()

    def _on_edit_rebuild_failed(self, message: str) -> None:
        self._toast(f"3D rebuild failed: {message}", "warning")
        self._sync_user_hidden()

    def _on_edit_rebuild(self, generation: int, cpu: PreviewCpuScene, keep_id) -> None:
        if not self._job.is_current(generation) or self._renderer is None:
            return
        try:
            self._renderer.upload_cpu_scene(cpu, grid_filter=self._grid_filter, refit=False)
        except Exception as exc:
            self._toast(f"3D rebuild failed: {exc}", "warning")
            return
        self._cpu_scene = cpu
        self._sync_user_hidden()
        if keep_id is not None:
            for rec in cpu.picks:
                if pick_identity(rec) == keep_id:
                    self._selected_rec = rec
                    self._selected_label = selection_caption(rec)
                    self._renderer.select(rec.instance_id)
                    break
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _focus_selection(self) -> None:
        if self._renderer is None:
            return
        if self._selected_rec is None:
            self._renderer.refit_to_visible()
        else:
            self._renderer.frame_selection(self._selected_rec)
        self._schedule_redraw(interactive=False)

    def _clear_and_fit(self) -> None:
        self._clear_selection()
        if self._renderer is not None:
            self._renderer.select(None)
            self._renderer.refit_to_visible()
        self._apply_dissect_chrome()
        self._refresh_status()
        self._schedule_redraw(interactive=False)

    def _on_double_click(self, event) -> None:
        if not self._mesh_ready:
            return
        self._pick_at(event.x, event.y)
        self._focus_selection()

    def _save_as_new(self) -> None:
        if self._source_path is None:
            self._toast("Load a blueprint folder before saving.", "warning")
            return
        try:
            source = resolve_blueprint_dir(self._source_path)
        except Exception as exc:
            self._toast(str(exc), "error")
            return
        dest = unique_edited_dir(source)
        overwrite = False
        if dest.exists():
            self._toast("Could not pick a free Save As folder.", "error")
            return
        deleted = set(self._edits.deleted)
        moves = dict(self._edits.moves)
        self._save_generation += 1
        generation = self._save_generation

        def task() -> None:
            try:
                written = save_blueprint_as(
                    source,
                    deleted,
                    moves,
                    dest_dir=dest,
                    overwrite_original=overwrite,
                )
            except FileExistsError:
                self.after(0, lambda: self._on_save_as_done(generation, None, "exists"))
                return
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda msg=message: self._on_save_as_done(generation, None, msg))
                return
            self.after(0, lambda: self._on_save_as_done(generation, written, None))

        threading.Thread(target=task, daemon=True).start()
        self._toast("Saving edited blueprint…", "info")

    def _on_save_as_done(self, generation: int, written, error: Optional[str]) -> None:
        if generation != self._save_generation:
            return
        if error == "exists":
            self._toast("Save As cancelled — destination already exists.", "warning")
        elif error:
            self._toast(f"Save failed: {error}", "error")
        elif written is not None:
            self._toast(f"Saved new blueprint: {written}", "success")

    def gl_failed_message(self) -> str:
        return last_gl_error() or "OpenGL preview is unavailable on this machine."

    def destroy(self):
        self._job.cancel()
        self._wheel_grabbed = False
        super().destroy()
