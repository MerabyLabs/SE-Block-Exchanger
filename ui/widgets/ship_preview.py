"""Subgrids right pane: 3D ModernGL preview when possible, else the 2D map."""

from __future__ import annotations

from typing import Callable, List, Optional
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.gl_backend import last_gl_error
from se_render.scene_graph import PreviewScene
from se_render.viewport import GLPreviewRenderer, scene_bounds_caption
from ui.theme import TacticalTheme
from ui.widgets.ship_canvas import ShipCanvas, VoxelBlock


class ShipPreviewHost(ctk.CTkFrame):
    """
    Hosts the 2D map always, and a 3D blit canvas when OpenGL and a valid
    Space Engineers install are available.
    """

    def __init__(
        self,
        master,
        on_locate: Optional[Callable[[], None]] = None,
        on_clear_install: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=TacticalTheme.BG_DARK, corner_radius=8, **kwargs)
        self._on_locate = on_locate
        self._on_clear_install = on_clear_install
        self._mode = "2d"
        self._scene: Optional[PreviewScene] = None
        self._catalog: Optional[CubeBlockCatalog] = None
        self._meshes = MeshLibrary()
        self._grid_filter: Optional[str] = None
        self._renderer: Optional[GLPreviewRenderer] = None
        self._photo = None
        self._redraw_job = None
        self._drag_x = 0
        self._drag_y = 0
        self._install_valid = False
        self._gl_failed = False

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
        self._gl_status = ctk.CTkLabel(
            toolbar,
            text="No ship loaded",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        self._gl_status.pack(side="left", padx=8)

        canvas_box = ctk.CTkFrame(self._gl_frame, fg_color="#080e1a", corner_radius=8)
        canvas_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._gl_canvas = tk.Canvas(canvas_box, bg="#070c18", highlightthickness=0, bd=0)
        self._gl_canvas.pack(fill="both", expand=True)
        self._gl_canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._gl_canvas.bind("<B1-Motion>", self._on_orbit)
        self._gl_canvas.bind("<ButtonPress-3>", self._on_drag_start)
        self._gl_canvas.bind("<B3-Motion>", self._on_pan)
        self._gl_canvas.bind("<MouseWheel>", self._on_wheel)
        self._gl_canvas.bind("<Button-4>", lambda _e: self._zoom(0.9))
        self._gl_canvas.bind("<Button-5>", lambda _e: self._zoom(1.1))
        self._gl_canvas.bind("<Configure>", lambda _e: self._schedule_redraw())

    def _emit_locate(self) -> None:
        if self._on_locate:
            self._on_locate()

    def set_install_state(self, valid: bool, path_text: str = "", message: str = "") -> None:
        self._install_valid = bool(valid)
        if valid:
            shown = path_text or "Space Engineers install"
            self._banner_label.configure(
                text=f"Using official models from {shown}",
                text_color=TacticalTheme.TEXT_CYAN,
            )
            self._locate_btn.configure(text="Change folder…")
        else:
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
        if self._scene is not None and self._mode == "3d":
            self._upload_scene()

    def load_structure_data(self, blocks: List[VoxelBlock], scene: Optional[PreviewScene] = None) -> None:
        self._scene = scene
        self._grid_filter = None
        self.ship_canvas.load_structure_data(blocks)
        self._apply_mode()
        if self._mode == "3d":
            self._upload_scene()

    def filter_by_grid(self, grid_name: Optional[str]) -> None:
        self._grid_filter = grid_name
        self.ship_canvas.filter_by_grid(grid_name)
        if self._mode == "3d":
            self._upload_scene()

    def clear(self) -> None:
        self._scene = None
        self._grid_filter = None
        self.ship_canvas.clear()
        self._gl_status.configure(text="No ship loaded")
        self._gl_canvas.delete("all")
        self._photo = None

    def refresh(self) -> None:
        if self._mode == "3d":
            self._schedule_redraw()
        else:
            self.ship_canvas.refresh()

    def fit_to_view(self) -> None:
        if self._mode == "3d" and self._renderer is not None:
            self._renderer.fit()
            self._schedule_redraw()
        else:
            self.ship_canvas.fit_to_view()

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
        want_3d = self._install_valid and not self._gl_failed
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
            if self._scene is not None:
                self._upload_scene()
        else:
            self._gl_frame.pack_forget()
            self.ship_canvas.pack(fill="both", expand=True)

    def _upload_scene(self) -> None:
        if self._scene is None or self._renderer is None or not self._renderer.available:
            return
        try:
            self._renderer.load(self._scene, self._catalog, self._meshes, self._grid_filter)
        except Exception as exc:
            self._gl_failed = True
            self._gl_status.configure(text=f"3D preview failed: {exc}")
            self._apply_mode()
            return
        self._gl_status.configure(text=scene_bounds_caption(self._scene, self._grid_filter))
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(30, self._blit)

    def _blit(self) -> None:
        self._redraw_job = None
        if self._mode != "3d" or self._renderer is None:
            return
        w = max(self._gl_canvas.winfo_width(), 64)
        h = max(self._gl_canvas.winfo_height(), 64)
        if w < 40 or h < 40:
            self.after(80, self._schedule_redraw)
            return
        try:
            raw = self._renderer.render(w, h)
        except Exception as exc:
            self._gl_failed = True
            self._apply_mode()
            self._gl_status.configure(text=last_gl_error() or str(exc))
            return
        if raw is None:
            return
        image = Image.frombytes("RGB", (max(64, int(w)), max(64, int(h))), raw)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        self._photo = ImageTk.PhotoImage(image)
        self._gl_canvas.delete("all")
        self._gl_canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _on_drag_start(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_orbit(self, event) -> None:
        if self._renderer is None:
            return
        dx = (event.x - self._drag_x) * 0.01
        dy = (event.y - self._drag_y) * 0.01
        self._drag_x = event.x
        self._drag_y = event.y
        self._renderer.camera.orbit(dx, dy)
        self._schedule_redraw()

    def _on_pan(self, event) -> None:
        if self._renderer is None:
            return
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        self._drag_x = event.x
        self._drag_y = event.y
        self._renderer.camera.pan(dx, dy)
        self._schedule_redraw()

    def _on_wheel(self, event) -> None:
        self._zoom(0.9 if event.delta > 0 else 1.1)

    def _zoom(self, factor: float) -> None:
        if self._renderer is None:
            return
        self._renderer.camera.zoom(factor)
        self._schedule_redraw()

    def gl_failed_message(self) -> str:
        return last_gl_error() or "OpenGL preview is unavailable on this machine."
