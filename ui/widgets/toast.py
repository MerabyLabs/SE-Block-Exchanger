"""
Toast Notification Widget
Non-blocking slide-in notifications that auto-dismiss
"""

from __future__ import annotations

from typing import Callable, List, Optional

import customtkinter as ctk
from ui.theme import TacticalTheme


class Toast(ctk.CTkFrame):
    """A single toast notification that slides in and auto-dismisses."""

    def __init__(
        self,
        master,
        message: str,
        level: str = "info",
        duration: int = 3000,
        on_dismiss: Optional[Callable[["Toast"], None]] = None,
    ):
        super().__init__(
            master,
            fg_color=TacticalTheme.BG_GLASS,
            border_width=1,
            border_color=self._get_border_color(level),
            corner_radius=6,
        )
        self._duration = duration
        self._after_id = None
        self._on_dismiss = on_dismiss
        self._dismissed = False

        bar = ctk.CTkFrame(
            self,
            width=4,
            corner_radius=0,
            fg_color=self._get_border_color(level),
        )
        bar.pack(side="left", fill="y", padx=(0, 8), pady=2)

        ctk.CTkLabel(
            self,
            text=message,
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_CYAN,
            wraplength=350,
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)

        close_btn = ctk.CTkButton(
            self,
            text="X",
            width=24,
            height=24,
            font=TacticalTheme.FONT_SMALL,
            fg_color="transparent",
            hover_color=TacticalTheme.BG_MEDIUM,
            text_color=TacticalTheme.TEXT_GRAY,
            command=self.dismiss,
        )
        close_btn.pack(side="right", padx=4, pady=4)

    @staticmethod
    def _get_border_color(level: str) -> str:
        colors = {
            "info": TacticalTheme.CYAN_PRIMARY,
            "success": TacticalTheme.GREEN_PRIMARY,
            "warning": TacticalTheme.ORANGE_PRIMARY,
            "error": TacticalTheme.RED_PRIMARY,
        }
        return colors.get(level, TacticalTheme.CYAN_PRIMARY)

    def show(self):
        """Display the toast and schedule auto-dismiss."""
        self.pack(fill="x", padx=10, pady=(0, 4))
        self.lift()
        if self._duration > 0:
            self._after_id = self.after(self._duration, self.dismiss)

    def dismiss(self):
        """Remove the toast."""
        if self._dismissed:
            return
        self._dismissed = True
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        callback = self._on_dismiss
        self.pack_forget()
        self.destroy()
        if callback:
            callback(self)


class ToastManager:
    """Manages a stack of toast notifications anchored to a parent widget."""

    def __init__(self, parent):
        self._parent = parent
        # Transparent + unplaced until a toast exists. An empty placed CTkFrame
        # paints a solid rectangle that blocks header/control-panel clicks.
        self._container = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            bg_color="transparent",
            width=1,
            height=1,
        )
        self._toasts: List[Toast] = []

    @property
    def visible(self) -> bool:
        return bool(self._container.place_info())

    def toast(self, message: str, level: str = "info", duration: int = 3000):
        """Show a new toast notification."""
        t = Toast(
            self._container,
            message,
            level,
            duration,
            on_dismiss=self._on_toast_dismissed,
        )
        self._toasts.append(t)
        self._container.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
        self._container.lift()
        t.show()
        return t

    def _on_toast_dismissed(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        if not self._toasts:
            self._container.place_forget()

    def dismiss_all(self) -> None:
        for toast in list(self._toasts):
            toast.dismiss()
        self._toasts.clear()
        self._container.place_forget()
