"""
Interactive 2D / 2.5D Graphical Ship Blueprint Canvas.
Renders authentic 1:1 square voxel representations of Space Engineers grids and subgrids
with orthographic projection modes, deck slicer, subsystem color coding, and zoom/pan.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import List, Optional, Tuple
import customtkinter as ctk

from ui.theme import TacticalTheme


@dataclass
class VoxelBlock:
    x: int
    y: int
    z: int
    subtype: str
    grid_name: str
    is_subgrid: bool
    grid_size: str = "Large"


class ShipCanvas(ctk.CTkFrame):
    """
    Interactive 2D/2.5D graphical blueprint viewer.
    """

    PROJECTIONS = ("TOP (X-Z)", "SIDE (X-Y)", "FRONT (Y-Z)", "ISOMETRIC 2.5D")

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=TacticalTheme.BG_DARK, corner_radius=6, **kwargs)

        self.blocks: List[VoxelBlock] = []
        self.selected_grid_filter: Optional[str] = None
        self.projection_mode: str = "TOP (X-Z)"
        self.slice_axis: str = "Y"  # Default slice height for Top view
        self.slice_index: Optional[int] = None  # None = show all slices
        self.min_coords = (0, 0, 0)
        self.max_coords = (0, 0, 0)

        # Canvas pan/zoom transforms
        self.scale: float = 18.0  # Pixels per block voxel
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self._drag_start_x = 0
        self._drag_start_y = 0

        self._build_ui()

    def _build_ui(self) -> None:
        # Top toolbar
        toolbar = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, height=36, corner_radius=6)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        # View Mode Dropdown
        ctk.CTkLabel(
            toolbar,
            text="VIEW:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        ).pack(side="left", padx=(8, 4))

        self.view_var = ctk.StringVar(value="TOP (X-Z)")
        self.view_menu = ctk.CTkOptionMenu(
            toolbar,
            values=list(self.PROJECTIONS),
            variable=self.view_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_MEDIUM,
            button_hover_color=TacticalTheme.CYAN_DIM,
            text_color=TacticalTheme.TEXT_WHITE,
            width=140,
            height=28,
            command=self._on_projection_changed,
        )
        self.view_menu.pack(side="left", padx=4)

        # Deck Slicer Controls
        ctk.CTkLabel(
            toolbar,
            text="DECK SLICE:",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.ORANGE_PRIMARY,
        ).pack(side="left", padx=(12, 4))

        self.slice_toggle_var = ctk.BooleanVar(value=False)
        self.slice_chk = ctk.CTkCheckBox(
            toolbar,
            text="Enable",
            variable=self.slice_toggle_var,
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            hover_color=TacticalTheme.ORANGE_DIM,
            width=65,
            command=self._toggle_slice_mode,
        )
        self.slice_chk.pack(side="left", padx=2)

        self.slice_slider = ctk.CTkSlider(
            toolbar,
            from_=0,
            to=10,
            number_of_steps=10,
            width=120,
            height=16,
            progress_color=TacticalTheme.ORANGE_PRIMARY,
            button_color=TacticalTheme.ORANGE_PRIMARY,
            command=self._on_slice_slider_moved,
        )
        self.slice_slider.pack(side="left", padx=4)
        self.slice_slider.set(0)

        self.slice_label = ctk.CTkLabel(
            toolbar,
            text="ALL DECKS",
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
            width=90,
        )
        self.slice_label.pack(side="left", padx=2)

        # Zoom & Fit Controls
        btn_fit = ctk.CTkButton(
            toolbar,
            text="FIT VIEW",
            width=75,
            height=26,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_CYAN,
            hover_color=TacticalTheme.CYAN_DIM,
            command=self.fit_to_view,
        )
        btn_fit.pack(side="right", padx=6)

        btn_zoom_in = ctk.CTkButton(
            toolbar,
            text="+",
            width=30,
            height=26,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            hover_color=TacticalTheme.CYAN_DIM,
            command=lambda: self._zoom(1.25),
        )
        btn_zoom_in.pack(side="right", padx=2)

        btn_zoom_out = ctk.CTkButton(
            toolbar,
            text="-",
            width=30,
            height=26,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            hover_color=TacticalTheme.CYAN_DIM,
            command=lambda: self._zoom(0.8),
        )
        btn_zoom_out.pack(side="right", padx=2)

        # Canvas drawing surface
        canvas_container = ctk.CTkFrame(self, fg_color="#080e1a", corner_radius=6)
        canvas_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.canvas = tk.Canvas(
            canvas_container,
            bg="#070c18",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Canvas event bindings
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_drag)
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas.bind("<ButtonPress-3>", self._on_pan_start)
        self.canvas.bind("<B3-Motion>", self._on_pan_drag)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        # Legend Bar
        legend = ctk.CTkFrame(self, fg_color="transparent", height=24)
        legend.pack(fill="x", padx=10, pady=(0, 6))

        legend_items = [
            ("Hull / Armor", TacticalTheme.COLOR_ARMOR),
            ("Cockpit", TacticalTheme.COLOR_COCKPIT),
            ("Thrusters", TacticalTheme.COLOR_PROPULSION),
            ("Weapons", TacticalTheme.COLOR_WEAPONS),
            ("Power", TacticalTheme.COLOR_POWER),
            ("Subgrids", TacticalTheme.COLOR_SUBGRID),
            ("DLC Reskins", TacticalTheme.COLOR_DLC),
        ]

        for text, color in legend_items:
            dot = ctk.CTkLabel(
                legend,
                text="■",
                font=("Segoe UI", 12),
                text_color=color,
                width=14,
            )
            dot.pack(side="left", padx=(6, 2))
            ctk.CTkLabel(
                legend,
                text=text,
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.TEXT_GRAY,
            ).pack(side="left", padx=(0, 8))

        self.info_status = ctk.CTkLabel(
            legend,
            text="0 Voxels Loaded",
            font=TacticalTheme.FONT_CODE_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        self.info_status.pack(side="right", padx=8)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------

    def load_structure_data(self, blocks: List[VoxelBlock]) -> None:
        """Load block voxels and recalculate 3D bounding geometry."""
        self.blocks = list(blocks)
        if not self.blocks:
            self.min_coords = (0, 0, 0)
            self.max_coords = (0, 0, 0)
            self.info_status.configure(text="0 Voxels Loaded")
            self.redraw()
            return

        xs = [b.x for b in self.blocks]
        ys = [b.y for b in self.blocks]
        zs = [b.z for b in self.blocks]

        self.min_coords = (min(xs), min(ys), min(zs))
        self.max_coords = (max(xs), max(ys), max(zs))

        # Setup slice slider range
        self._update_slider_range()

        dim_x = self.max_coords[0] - self.min_coords[0] + 1
        dim_y = self.max_coords[1] - self.min_coords[1] + 1
        dim_z = self.max_coords[2] - self.min_coords[2] + 1
        self.info_status.configure(text=f"{len(self.blocks):,} Voxels | Grid: {dim_x}W x {dim_y}H x {dim_z}L")

        self.fit_to_view()

    def filter_by_grid(self, grid_name: Optional[str]) -> None:
        self.selected_grid_filter = grid_name
        self.redraw()

    # ------------------------------------------------------------------
    # Canvas Transforms & Rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _get_block_color(subtype: str, is_subgrid: bool) -> Tuple[str, str]:
        if is_subgrid:
            return TacticalTheme.COLOR_SUBGRID, "#047857"

        s = subtype.lower()
        if "cockpit" in s or "cryo" in s:
            return TacticalTheme.COLOR_COCKPIT, "#b45309"
        if "thrust" in s:
            return TacticalTheme.COLOR_PROPULSION, "#0e7490"
        if any(k in s for k in ("turret", "missile", "gatling", "cannon", "railgun", "warhead", "rocket")):
            return TacticalTheme.COLOR_WEAPONS, "#b91c1c"
        if any(k in s for k in ("reactor", "battery", "generator", "solar")):
            return TacticalTheme.COLOR_POWER, "#a16207"
        if any(k in s for k in ("industrial", "scifi", "contact", "signal", "warfare", "wasteland")):
            return TacticalTheme.COLOR_DLC, "#be185d"
        if "heavy" in s:
            return "#1e293b", TacticalTheme.ORANGE_PRIMARY
        if "armor" in s or "panel" in s:
            return TacticalTheme.COLOR_ARMOR, TacticalTheme.CYAN_DIM
        return "#334155", "#475569"

    def redraw(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()

        if w < 10 or h < 10 or not self.blocks:
            self.canvas.create_text(
                w // 2,
                h // 2,
                text="No blueprint voxel data loaded.\nSelect a blueprint in the database to inspect hull geometry.",
                font=TacticalTheme.FONT_NORMAL,
                fill=TacticalTheme.TEXT_MUTED,
                justify="center",
            )
            return

        # Draw subtle holographic background grid
        self._draw_holo_grid(w, h)

        # Center reference
        cx = w / 2 + self.pan_x
        cy = h / 2 + self.pan_y

        active_blocks = self.blocks
        if self.selected_grid_filter:
            active_blocks = [b for b in active_blocks if b.grid_name == self.selected_grid_filter]

        # Apply deck slicing
        if self.slice_toggle_var.get() and self.slice_index is not None:
            if self.projection_mode.startswith("TOP"):
                active_blocks = [b for b in active_blocks if b.y == self.slice_index]
            elif self.projection_mode.startswith("SIDE"):
                active_blocks = [b for b in active_blocks if b.z == self.slice_index]
            elif self.projection_mode.startswith("FRONT"):
                active_blocks = [b for b in active_blocks if b.x == self.slice_index]

        mid_x = (self.min_coords[0] + self.max_coords[0]) / 2.0
        mid_y = (self.min_coords[1] + self.max_coords[1]) / 2.0
        mid_z = (self.min_coords[2] + self.max_coords[2]) / 2.0

        # Sort blocks for clean painter's algorithm
        if self.projection_mode.startswith("ISOMETRIC"):
            active_blocks = sorted(active_blocks, key=lambda b: (b.x + b.z - b.y))
        elif self.projection_mode.startswith("TOP"):
            active_blocks = sorted(active_blocks, key=lambda b: b.y)
        elif self.projection_mode.startswith("SIDE"):
            active_blocks = sorted(active_blocks, key=lambda b: b.z)
        elif self.projection_mode.startswith("FRONT"):
            active_blocks = sorted(active_blocks, key=lambda b: b.x)

        step = self.scale

        for b in active_blocks:
            fill_color, outline_color = self._get_block_color(b.subtype, b.is_subgrid)

            if self.projection_mode.startswith("TOP"):
                # X-Z Plane (Ship looking down from top: X horizontal, Z vertical)
                px = cx + (b.x - mid_x) * step
                py = cy + (b.z - mid_z) * step
                self.canvas.create_rectangle(
                    px, py, px + step - 1, py + step - 1,
                    fill=fill_color,
                    outline=outline_color if step > 6 else "",
                    width=1,
                )

            elif self.projection_mode.startswith("SIDE"):
                # X-Y Plane (Ship profile: X horizontal, Y vertical inverted)
                px = cx + (b.x - mid_x) * step
                py = cy - (b.y - mid_y) * step
                self.canvas.create_rectangle(
                    px, py, px + step - 1, py + step - 1,
                    fill=fill_color,
                    outline=outline_color if step > 6 else "",
                    width=1,
                )

            elif self.projection_mode.startswith("FRONT"):
                # Y-Z Plane (Cross section: Z horizontal, Y vertical inverted)
                px = cx + (b.z - mid_z) * step
                py = cy - (b.y - mid_y) * step
                self.canvas.create_rectangle(
                    px, py, px + step - 1, py + step - 1,
                    fill=fill_color,
                    outline=outline_color if step > 6 else "",
                    width=1,
                )

            elif self.projection_mode.startswith("ISOMETRIC"):
                # 2.5D Isometric projection
                rel_x = b.x - mid_x
                rel_y = b.y - mid_y
                rel_z = b.z - mid_z

                iso_x = (rel_x - rel_z) * (step * 0.866)
                iso_y = (-rel_y * step * 0.9) + (rel_x + rel_z) * (step * 0.5)

                px = cx + iso_x
                py = cy + iso_y

                # Draw isometric cube diamond top
                h_step = step * 0.5
                points = [
                    px, py - h_step,
                    px + h_step, py,
                    px, py + h_step,
                    px - h_step, py,
                ]
                self.canvas.create_polygon(
                    points,
                    fill=fill_color,
                    outline=outline_color if step > 6 else "",
                    width=1,
                )

    def _draw_holo_grid(self, w: int, h: int) -> None:
        grid_size = 40
        for x in range(0, w, grid_size):
            self.canvas.create_line(x, 0, x, h, fill="#0d1829", width=1)
        for y in range(0, h, grid_size):
            self.canvas.create_line(0, y, w, y, fill="#0d1829", width=1)

    def fit_to_view(self) -> None:
        w = max(self.canvas.winfo_width(), 400)
        h = max(self.canvas.winfo_height(), 300)

        if not self.blocks:
            self.scale = 18.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.redraw()
            return

        dim_x = max(1, self.max_coords[0] - self.min_coords[0] + 1)
        dim_y = max(1, self.max_coords[1] - self.min_coords[1] + 1)
        dim_z = max(1, self.max_coords[2] - self.min_coords[2] + 1)

        if self.projection_mode.startswith("TOP"):
            max_span_w = dim_x
            max_span_h = dim_z
        elif self.projection_mode.startswith("SIDE"):
            max_span_w = dim_x
            max_span_h = dim_y
        elif self.projection_mode.startswith("FRONT"):
            max_span_w = dim_z
            max_span_h = dim_y
        else:
            max_span_w = dim_x + dim_z
            max_span_h = dim_y + (dim_x + dim_z) * 0.5

        scale_x = (w * 0.8) / max_span_w
        scale_y = (h * 0.8) / max_span_h
        self.scale = max(4.0, min(36.0, min(scale_x, scale_y)))
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw()

    # ------------------------------------------------------------------
    # Interactivity: Zoom, Pan, Slicing
    # ------------------------------------------------------------------

    def _zoom(self, factor: float) -> None:
        self.scale = max(2.0, min(64.0, self.scale * factor))
        self.redraw()

    def _on_mouse_wheel(self, event) -> None:
        factor = 1.15 if event.delta > 0 else 0.85
        self._zoom(factor)

    def _on_pan_start(self, event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_pan_drag(self, event) -> None:
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self.pan_x += dx
        self.pan_y += dy
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.redraw()

    def _on_projection_changed(self, choice: str) -> None:
        self.projection_mode = choice
        self._update_slider_range()
        self.fit_to_view()

    def _update_slider_range(self) -> None:
        if not self.blocks:
            return

        if self.projection_mode.startswith("TOP"):
            min_v, max_v = self.min_coords[1], self.max_coords[1]
            axis_name = "Deck Y"
        elif self.projection_mode.startswith("SIDE"):
            min_v, max_v = self.min_coords[2], self.max_coords[2]
            axis_name = "Slice Z"
        elif self.projection_mode.startswith("FRONT"):
            min_v, max_v = self.min_coords[0], self.max_coords[0]
            axis_name = "Cross X"
        else:
            min_v, max_v = 0, 10
            axis_name = "Isometric"

        steps = max(1, max_v - min_v)
        self.slice_slider.configure(from_=min_v, to=max_v, number_of_steps=steps)
        if self.slice_index is None or self.slice_index < min_v or self.slice_index > max_v:
            self.slice_index = min_v
            self.slice_slider.set(min_v)

        if self.slice_toggle_var.get():
            self.slice_label.configure(text=f"{axis_name} = {int(self.slice_slider.get())}")
        else:
            self.slice_label.configure(text="ALL DECKS")

    def _toggle_slice_mode(self) -> None:
        if self.slice_toggle_var.get():
            self.slice_index = int(self.slice_slider.get())
            self._update_slider_range()
        else:
            self.slice_index = None
            self.slice_label.configure(text="ALL DECKS")
        self.redraw()

    def _on_slice_slider_moved(self, value) -> None:
        if self.slice_toggle_var.get():
            self.slice_index = int(value)
            self._update_slider_range()
            self.redraw()
