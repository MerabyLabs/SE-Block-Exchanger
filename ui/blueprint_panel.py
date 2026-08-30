"""Left panel with searchable blueprint card list."""

import customtkinter as ctk
from typing import List, Optional, Callable, Sequence
from ui.theme import TacticalTheme
from ui.widgets.blueprint_card import BlueprintCard


def highlight_cards_by_visible_index(cards, selected_indices) -> None:
    """Highlight by each card's visible index, not its position in `_cards`."""
    selected = set(selected_indices)
    for card in cards:
        card.set_selected(getattr(card, "index", -1) in selected)


def blueprint_matches_search(bp, search: str) -> bool:
    query = (search or "").lower()
    if not query:
        return True
    return query in (bp.name or "").lower() or query in (bp.display_name or "").lower()


def search_pack_order(cards, blueprints, search: str) -> List:
    """Matching cards in original list order — pack() without before= scrambles this."""
    ordered = []
    for card, bp in zip(cards, blueprints):
        if blueprint_matches_search(bp, search):
            ordered.append(card)
    return ordered


def blueprint_for_card(blueprints: Sequence, card):
    """Resolve the ship from the card path, never from a remapped visible index."""
    path = getattr(getattr(card, "bp_info", None), "path", None)
    if path is not None:
        for bp in blueprints:
            if bp.path == path:
                return bp
    return getattr(card, "bp_info", None)


def visible_index_for_path(blueprints: Sequence, path) -> int:
    for index, bp in enumerate(blueprints):
        if bp.path == path:
            return index
    return -1


class BlueprintPanel(ctk.CTkFrame):
    """Left panel containing search bar and scrollable blueprint card list."""

    def __init__(
        self,
        master,
        on_select: Optional[Callable] = None,
        on_recent_select: Optional[Callable] = None,
        on_browse: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            **TacticalTheme.panel_kwargs(),
            **kwargs,
        )
        self._on_select = on_select
        self._on_recent_select = on_recent_select
        self._on_browse = on_browse
        self._cards: List[BlueprintCard] = []
        self._blueprints = []
        self._selected_indices: set = set()
        self._recent_lookup = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(14, 6))

        ctk.CTkLabel(
            header,
            text="Your blueprints",
            font=TacticalTheme.FONT_LARGE,
            text_color=TacticalTheme.TEXT_WHITE,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Select a ship to preview what will change",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(anchor="w", pady=(2, 0))

        recent_row = ctk.CTkFrame(self, fg_color="transparent")
        recent_row.pack(fill="x", padx=14, pady=(4, 6))

        ctk.CTkLabel(
            recent_row,
            text="Jump back",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        ).pack(side="left", padx=(0, 8))

        self.recent_var = ctk.StringVar(value="(none)")
        self.recent_menu = ctk.CTkOptionMenu(
            recent_row,
            values=["(none)"],
            variable=self.recent_var,
            width=230,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_GLASS,
            button_hover_color=TacticalTheme.CYAN_DIM,
            dropdown_fg_color=TacticalTheme.BG_MEDIUM,
            dropdown_hover_color=TacticalTheme.BG_GLASS,
            text_color=TacticalTheme.TEXT_WHITE,
            font=TacticalTheme.FONT_SMALL,
            command=self._on_recent_picked,
        )
        self.recent_menu.pack(side="left", fill="x", expand=True)

        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=14, pady=(0, 8))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())

        self._search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="Search by name",
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_WHITE,
            fg_color=TacticalTheme.BG_DARK,
            border_color=TacticalTheme.BORDER_SUBTLE,
            placeholder_text_color=TacticalTheme.TEXT_GRAY,
            height=34,
            corner_radius=8,
        )
        self._search_entry.pack(fill="x")

        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=TacticalTheme.BG_DARK,
            border_width=0,
            corner_radius=8,
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def set_blueprints(self, blueprints):
        """Populate the card list with blueprint data."""
        if (
            self._cards
            and len(self._cards) == len(blueprints)
            and all(self._cards[i].bp_info.path == blueprints[i].path for i in range(len(blueprints)))
        ):
            self._blueprints = blueprints
            for card, bp in zip(self._cards, blueprints):
                card.update_info(bp)
            return
        self._blueprints = blueprints
        self._selected_indices.clear()
        self._rebuild_cards(blueprints)

    def _rebuild_cards(self, blueprints):
        """Rebuild all card widgets."""
        for child in self._scroll_frame.winfo_children():
            child.destroy()
        self._cards.clear()

        if not blueprints:
            empty = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
            empty.pack(fill="x", padx=8, pady=28)
            ctk.CTkLabel(
                empty,
                text="No blueprints here",
                font=TacticalTheme.FONT_LARGE,
                text_color=TacticalTheme.TEXT_WHITE,
            ).pack(pady=(0, 6))
            ctk.CTkLabel(
                empty,
                text="Open your Space Engineers Blueprints folder\nto convert ships without touching XML.",
                font=TacticalTheme.FONT_SMALL,
                text_color=TacticalTheme.TEXT_GRAY,
                justify="center",
            ).pack(pady=(0, 12))
            if self._on_browse:
                ctk.CTkButton(
                    empty,
                    text="Open folder",
                    font=TacticalTheme.FONT_SMALL,
                    fg_color=TacticalTheme.CYAN_PRIMARY,
                    text_color=TacticalTheme.BG_DARK,
                    hover_color=TacticalTheme.CYAN_DIM,
                    width=140,
                    height=32,
                    corner_radius=8,
                    command=self._on_browse,
                ).pack()
            return

        for i, bp in enumerate(blueprints):
            card = BlueprintCard(
                self._scroll_frame, bp, i,
                on_select=self._handle_card_select,
            )
            card.pack(fill="x", padx=4, pady=3)
            self._cards.append(card)

    def _handle_card_select(self, card_or_index, multi: bool = False):
        """Handle card selection, supporting multi-select with Ctrl."""
        visible = self._get_visible_blueprints()
        if hasattr(card_or_index, "bp_info"):
            bp = blueprint_for_card(self._blueprints, card_or_index)
            if bp is None:
                return
            index = visible_index_for_path(visible, bp.path)
            if index < 0:
                return
        else:
            index = int(card_or_index)
            if index < 0 or index >= len(visible):
                return
            bp = visible[index]

        if multi:
            if index in self._selected_indices:
                self._selected_indices.discard(index)
            else:
                self._selected_indices.add(index)
        else:
            self._selected_indices = {index}

        highlight_cards_by_visible_index(self._cards, self._selected_indices)

        if self._on_select:
            self._on_select(bp)

    def _on_search(self):
        """Filter cards based on search text without destroying widgets."""
        if not self._cards:
            self._rebuild_cards(self._blueprints)
            return
        search = self.search_var.get()
        self._selected_indices.clear()
        for card in self._cards:
            card.pack_forget()
            card.index = -1
        packed = search_pack_order(self._cards, self._blueprints, search)
        for visible, card in enumerate(packed):
            card.index = visible
            card.pack(fill="x", padx=4, pady=3)

    def _get_visible_blueprints(self):
        """Return the currently visible (possibly filtered) blueprints."""
        search = self.search_var.get()
        return [bp for bp in self._blueprints if blueprint_matches_search(bp, search)]

    def get_selected_blueprints(self):
        """Return list of currently selected blueprint infos."""
        visible = self._get_visible_blueprints()
        return [visible[i] for i in sorted(self._selected_indices) if i < len(visible)]

    def get_selected_count(self) -> int:
        return len(self._selected_indices)

    def set_recent_blueprints(self, blueprint_names: List[str]):
        values = ["(none)"]
        self._recent_lookup = {}
        for idx, name in enumerate(blueprint_names):
            key = f"{idx + 1}. {name}"
            self._recent_lookup[key] = name
            values.append(key)
        self.recent_menu.configure(values=values)
        self.recent_var.set(values[0])

    def _on_recent_picked(self, value: str):
        if value == "(none)":
            return
        name = self._recent_lookup.get(value)
        if not name:
            return
        self.select_blueprint_by_name(name)
        if self._on_recent_select:
            self._on_recent_select(name)

    def select_blueprint_by_name(self, name: str, notify: bool = True) -> bool:
        visible = self._get_visible_blueprints()
        for idx, bp in enumerate(visible):
            if bp.display_name == name or bp.name == name:
                if notify:
                    self._handle_card_select(idx, multi=False)
                else:
                    self._selected_indices = {idx}
                    for i, card in enumerate(self._cards):
                        card.set_selected(card.index == idx)
                return True
        return False
