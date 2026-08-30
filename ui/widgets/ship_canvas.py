"""Interactive 2D ship map — renders blueprint blocks as a grid without freezing the UI."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from ui.theme import TacticalTheme


MAP_BG_RGB = (7, 12, 24)
MAP_GRID_RGB = (30, 41, 59)


def project_cell_key(block: "VoxelBlock", mode: str) -> Tuple[int, int]:
    if mode == "Top":
        return (int(block.x), int(block.z))
    if mode == "Side":
        return (int(block.x), -int(block.y))
    return (int(block.z), -int(block.y))


def collect_projected_cells(
    blocks: List["VoxelBlock"],
    mode: str,
) -> Dict[Tuple[int, int], Tuple[str, str]]:
    cells: Dict[Tuple[int, int], Tuple[str, str]] = {}
    for block in blocks:
        cells[project_cell_key(block, mode)] = ShipCanvas._get_block_color(
            block.subtype, block.is_subgrid, block.color_rgb
        )
    return cells


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    raw = (color or "").lstrip("#")
    if len(raw) != 6:
        return MAP_BG_RGB
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _clip_fill(
    arr: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: Tuple[int, int, int],
) -> None:
    h, w = arr.shape[0], arr.shape[1]
    xa, xb = max(0, min(x0, x1)), min(w, max(x0, x1) + 1)
    ya, yb = max(0, min(y0, y1)), min(h, max(y0, y1) + 1)
    if xa < xb and ya < yb:
        arr[ya:yb, xa:xb] = color


def rasterize_projected_cells(
    cells: Dict[Tuple[int, int], Tuple[str, str]],
    *,
    width: int,
    height: int,
    step: float,
    cx: float,
    cy: float,
    mid_x: float,
    mid_y: float,
    projection: str,
    draw_grid: bool,
) -> Image.Image:
    """One bitmap for the 2D map — same colors/legend as per-cell rectangles."""
    w = max(1, int(width))
    h = max(1, int(height))
    arr = np.empty((h, w, 3), dtype=np.uint8)
    arr[:] = MAP_BG_RGB
    if not cells:
        return Image.fromarray(arr, "RGB")
    cell = max(1.0, float(step))

    def project(gx: int, gy: int) -> Tuple[float, float]:
        if projection == "Top":
            return cx + (gx - mid_x) * cell, cy + (gy - mid_y) * cell
        if projection == "Side":
            return cx + (gx - mid_x) * cell, cy - ((-gy) - mid_y) * cell
        return cx + (gx - mid_x) * cell, cy - ((-gy) - mid_y) * cell

    xs = [key[0] for key in cells]
    ys = [key[1] for key in cells]
    min_gx, max_gx = min(xs), max(xs)
    min_gy, max_gy = min(ys), max(ys)
    if draw_grid and (max_gx - min_gx) <= 80 and (max_gy - min_gy) <= 80:
        for gx in range(min_gx, max_gx + 2):
            x0, y0 = project(gx, min_gy)
            _x1, y1 = project(gx, max_gy + 1)
            _clip_fill(arr, int(round(x0)), int(round(y0)), int(round(x0)), int(round(y1)), MAP_GRID_RGB)
        for gy in range(min_gy, max_gy + 2):
            x0, y0 = project(min_gx, gy)
            x1, _y1 = project(max_gx + 1, gy)
            _clip_fill(arr, int(round(x0)), int(round(y0)), int(round(x1)), int(round(y0)), MAP_GRID_RGB)

    inset = cell >= 8
    size = max(1, int(round(cell)))
    for (gx, gy), (fill, outline) in cells.items():
        px, py = project(gx, gy)
        x0 = int(round(px))
        y0 = int(round(py))
        x1 = x0 + size - 1
        y1 = y0 + size - 1
        _clip_fill(arr, x0, y0, x1, y1, _hex_to_rgb(fill))
        if inset and outline:
            rgb = _hex_to_rgb(outline)
            _clip_fill(arr, x0, y0, x1, y0, rgb)
            _clip_fill(arr, x0, y1, x1, y1, rgb)
            _clip_fill(arr, x0, y0, x0, y1, rgb)
            _clip_fill(arr, x1, y0, x1, y1, rgb)
    return Image.fromarray(arr, "RGB")


def voxels_to_blocks(voxels: Iterable[dict]) -> List["VoxelBlock"]:
    """Build 2D map cubes. Call only when the 2D map will actually draw."""
    return [
        VoxelBlock(
            x=int(v["x"]),
            y=int(v["y"]),
            z=int(v["z"]),
            subtype=v["subtype"],
            grid_name=v["grid_name"],
            grid_size=v.get("grid_size", "Large"),
            is_subgrid=bool(v.get("is_subgrid", False)),
            color_rgb=v.get("color_rgb"),
            grid_entity_id=str(v.get("grid_entity_id") or ""),
        )
        for v in voxels
    ]


@dataclass
class VoxelBlock:
    x: int
    y: int
    z: int
    subtype: str
    grid_name: str
    is_subgrid: bool
    grid_size: str = "Large"
    color_rgb: Optional[Tuple[float, float, float]] = None
    grid_entity_id: str = ""


class ShipCanvas(ctk.CTkFrame):
    """Top / side / front map of CubeGrid voxels."""

    PROJECTIONS = ("Top", "Side", "Front")
    _session_projection = "Top"

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=TacticalTheme.BG_DARK, corner_radius=8, **kwargs)
        self.blocks: List[VoxelBlock] = []
        self.selected_grid_filter: Optional[str] = None
        self.selected_grid_entity_id: Optional[str] = None
        self.projection_mode = str(self._session_projection or "Top")
        if self.projection_mode not in self.PROJECTIONS:
            self.projection_mode = "Top"
        self.min_coords = (0, 0, 0)
        self.max_coords = (0, 0, 0)
        self.scale = 16.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._redraw_job = None
        self._photo = None
        self._photo_size = (0, 0)
        self._map_image_id = None
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_GLASS, height=40, corner_radius=8)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            toolbar, text="View",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(10, 6))

        self.view_var = ctk.StringVar(value=self.projection_mode)
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
        self.canvas.bind("<Map>", self._on_mapped)

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

    def load_structure_data(self, blocks: List[VoxelBlock], *, draw: bool = True) -> None:
        self.blocks = list(blocks)
        self.selected_grid_filter = None
        self.selected_grid_entity_id = None
        if not self.blocks:
            self.min_coords = (0, 0, 0)
            self.max_coords = (0, 0, 0)
            self.info_status.configure(text="No blocks to draw")
            if draw:
                self._schedule_redraw()
            return
        self.min_coords, self.max_coords = self.bounds_for(self.blocks)
        self._update_status_caption(self.blocks)
        if draw:
            self.fit_to_view()

    def filter_by_grid(
        self,
        grid_name: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
    ) -> None:
        self.selected_grid_filter = grid_name
        self.selected_grid_entity_id = grid_entity_id
        visible = self._visible_blocks()
        self._update_status_caption(visible)
        if self.blocks:
            self.fit_to_view()
        else:
            self._schedule_redraw()

    def _visible_blocks(self) -> List[VoxelBlock]:
        if self.selected_grid_entity_id:
            return [b for b in self.blocks if b.grid_entity_id == self.selected_grid_entity_id]
        if not self.selected_grid_filter:
            return self.blocks
        return [b for b in self.blocks if b.grid_name == self.selected_grid_filter]

    @staticmethod
    def bounds_for(blocks: List[VoxelBlock]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        if not blocks:
            return (0, 0, 0), (0, 0, 0)
        xs = [b.x for b in blocks]
        ys = [b.y for b in blocks]
        zs = [b.z for b in blocks]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def _update_status_caption(self, blocks: List[VoxelBlock]) -> None:
        if not blocks:
            self.info_status.configure(
                text="No blocks on this grid." if self.selected_grid_filter else "No blocks to draw"
            )
            return
        min_c, max_c = self.bounds_for(blocks)
        dim = (
            max_c[0] - min_c[0] + 1,
            max_c[1] - min_c[1] + 1,
            max_c[2] - min_c[2] + 1,
        )
        prefix = f"{self.selected_grid_filter}  ·  " if self.selected_grid_filter else ""
        self.info_status.configure(
            text=f"{prefix}{len(blocks):,} blocks  ·  {dim[0]} × {dim[1]} × {dim[2]}"
        )

    def clear(self) -> None:
        self.blocks = []
        self.selected_grid_filter = None
        self.info_status.configure(text="No ship loaded")
        self._schedule_redraw()

    @staticmethod
    def _rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
        r = max(0, min(255, int(round(rgb[0] * 255))))
        g = max(0, min(255, int(round(rgb[1] * 255))))
        b = max(0, min(255, int(round(rgb[2] * 255))))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _get_block_color(
        subtype: str,
        is_subgrid: bool,
        color_rgb: Optional[Tuple[float, float, float]] = None,
    ) -> Tuple[str, str]:
        if color_rgb is not None:
            fill = ShipCanvas._rgb_to_hex(color_rgb)
            return fill, "#0f172a"
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

    def _on_mapped(self, _event=None) -> None:
        if self.blocks:
            self.fit_to_view()
        else:
            self._schedule_redraw()

    def refresh(self) -> None:
        """Redraw after the Map/Subgrids tab becomes visible."""
        if self.blocks:
            self.fit_to_view()
        else:
            self._schedule_redraw()

    def _is_drawn(self) -> bool:
        try:
            return bool(self.winfo_ismapped() and self.canvas.winfo_ismapped())
        except Exception:
            return False

    def _schedule_redraw(self) -> None:
        if not self._is_drawn():
            return
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(40, self.redraw)

    def redraw(self) -> None:
        self._redraw_job = None
        if not self._is_drawn():
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 40 or h < 40:
            if self.blocks:
                self.after(80, self.refresh)
            return
        if not self.blocks:
            self._clear_map_image()
            self.canvas.delete("all")
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
        active = self._visible_blocks()
        if not active:
            self._clear_map_image()
            self.canvas.delete("all")
            self.canvas.create_text(
                w // 2, h // 2,
                text="No blocks on this grid.",
                font=TacticalTheme.FONT_LARGE,
                fill=TacticalTheme.TEXT_MUTED,
            )
            return

        min_c, max_c = self.bounds_for(active)
        mid_x = (min_c[0] + max_c[0]) / 2.0
        mid_y = (min_c[1] + max_c[1]) / 2.0
        mid_z = (min_c[2] + max_c[2]) / 2.0
        step = max(4.0, self.scale)
        cells = collect_projected_cells(active, self.projection_mode)
        if self.projection_mode == "Top":
            axis_mid_x, axis_mid_y = mid_x, mid_z
        elif self.projection_mode == "Side":
            axis_mid_x, axis_mid_y = mid_x, mid_y
        else:
            axis_mid_x, axis_mid_y = mid_z, mid_y
        image = rasterize_projected_cells(
            cells,
            width=w,
            height=h,
            step=step,
            cx=cx,
            cy=cy,
            mid_x=axis_mid_x,
            mid_y=axis_mid_y,
            projection=self.projection_mode,
            draw_grid=True,
        )
        if self._photo is not None and self._photo_size == image.size:
            self._photo.paste(image)
        else:
            self._photo = ImageTk.PhotoImage(image)
            self._photo_size = image.size
            if self._map_image_id is None:
                self.canvas.delete("all")
                self._map_image_id = self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
            else:
                self.canvas.itemconfig(self._map_image_id, image=self._photo)
        if self._map_image_id is not None:
            self.canvas.coords(self._map_image_id, 0, 0)

    def fit_to_view(self) -> None:
        w = max(self.canvas.winfo_width(), 320)
        h = max(self.canvas.winfo_height(), 240)
        visible = self._visible_blocks()
        if not visible:
            self.scale = 16.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self._schedule_redraw()
            return
        min_c, max_c = self.bounds_for(visible)
        dim_x = max(1, max_c[0] - min_c[0] + 1)
        dim_y = max(1, max_c[1] - min_c[1] + 1)
        dim_z = max(1, max_c[2] - min_c[2] + 1)
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

    def _clear_map_image(self) -> None:
        self._photo = None
        self._photo_size = (0, 0)
        self._map_image_id = None

    def _on_pan_drag(self, event) -> None:
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self.pan_x += dx
        self.pan_y += dy
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._schedule_redraw()

    def _on_projection_changed(self, choice: str) -> None:
        self.projection_mode = choice
        ShipCanvas._session_projection = choice
        self.fit_to_view()
