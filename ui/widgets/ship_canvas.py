"""Interactive 2D ship map — renders blueprint blocks as a grid without freezing the UI."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    """Top / side / front map of CubeGrid voxels."""

    PROJECTIONS = ("Top", "Side", "Front")

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=TacticalTheme.BG_DARK, corner_radius=8, **kwargs)
        self.blocks: List[VoxelBlock] = []
        self.selected_grid_filter: Optional[str] = None
        self.projection_mode = "Top"
        self.min_coords = (0, 0, 0)
        self.max_coords = (0, 0, 0)
        self.scale = 16.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._redraw_job = None
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, height=40, corner_radius=8)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            toolbar, text="View",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(10, 6))

        self.view_var = ctk.StringVar(value="Top")
        ctk.CTkOptionMenu(
            toolbar,
            values=list(self.PROJECTIONS),
            variable=self.view_var,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_MEDIUM,
            text_color=TacticalTheme.TEXT_WHITE,
            width=110,
            height=30,
            command=self._on_projection_changed,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            toolbar, text="Fit", width=70, height=30,
            font=TacticalTheme.FONT_SMALL,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            command=self.fit_to_view,
        ).pack(side="right", padx=8)
        ctk.CTkButton(
            toolbar, text="+", width=36, height=30,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=lambda: self._zoom(1.25),
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            toolbar, text="−", width=36, height=30,
            font=TacticalTheme.FONT_LARGE,
            fg_color=TacticalTheme.BG_DARK,
            text_color=TacticalTheme.TEXT_WHITE,
            command=lambda: self._zoom(0.8),
        ).pack(side="right", padx=2)

        canvas_container = ctk.CTkFrame(self, fg_color="#080e1a", corner_radius=8)
        canvas_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.canvas = tk.Canvas(canvas_container, bg="#070c18", highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_drag)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", lambda _e: self._zoom(1.15))
        self.canvas.bind("<Button-5>", lambda _e: self._zoom(0.85))
        self.canvas.bind("<Configure>", self._on_configure)

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=10, pady=(0, 8))
        for text, color in (
            ("Armor", TacticalTheme.COLOR_ARMOR),
            ("Cockpit", TacticalTheme.COLOR_COCKPIT),
            ("Thrusters", TacticalTheme.COLOR_PROPULSION),
            ("Weapons", TacticalTheme.COLOR_WEAPONS),
            ("Power", TacticalTheme.COLOR_POWER),
            ("Subgrids", TacticalTheme.COLOR_SUBGRID),
        ):
            ctk.CTkLabel(legend, text="■", font=TacticalTheme.FONT_NORMAL, text_color=color, width=16).pack(side="left")
            ctk.CTkLabel(legend, text=text, font=TacticalTheme.FONT_SMALL, text_color=TacticalTheme.TEXT_GRAY).pack(
                side="left", padx=(0, 10)
            )
        self.info_status = ctk.CTkLabel(
            legend, text="No ship loaded",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.CYAN_PRIMARY,
        )
        self.info_status.pack(side="right")

    def load_structure_data(self, blocks: List[VoxelBlock]) -> None:
        self.blocks = list(blocks)
        if not self.blocks:
            self.min_coords = (0, 0, 0)
            self.max_coords = (0, 0, 0)
            self.info_status.configure(text="No blocks to draw")
            self._schedule_redraw()
            return
        xs = [b.x for b in self.blocks]
        ys = [b.y for b in self.blocks]
        zs = [b.z for b in self.blocks]
        self.min_coords = (min(xs), min(ys), min(zs))
        self.max_coords = (max(xs), max(ys), max(zs))
        dim = (
            self.max_coords[0] - self.min_coords[0] + 1,
            self.max_coords[1] - self.min_coords[1] + 1,
            self.max_coords[2] - self.min_coords[2] + 1,
        )
        self.info_status.configure(
            text=f"{len(self.blocks):,} blocks  ·  {dim[0]} × {dim[1]} × {dim[2]}"
        )
        self.fit_to_view()

    def filter_by_grid(self, grid_name: Optional[str]) -> None:
        self.selected_grid_filter = grid_name
        self._schedule_redraw()

    def clear(self) -> None:
        self.blocks = []
        self.selected_grid_filter = None
        self.info_status.configure(text="No ship loaded")
        self._schedule_redraw()

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
        if any(k in s for k in ("reactor", "battery", "generator", "solar", "jumpdrive", "hydrogenengine")):
            return TacticalTheme.COLOR_POWER, "#a16207"
        if "heavy" in s:
            return "#1e293b", TacticalTheme.ORANGE_PRIMARY
        if "armor" in s or "panel" in s:
            return TacticalTheme.COLOR_ARMOR, TacticalTheme.CYAN_DIM
        return "#334155", "#475569"

    def _on_configure(self, _event=None) -> None:
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(40, self.redraw)

    def redraw(self) -> None:
        self._redraw_job = None
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return
        if not self.blocks:
            self.canvas.create_text(
                w // 2,
                h // 2,
                text="Select a blueprint to see its grids on this map.",
                font=TacticalTheme.FONT_LARGE,
                fill=TacticalTheme.TEXT_MUTED,
                justify="center",
            )
            return

        cx = w / 2 + self.pan_x
        cy = h / 2 + self.pan_y
        active = self.blocks
        if self.selected_grid_filter:
            active = [b for b in active if b.grid_name == self.selected_grid_filter]
        if not active:
            self.canvas.create_text(
                w // 2, h // 2,
                text="No blocks on this grid.",
                font=TacticalTheme.FONT_LARGE,
                fill=TacticalTheme.TEXT_MUTED,
            )
            return

        mid_x = (self.min_coords[0] + self.max_coords[0]) / 2.0
        mid_y = (self.min_coords[1] + self.max_coords[1]) / 2.0
        mid_z = (self.min_coords[2] + self.max_coords[2]) / 2.0
        step = max(4.0, self.scale)
        cells: Dict[Tuple[int, int], Tuple[str, str]] = {}
        for b in active:
            fill, outline = self._get_block_color(b.subtype, b.is_subgrid)
            if self.projection_mode == "Top":
                key = (b.x, b.z)
            elif self.projection_mode == "Side":
                key = (b.x, -b.y)
            else:
                key = (b.z, -b.y)
            cells[key] = (fill, outline)

        for (gx, gy), (fill, outline) in cells.items():
            if self.projection_mode == "Top":
                px = cx + (gx - mid_x) * step
                py = cy + (gy - mid_z) * step
            elif self.projection_mode == "Side":
                px = cx + (gx - mid_x) * step
                py = cy - ((-gy) - mid_y) * step
            else:
                px = cx + (gx - mid_z) * step
                py = cy - ((-gy) - mid_y) * step
            self.canvas.create_rectangle(
                px, py, px + step - 1, py + step - 1,
                fill=fill,
                outline=outline if step >= 8 else "",
                width=1,
            )

    def fit_to_view(self) -> None:
        w = max(self.canvas.winfo_width(), 320)
        h = max(self.canvas.winfo_height(), 240)
        if not self.blocks:
            self.scale = 16.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self._schedule_redraw()
            return
        dim_x = max(1, self.max_coords[0] - self.min_coords[0] + 1)
        dim_y = max(1, self.max_coords[1] - self.min_coords[1] + 1)
        dim_z = max(1, self.max_coords[2] - self.min_coords[2] + 1)
        if self.projection_mode == "Top":
            span_w, span_h = dim_x, dim_z
        elif self.projection_mode == "Side":
            span_w, span_h = dim_x, dim_y
        else:
            span_w, span_h = dim_z, dim_y
        self.scale = max(6.0, min(40.0, min((w * 0.8) / span_w, (h * 0.8) / span_h)))
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._schedule_redraw()

    def _zoom(self, factor: float) -> None:
        self.scale = max(4.0, min(48.0, self.scale * factor))
        self._schedule_redraw()

    def _on_mouse_wheel(self, event) -> None:
        self._zoom(1.15 if event.delta > 0 else 0.85)

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
        self.canvas.move("all", dx, dy)

    def _on_projection_changed(self, choice: str) -> None:
        self.projection_mode = choice
        self.fit_to_view()
