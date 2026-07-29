"""Capture a registered DCC's real Windows application window.

This captures desktop pixels owned by Windows. It never asks a DCC to
render or capture its own viewport.
"""

from __future__ import annotations

import ctypes
import io
import os
import time
from ctypes import wintypes
from dataclasses import dataclass


class WindowCaptureError(RuntimeError):
    """Raised when a process window cannot be found or captured."""


_MAX_OUTPUT_SIZE = (1920, 1080)


@dataclass(frozen=True)
class WindowCandidate:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    owned: bool
    minimized: bool

    @property
    def area(self) -> int:
        left, top, right, bottom = self.rect
        return max(0, right - left) * max(0, bottom - top)


def _select_main_window(candidates: list[WindowCandidate]) -> WindowCandidate | None:
    """Prefer a normal, non-minimized window, then the largest window."""
    # Minimized top-level windows use a tiny off-screen placeholder rect;
    # accept them here because capture restores the window before reading
    # its real bounds. Tiny non-minimized helper surfaces stay excluded.
    usable = [
        candidate
        for candidate in candidates
        if candidate.minimized or candidate.area >= 10_000
    ]
    if not usable:
        return None
    return max(
        usable,
        key=lambda candidate: (
            not candidate.owned,
            not candidate.minimized,
            candidate.area,
        ),
    )


def _windows_api():
    if os.name != "nt":
        raise WindowCaptureError("system window screenshots are supported on Windows only")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    return user32, dwmapi, kernel32


def _enable_dpi_awareness(user32) -> None:
    # Match window coordinates to physical pixels on mixed-DPI displays.
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _window_rect(hwnd: int, user32, dwmapi) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS includes the actual visible window frame.
    try:
        result = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)
        )
    except (AttributeError, OSError):
        result = -1
    if result != 0 and not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise WindowCaptureError(f"Windows could not read bounds for window {hwnd}")
    return rect.left, rect.top, rect.right, rect.bottom


def find_process_main_window(pid: int) -> WindowCandidate:
    """Find the most likely visible top-level application window for ``pid``."""
    user32, dwmapi, _kernel32 = _windows_api()
    _enable_dpi_awareness(user32)
    candidates: list[WindowCandidate] = []
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    @enum_proc_type
    def visit(hwnd, _lparam):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != pid or not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)

        cloaked = wintypes.DWORD()
        try:
            dwmapi.DwmGetWindowAttribute(
                hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
        except (AttributeError, OSError):
            cloaked.value = 0
        if cloaked.value:
            return True

        try:
            rect = _window_rect(int(hwnd), user32, dwmapi)
        except WindowCaptureError:
            return True
        candidates.append(
            WindowCandidate(
                hwnd=int(hwnd),
                title=title_buffer.value,
                rect=rect,
                owned=bool(user32.GetWindow(hwnd, 4)),  # GW_OWNER
                minimized=bool(user32.IsIconic(hwnd)),
            )
        )
        return True

    if not user32.EnumWindows(visit, 0):
        raise WindowCaptureError("Windows failed while enumerating application windows")
    selected = _select_main_window(candidates)
    if selected is None:
        raise WindowCaptureError(f"no visible application window found for PID {pid}")
    return selected


def _activate_window(hwnd: int, user32, kernel32) -> None:
    """Best-effort foreground activation so desktop pixels are unobscured."""
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )
    attached = bool(
        foreground_thread
        and foreground_thread != current_thread
        and user32.AttachThreadInput(current_thread, foreground_thread, True)
    )
    try:
        user32.BringWindowToTop(wintypes.HWND(hwnd))
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def capture_process_window(pid: int, *, settle_seconds: float = 0.2) -> bytes:
    """Return a PNG of the real Windows top-level window owned by ``pid``."""
    from PIL import Image, ImageGrab

    user32, dwmapi, kernel32 = _windows_api()
    candidate = find_process_main_window(pid)
    hwnd = candidate.hwnd
    previous_foreground = int(user32.GetForegroundWindow() or 0)
    was_minimized = bool(user32.IsIconic(wintypes.HWND(hwnd)))

    try:
        if was_minimized:
            user32.ShowWindow(wintypes.HWND(hwnd), 9)  # SW_RESTORE
        _activate_window(hwnd, user32, kernel32)
        if settle_seconds > 0:
            time.sleep(settle_seconds)

        left, top, right, bottom = _window_rect(hwnd, user32, dwmapi)
        if right <= left or bottom <= top:
            raise WindowCaptureError(
                f"window for PID {pid} has invalid bounds {(left, top, right, bottom)}"
            )
        image = ImageGrab.grab(
            bbox=(left, top, right, bottom),
            include_layered_windows=True,
            all_screens=True,
        )
        image.thumbnail(_MAX_OUTPUT_SIZE, resample=Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    except WindowCaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 - expose a stable MCP-facing error
        raise WindowCaptureError(f"failed to capture window for PID {pid}: {exc}") from exc
    finally:
        if previous_foreground and previous_foreground != hwnd:
            _activate_window(previous_foreground, user32, kernel32)
        if was_minimized:
            user32.ShowWindow(wintypes.HWND(hwnd), 6)  # SW_MINIMIZE
