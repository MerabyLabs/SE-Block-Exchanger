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
        on_dismiss: Optional[Callable[[Toast], None]] = None,
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

        # Color bar on the left
        bar = ctk.CTkFrame(
            self, width=4, corner_radius=0,
            fg_color=self._get_border_color(level),
        )
        bar.pack(side="left", fill="y", padx=(0, 8), pady=2)

        # Message
        ctk.CTkLabel(
            self, text=message,
            font=TacticalTheme.FONT_NORMAL,
            text_color=TacticalTheme.TEXT_CYAN,
            wraplength=350,
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)

        # Close button
        close_btn = ctk.CTkButton(
            self, text="X", width=24, height=24,
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
        self._after_id = self.after(self._duration, self.dismiss)

    def dismiss(self):
        """Remove the toast."""
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass  # after id already fired or widget is gone
            self._after_id = None
        if self._on_dismiss:
            try:
                self._on_dismiss(self)
            except Exception:
                pass  # dismiss callback must not block destroying the toast
        self.pack_forget()
        self.destroy()


class ToastManager:
    """Manages a stack of toast notifications anchored to a parent widget."""

    def __init__(self, parent):
        self._parent = parent
        self._container = ctk.CTkFrame(parent, fg_color="transparent")
        self._active_toasts: List[Toast] = []
        # Note: Container is not placed until a toast is active to prevent blocking header buttons

    def toast(self, message: str, level: str = "info", duration: int = 3000):
        """Show a new toast notification."""
        if not self._active_toasts:
            # Anchor cleanly at bottom-right above footer
            self._container.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-45)
            self._container.lift()

        t = Toast(
            self._container,
            message,
            level=level,
            duration=duration,
            on_dismiss=self._handle_toast_dismiss,
        )
        self._active_toasts.append(t)
        t.show()

    def _handle_toast_dismiss(self, toast_item: Toast):
        if toast_item in self._active_toasts:
            self._active_toasts.remove(toast_item)
        if not self._active_toasts:
            self._container.place_forget()
