"""
Native Windows file drop helper for Tk/CTk windows.
"""

from __future__ import annotations

import sys
from typing import Callable, List

# Keep message ids at module level so close handling never depends on a
# Windows-only import succeeding partway through subclassing.
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SYSCOMMAND = 0x0112
WM_DROPFILES = 0x0233
SC_CLOSE = 0xF060
GWLP_WNDPROC = -4
GA_ROOT = 2


if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    LONG_PTR = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LONG_PTR,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )


def _is_close_message(msg: int, wparam: int) -> bool:
    """True for the messages the title-bar X / Alt+F4 send on Windows."""
    if msg == WM_CLOSE:
        return True
    if msg == WM_SYSCOMMAND and (int(wparam) & 0xFFF0) == SC_CLOSE:
        return True
    return False


class WindowsFileDropTarget:
    """Enable drag-and-drop of files/folders onto a Tk top-level window."""

    def __init__(self, tk_window, on_files: Callable[[List[str]], None]):
        self.tk_window = tk_window
        self.on_files = on_files
        self.enabled = False
        self._wndproc = None
        self._old_wndproc = None
        self._hwnd = None

    def enable(self) -> bool:
        if not sys.platform.startswith("win"):
            return False
        if self.enabled:
            return True
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return False

        self._hwnd = hwnd
        self._wndproc = WNDPROC(self._handle_window_message)
        previous = user32.SetWindowLongPtrW(self._hwnd, GWLP_WNDPROC, self._wndproc)
        if not previous:
            # Subclassing failed or there is no previous proc. Do not leave a
            # window with a Python WndProc and nothing to forward close/paint to.
            self._wndproc = None
            self._hwnd = None
            return False
        self._old_wndproc = previous
        shell32.DragAcceptFiles(self._hwnd, True)
        self.enabled = True
        return True

    def _resolve_hwnd(self) -> int:
        hwnd = int(self.tk_window.winfo_id() or 0)
        if not hwnd:
            return 0
        try:
            root = int(user32.GetAncestor(hwnd, GA_ROOT) or 0)
        except Exception:
            root = 0
        return root or hwnd

    def disable(self):
        if not self.enabled or not sys.platform.startswith("win"):
            return
        try:
            shell32.DragAcceptFiles(self._hwnd, False)
            if self._old_wndproc and self._hwnd:
                user32.SetWindowLongPtrW(self._hwnd, GWLP_WNDPROC, self._old_wndproc)
        finally:
            self.enabled = False
            self._old_wndproc = None
            self._wndproc = None
            self._hwnd = None

    def _forward(self, hwnd, msg, wparam, lparam):
        if self._old_wndproc:
            return user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_window_message(self, hwnd, msg, wparam, lparam):
        # Never swallow close. The previous handler returned 0 for WM_CLOSE,
        # which made the Windows title-bar X do nothing.
        if _is_close_message(msg, wparam):
            return self._forward(hwnd, msg, wparam, lparam)
        if msg == WM_DROPFILES:
            files = self._extract_drop_files(wparam)
            if files:
                try:
                    self.on_files(files)
                except Exception:
                    pass
            return 0
        if msg == WM_DESTROY:
            result = self._forward(hwnd, msg, wparam, lparam)
            self.enabled = False
            self._old_wndproc = None
            self._wndproc = None
            self._hwnd = None
            return result
        return self._forward(hwnd, msg, wparam, lparam)

    @staticmethod
    def _extract_drop_files(hdrop) -> List[str]:
        files: List[str] = []
        count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        for index in range(count):
            size = shell32.DragQueryFileW(hdrop, index, None, 0) + 1
            buffer = ctypes.create_unicode_buffer(size)
            shell32.DragQueryFileW(hdrop, index, buffer, size)
            files.append(buffer.value)
        shell32.DragFinish(hdrop)
        return files
