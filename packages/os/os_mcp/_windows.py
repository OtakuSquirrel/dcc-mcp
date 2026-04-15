"""Windows backend — Win32 API implementations.

All functions use `ctypes` to call Win32 directly (no pywin32 dependency
except for screenshots/clipboard which use Pillow/pywin32 where cleaner).
Every function is designed to be fast and non-blocking — queries that
could hang a normal API call (like talking to a frozen DCC) are avoided.

This module MUST NOT be imported on non-Windows platforms — the
module-level `ctypes.WinDLL(...)` calls will fail. The platform
dispatcher in `_platform.py` handles that.
"""

from __future__ import annotations

import ctypes
import logging
import os
import socket
import time
from ctypes import wintypes
from typing import Any

logger = logging.getLogger(__name__)

_PLATFORM = "Windows"

# ── Win32 library handles ──
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

# ── Win32 constants ──
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
TCP_TABLE_OWNER_PID_LISTENER = 3
AF_INET = 2
MIB_TCP_STATE_LISTEN = 2
GW_OWNER = 4
SW_RESTORE = 9
SW_SHOW = 5

# Dialog detection heuristics
_DIALOG_CLASSES = {"#32770", "QDialog", "QMessageBox", "SysDialog"}
_NON_DIALOG_KEYWORDS = {
    "console", ".hip", ".hipnc", ".hiplc",
    "houdini fx", "houdini core",
}


# ══════════════════════════════════════════════════════════════
# Port / process lookup
# ══════════════════════════════════════════════════════════════


class _MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


def _get_tcp_listener_table() -> list[tuple[int, int]]:
    """Return list of (local_port, pid) for all listening TCP sockets.

    Uses GetExtendedTcpTable — one fast kernel call, no subprocess.
    """
    size = wintypes.DWORD(0)
    # First call: get required buffer size
    _iphlpapi.GetExtendedTcpTable(
        None, ctypes.byref(size), False, AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER, 0,
    )
    if size.value == 0:
        return []

    buf = (ctypes.c_byte * size.value)()
    ret = _iphlpapi.GetExtendedTcpTable(
        buf, ctypes.byref(size), False, AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER, 0,
    )
    if ret != 0:
        logger.warning("GetExtendedTcpTable failed with code %d", ret)
        return []

    # First DWORD is entry count; rest is an array of MIB_TCPROW_OWNER_PID
    num_entries = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    rows_ptr = ctypes.cast(
        ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD),
        ctypes.POINTER(_MIB_TCPROW_OWNER_PID),
    )

    result = []
    for i in range(num_entries):
        row = rows_ptr[i]
        # dwLocalPort is big-endian in the low 16 bits
        port_be = row.dwLocalPort
        port = ((port_be & 0xFF) << 8) | ((port_be >> 8) & 0xFF)
        pid = row.dwOwningPid
        result.append((port, pid))
    return result


def is_port_open(port: int, host: str = "localhost", timeout: float = 0.3) -> bool:
    """Check if a TCP port is accepting connections (cross-platform)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def find_pid_for_port(port: int) -> int | None:
    """Return the PID of the process listening on a TCP port, or None."""
    for p, pid in _get_tcp_listener_table():
        if p == port:
            return pid
    return None


def list_listening_ports(port_min: int, port_max: int) -> dict[int, int]:
    """Return {port: pid} for all listening TCP sockets in the range."""
    return {
        p: pid
        for p, pid in _get_tcp_listener_table()
        if port_min <= p <= port_max
    }


# ══════════════════════════════════════════════════════════════
# Process info
# ══════════════════════════════════════════════════════════════


def get_exe_path(pid: int) -> str | None:
    """Return the full path to a process's main executable."""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        # QueryFullProcessImageNameW
        ok = _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        if not ok:
            return None
        return buf.value
    finally:
        _kernel32.CloseHandle(h)


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _get_memory_mb(pid: int) -> float | None:
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        pmc = _PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        ok = _psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
        if not ok:
            return None
        return round(pmc.WorkingSetSize / (1024 * 1024), 1)
    finally:
        _kernel32.CloseHandle(h)


def _get_start_time_iso(pid: int) -> str | None:
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_t = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = _kernel32.GetProcessTimes(
            h, ctypes.byref(creation), ctypes.byref(exit_t),
            ctypes.byref(kernel), ctypes.byref(user),
        )
        if not ok:
            return None
        # FILETIME → Unix epoch
        ft = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        # 100ns intervals since 1601-01-01 → seconds since 1970-01-01
        unix = (ft - 116444736000000000) / 10_000_000
        from datetime import datetime, timezone
        return datetime.fromtimestamp(unix, tz=timezone.utc).isoformat()
    finally:
        _kernel32.CloseHandle(h)


def get_process_info(pid: int) -> dict:
    """Return {pid, exe_path, memory_mb, cpu_percent, start_time}."""
    return {
        "pid": pid,
        "exe_path": get_exe_path(pid),
        "memory_mb": _get_memory_mb(pid),
        "cpu_percent": sample_cpu_percent(pid, interval=0.3),
        "start_time": _get_start_time_iso(pid),
    }


def kill_process(pid: int, force: bool = False) -> dict:
    """Terminate a process via TerminateProcess.

    On Windows there is no clean distinction between "graceful" and
    "force" at the OS level — TerminateProcess is the only kill primitive
    available without DCC-specific protocol messages. The `force` flag is
    kept for API symmetry with Unix.
    """
    h = _kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return {"killed": False, "pid": pid, "error": "OpenProcess failed (no permission or dead)"}
    try:
        ok = _kernel32.TerminateProcess(h, 1)
        return {
            "killed": bool(ok),
            "pid": pid,
            "method": "terminate",
        }
    finally:
        _kernel32.CloseHandle(h)


# ══════════════════════════════════════════════════════════════
# CPU sampling
# ══════════════════════════════════════════════════════════════


def sample_cpu_percent(pid: int, interval: float = 0.5) -> float | None:
    """Sample CPU usage % via GetProcessTimes. Sum across all cores."""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None

    def _cpu_time():
        c = wintypes.FILETIME()
        e = wintypes.FILETIME()
        k = wintypes.FILETIME()
        u = wintypes.FILETIME()
        ok = _kernel32.GetProcessTimes(
            h, ctypes.byref(c), ctypes.byref(e),
            ctypes.byref(k), ctypes.byref(u),
        )
        if not ok:
            return None
        kt = k.dwLowDateTime | (k.dwHighDateTime << 32)
        ut = u.dwLowDateTime | (u.dwHighDateTime << 32)
        return kt + ut

    try:
        t1 = _cpu_time()
        if t1 is None:
            return None
        time.sleep(interval)
        t2 = _cpu_time()
        if t2 is None:
            return None
        delta_s = (t2 - t1) / 10_000_000
        return round(delta_s / interval * 100, 1)
    finally:
        _kernel32.CloseHandle(h)


# ══════════════════════════════════════════════════════════════
# Window inspection
# ══════════════════════════════════════════════════════════════


def _enum_windows_for_pid(pid: int, callback_fn):
    """Helper: call `callback_fn(hwnd)` for each visible top-level window
    owned by the given PID. callback_fn can return False to stop enumeration.
    """
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        result = callback_fn(hwnd)
        # Stop enumeration if callback returns False
        return False if result is False else True

    _user32.EnumWindows(cb, 0)


def check_window_responding(pid: int) -> bool | None:
    """Check if a process's main window is responding.

    Returns True (responding), False (hung), or None (no window found).
    """
    found = False
    responding = None

    def _cb(hwnd):
        nonlocal found, responding
        if _user32.GetWindowTextLengthW(hwnd) <= 0:
            return True  # continue
        found = True
        hung = _user32.IsHungAppWindow(hwnd)
        responding = not hung
        return False  # stop on first responding window

    _enum_windows_for_pid(pid, _cb)
    return responding if found else None


def get_main_window_title(pid: int) -> str | None:
    """Return the title of a process's first visible titled window."""
    title: list[str | None] = [None]

    def _cb(hwnd):
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        t = buf.value.strip()
        if t:
            title[0] = t
            return False  # stop
        return True

    _enum_windows_for_pid(pid, _cb)
    return title[0]


def get_window_rect(pid: int) -> tuple[int, int, int, int] | None:
    """Return (x, y, width, height) of a process's first titled window."""
    result: list[tuple[int, int, int, int] | None] = [None]

    def _cb(hwnd):
        if _user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 100 or h < 100:
            return True  # skip tiny windows
        result[0] = (rect.left, rect.top, w, h)
        return False

    _enum_windows_for_pid(pid, _cb)
    return result[0]


def bring_window_to_front(pid: int) -> dict:
    """Bring a process's main window to the foreground."""
    brought: list[bool] = [False]

    def _cb(hwnd):
        if _user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        _user32.ShowWindow(hwnd, SW_RESTORE)
        ok = _user32.SetForegroundWindow(hwnd)
        brought[0] = bool(ok)
        return False

    _enum_windows_for_pid(pid, _cb)
    return {"pid": pid, "brought_to_front": brought[0]}


# ══════════════════════════════════════════════════════════════
# Modal dialog detection
# ══════════════════════════════════════════════════════════════


def _read_child_text(hwnd: int, max_children: int = 20) -> str:
    """Read text from child controls of a window."""
    texts: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child_cb(child_hwnd, _):
        if len(texts) >= max_children:
            return False
        length = _user32.GetWindowTextLengthW(child_hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(child_hwnd, buf, length + 1)
            t = buf.value.strip()
            if t:
                texts.append(t)
        return True

    _user32.EnumChildWindows(hwnd, child_cb, 0)
    return " | ".join(texts)


def detect_modal_dialogs(pid: int) -> list[dict]:
    """Detect modal/popup dialog windows belonging to a process."""
    dialogs: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True

        # Class name
        cls_buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls_buf, 256)
        cls_name = cls_buf.value

        owner = _user32.GetWindow(hwnd, GW_OWNER)
        is_owned = bool(owner)
        is_dialog_class = cls_name in _DIALOG_CLASSES

        # Title
        length = _user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

        # Rect
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        if w < 50 or h < 50:
            return True

        title_lower = title.lower()
        is_known_window = any(kw in title_lower for kw in _NON_DIALOG_KEYWORDS)

        is_dialog = False
        if is_owned:
            is_dialog = True
        elif not is_known_window and (is_dialog_class or (w < 800 and h < 600)):
            is_dialog = True

        if not is_dialog:
            return True

        child_text = _read_child_text(hwnd)
        if not title and not child_text:
            return True

        dialogs.append({
            "title": title or "(untitled)",
            "child_text": child_text,
            "class": cls_name,
            "width": w,
            "height": h,
            "owned": is_owned,
        })
        return True

    _user32.EnumWindows(callback, 0)
    return dialogs


# ══════════════════════════════════════════════════════════════
# Clipboard
# ══════════════════════════════════════════════════════════════


CF_UNICODETEXT = 13


def read_clipboard() -> str:
    """Read the system clipboard as Unicode text."""
    if not _user32.OpenClipboard(None):
        return ""
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        locked = _kernel32.GlobalLock(h)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            _kernel32.GlobalUnlock(h)
    finally:
        _user32.CloseClipboard()


GMEM_MOVEABLE = 0x0002


def write_clipboard(text: str) -> None:
    """Write text to the system clipboard."""
    if not _user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        _user32.EmptyClipboard()
        # Allocate moveable global memory for the text
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h:
            raise RuntimeError("GlobalAlloc failed")
        locked = _kernel32.GlobalLock(h)
        if not locked:
            raise RuntimeError("GlobalLock failed")
        try:
            ctypes.memmove(locked, encoded, len(encoded))
        finally:
            _kernel32.GlobalUnlock(h)
        _user32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        _user32.CloseClipboard()
