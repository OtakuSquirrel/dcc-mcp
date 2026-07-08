"""Health checks in the registration model.

Two signals combine into a verdict:

* **connected** — is the DCC's registration still live? Free, from the
  hub. A disconnected instance is simply gone (``dead``).
* **responsive** — a ``ping`` that the plugin runs **on the DCC main
  thread**. This is the crucial bit: a frozen DCC (modal dialog, infinite
  loop) keeps its socket open on the network thread, so only a
  main-thread heartbeat reveals the freeze. No reply in time ⇒ busy/hung.

Windows OS checks (``IsHungAppWindow``, CPU sampling) refine "busy
computing" vs "truly hung" using the pid the DCC reported at
registration — no more scraping the pid from a port.

Verdicts: healthy | busy | hung | dead | unknown.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_IS_WIN = os.name == "nt"
_PING_TIMEOUT = 3.0


def check_window_responding(pid: int) -> bool | None:
    """Win32 IsHungAppWindow. Returns True/False/None (no window/unsupported)."""
    if not _IS_WIN:
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = False
    responding: bool | None = None

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        nonlocal found, responding
        if not user32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        if user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        found = True
        hung = user32.IsHungAppWindow(hwnd)
        responding = not hung
        return hung

    user32.EnumWindows(callback, 0)
    return responding if found else None


def sample_cpu_percent(pid: int, interval: float = 0.4) -> float | None:
    """CPU % via Win32 GetProcessTimes. None on unsupported/failure."""
    if not _IS_WIN:
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None

    def _cpu_time():
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e),
                                        ctypes.byref(k), ctypes.byref(u)):
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
        return round((t2 - t1) / 10_000_000 / interval * 100, 1)
    finally:
        kernel32.CloseHandle(h)


def _ping_main_thread(hub, instance_id: str, timeout: float = _PING_TIMEOUT) -> bool:
    """Ping that runs on the DCC main thread — reveals a wedged DCC.

    Runs in a helper thread with a hard timeout so this never hangs even
    if the DCC is frozen (the request itself would block otherwise)."""
    result = [False]

    def _run():
        try:
            hub.request(instance_id, "ping", timeout=timeout)
            result[0] = True
        except Exception:  # noqa: BLE001
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout + 0.5)
    return result[0]


def check_health(instance_id: str, hub) -> dict:
    """Composite verdict for a registered DCC.

    verdicts: healthy | busy | hung | dead | unknown
    """
    result = {
        "instance_id": instance_id,
        "kind": None,
        "pid": None,
        "connected": False,
        "responsive": False,
        "window_responding": None,
        "cpu_percent": None,
        "verdict": "dead",
        "details": "",
    }

    reg = hub.get(instance_id)
    if reg is None or reg._conn is None or not reg._conn.alive:
        result["details"] = "no live registration for this instance"
        return result

    result["connected"] = True
    result["kind"] = reg.kind
    result["pid"] = reg.pid

    responsive = _ping_main_thread(hub, instance_id)
    result["responsive"] = responsive

    if responsive:
        result["verdict"] = "healthy"
        result["details"] = "responsive"
        return result

    # Connected but the main thread didn't answer in time — busy or hung.
    # Use OS signals to tell them apart.
    pid = reg.pid
    win = check_window_responding(pid) if pid else None
    cpu = sample_cpu_percent(pid) if pid else None
    result["window_responding"] = win
    result["cpu_percent"] = cpu

    if cpu is not None and cpu > 10:
        result["verdict"] = "busy"
        result["details"] = f"main thread not answering, CPU {cpu}% — heavy compute"
    elif win is False:
        result["verdict"] = "hung"
        result["details"] = "main thread not answering and window not responding — hung"
    else:
        result["verdict"] = "busy"
        result["details"] = "main thread not answering — busy or briefly blocked"
    return result
