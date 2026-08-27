"""
Native Windows file drop helper for Tk/CTk windows.
"""

from __future__ import annotations

import sys
from typing import Callable, List


if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32

    WM_DROPFILES = 0x0233
    GWLP_WNDPROC = -4
    LONG_PTR = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LONG_PTR,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    # Configure 64-bit Windows pointer types
    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
        user32.SetWindowLongPtrW.restype = LONG_PTR
    else:
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
        user32.SetWindowLongW.restype = LONG_PTR

    user32.CallWindowProcW.argtypes = [LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = LONG_PTR


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
        try:
            self._hwnd = self.tk_window.winfo_id()
            if not self._hwnd:
                return False

            self._wndproc = WNDPROC(self._handle_window_message)
            set_wndproc = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            self._old_wndproc = set_wndproc(self._hwnd, GWLP_WNDPROC, ctypes.cast(self._wndproc, LONG_PTR).value)
            shell32.DragAcceptFiles(self._hwnd, True)
            self.enabled = True
            return True
        except Exception:
            return False

    def disable(self):
        if not self.enabled or not sys.platform.startswith("win"):
            return
        try:
            if self._hwnd:
                shell32.DragAcceptFiles(self._hwnd, False)
            if self._old_wndproc and self._hwnd:
                set_wndproc = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
                set_wndproc(self._hwnd, GWLP_WNDPROC, self._old_wndproc)
        except Exception:
            pass
        finally:
            self.enabled = False
            self._old_wndproc = None
            self._wndproc = None

    def _handle_window_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_DROPFILES:
                files = self._extract_drop_files(wparam)
                if files:
                    self.on_files(files)
                return 0
            if self._old_wndproc:
                return user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)
        except Exception:
            pass
        return 0

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
