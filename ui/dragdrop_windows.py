"""
Native Windows file drop helper for Tk/CTk windows.
"""

from __future__ import annotations

import sys
import traceback
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
    kernel32 = ctypes.windll.kernel32
    # 64-bit Windows uses pointer-sized WPARAM/LPARAM. Without explicit
    # prototypes, ctypes treats them as 32-bit ints and overflows.
    LRESULT = ctypes.c_ssize_t
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t
    HWND = wintypes.HWND
    LONG_PTR = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, wintypes.UINT, WPARAM, LPARAM)

    user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.CallWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.GetAncestor.argtypes = [HWND, wintypes.UINT]
    user32.GetAncestor.restype = HWND
    kernel32.SetLastError.argtypes = [wintypes.DWORD]
    kernel32.SetLastError.restype = None
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    shell32.DragAcceptFiles.argtypes = [HWND, wintypes.BOOL]
    shell32.DragAcceptFiles.restype = None
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [wintypes.HANDLE]
    shell32.DragFinish.restype = None


def _mask_wparam(value) -> int:
    return int(value) & 0xFFFFFFFFFFFFFFFF


def _mask_lparam(value) -> int:
    raw = int(value) & 0xFFFFFFFFFFFFFFFF
    if raw >= 1 << 63:
        raw -= 1 << 64
    return raw


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
        kernel32.SetLastError(0)
        previous = user32.SetWindowLongPtrW(
            self._hwnd,
            GWLP_WNDPROC,
            ctypes.cast(self._wndproc, ctypes.c_void_p),
        )
        if not previous and kernel32.GetLastError() != 0:
            # Subclassing failed. Do not leave a window with a Python WndProc
            # and nothing to forward close/paint to.
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
            root = 0  # GetAncestor unavailable or HWND already gone
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
        wp = _mask_wparam(wparam)
        lp = _mask_lparam(lparam)
        if self._old_wndproc:
            return user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wp, lp)
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _handle_window_message(self, hwnd, msg, wparam, lparam):
        # Never swallow close. The previous handler returned 0 for WM_CLOSE,
        # which made the Windows title-bar X do nothing.
        try:
            if _is_close_message(msg, wparam):
                return self._forward(hwnd, msg, wparam, lparam)
            if msg == WM_DROPFILES:
                files = self._extract_drop_files(wparam)
                if files:
                    self._invoke_drop_callback(files)
                return 0
            if msg == WM_DESTROY:
                result = self._forward(hwnd, msg, wparam, lparam)
                self.enabled = False
                self._old_wndproc = None
                self._wndproc = None
                self._hwnd = None
                return result
            return self._forward(hwnd, msg, wparam, lparam)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            try:
                return self._forward(hwnd, msg, wparam, lparam)
            except Exception:
                return 0

    def _invoke_drop_callback(self, files: List[str]) -> None:
        """Run the drop callback; log failures but do not raise into Explorer."""
        try:
            self.on_files(files)
        except Exception:
            print(
                "Windows file drop callback failed; acknowledging drop so Explorer does not retry.",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)

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
