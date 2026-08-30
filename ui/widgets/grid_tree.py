"""Clickable CubeGrid hierarchy of the main hull and attached subgrids."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from subgrid_engine.hierarchy_parser import MultiGridStructure, SubgridNode
from ui.theme import TacticalTheme


class GridHierarchyView(ctk.CTkFrame):
    """Left-hand tree of main grid and mechanically attached subgrids."""

    def __init__(self, master, on_select: Optional[Callable[[Optional[str]], None]] = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_select = on_select
        self._hit_rows = []
        self._structure = None
        self._selected_grid: Optional[str] = None
        self._last_width = 0
        self.canvas = tk.Canvas(
            self,
            bg=TacticalTheme.BG_DARK,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Map>", lambda _e: self._paint_tree())

    def render(self, structure: Optional[MultiGridStructure]) -> None:
        self._structure = structure
        self._selected_grid = None
        self._paint_tree()

    def set_selected(self, grid_name: Optional[str]) -> None:
        if grid_name == self._selected_grid:
            return
        self._selected_grid = grid_name
        self._paint_tree()

    def _on_configure(self, event) -> None:
        if event.width <= 20:
            return
        if abs(event.width - self._last_width) < 8:
            self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
            return
        self._last_width = event.width
        self._paint_tree()

    def _paint_tree(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self._hit_rows = []
        width = max(self.canvas.winfo_width(), 240)
        structure = self._structure

        if structure is None or structure.total_grids == 0:
            self.canvas.create_text(
                12,
                24,
                text="Select a blueprint to list its CubeGrids,\nrotors, hinges, and pistons.",
                font=TacticalTheme.FONT_NORMAL,
                fill=TacticalTheme.TEXT_GRAY,
                anchor="nw",
                width=width - 24,
            )
            return

        y = 10
        y = self._draw_row(
            y,
            width,
            indent=0,
            title=f"All grids  ·  {structure.total_grids}",
            subtitle=f"{structure.total_blocks:,} blocks",
            grid_name=None,
            accent=TacticalTheme.CYAN_PRIMARY,
            selected=self._selected_grid is None,
        )
        y += 8

        if structure.root_node:
            y = self._draw_node(structure.root_node, depth=0, y=y, width=width)
        for orphan in structure.orphaned_grids:
            y = self._draw_node(orphan, depth=0, y=y, width=width)

        self.canvas.configure(scrollregion=(0, 0, width, y + 16))

    def _draw_node(self, node: SubgridNode, depth: int, y: int, width: int) -> int:
        connector = "Main" if depth == 0 and node.is_main_grid else "↳"
        title = f"{connector}  {node.grid_name}"
        extra = f" via {node.attachment_via}" if node.attachment_via else ""
        subtitle = f"{node.grid_size} grid  ·  {node.block_count:,} blocks{extra}"
        accent = TacticalTheme.ORANGE_PRIMARY if depth == 0 else TacticalTheme.COLOR_SUBGRID
        y = self._draw_row(
            y,
            width,
            indent=depth,
            title=title,
            subtitle=subtitle,
            grid_name=node.grid_name,
            accent=accent,
            selected=self._selected_grid == node.grid_name,
        )
        for child in node.children:
            y = self._draw_node(child, depth + 1, y, width)
        return y

    def _draw_row(
        self,
        y: int,
        width: int,
        indent: int,
        title: str,
        subtitle: str,
        grid_name: Optional[str],
        accent: str,
        selected: bool = False,
    ) -> int:
        x = 10 + indent * 18
        height = 58
        box_color = "#132033" if selected else TacticalTheme.BG_DARK
        self.canvas.create_rectangle(
            6,
            y,
            width - 6,
            y + height,
            fill=box_color,
            outline=accent if selected else TacticalTheme.BORDER_SUBTLE,
            width=1,
        )
        self.canvas.create_rectangle(6, y, 12, y + height, fill=accent, outline="")
        self.canvas.create_text(
            x + 10,
            y + 12,
            text=title,
            font=TacticalTheme.FONT_NORMAL,
            fill=TacticalTheme.TEXT_WHITE,
            anchor="nw",
            width=width - x - 24,
        )
        self.canvas.create_text(
            x + 10,
            y + 34,
            text=subtitle,
            font=TacticalTheme.FONT_SMALL,
            fill=TacticalTheme.TEXT_GRAY,
            anchor="nw",
            width=width - x - 24,
        )
        self._hit_rows.append((y, y + height, grid_name))
        return y + height + 6

    def _on_click(self, event) -> None:
        y = self.canvas.canvasy(event.y)
        for top, bottom, grid_name in self._hit_rows:
            if top <= y <= bottom:
                self.set_selected(grid_name)
                if self._on_select:
                    self._on_select(grid_name)
                return
