"""OS-level health checks for DCC processes.

Ported from the old ``dcc_mcp_core.health``. Pure OS queries with hard
timeouts — they NEVER hang even if the DCC is completely frozen. The
Win32 paths (window-responding, CPU, modal-dialog detection) are
Windows-only and degrade gracefully to ``None`` on macOS/Linux, where
the daemon still reports port/protocol liveness.

The daemon supplies the protocol ping via the unified transport, so
health here takes a ``ping_fn`` rather than importing transport.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_IS_WIN = os.name == "nt"


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def find_pid_for_port(port: int) -> int | None:
    """Find the PID listening on a TCP port (cross-platform)."""
    try:
        if _IS_WIN:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
                 f"-ErrorAction SilentlyContinue).OwningProcess"],
                capture_output=True, text=True, timeout=5,
            )
            out = r.stdout.strip()
            return int(out.split()[0]) if out else None
        # macOS/Linux: lsof
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout.strip()
        return int(out.split()[0]) if out else None
    except Exception:
        return None


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


def _ping_with_timeout(ping_fn: Callable[[], bool], timeout: float = 3.0) -> bool:
    result = [False]

    def _run():
        try:
            result[0] = ping_fn()
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


def check_health(port: int, ping_fn: Callable[[], bool] | None = None) -> dict:
    """Composite verdict for a DCC on ``port``.

    verdicts: healthy | busy | hung | no_protocol | dead | unknown
    """
    result = {
        "port": port,
        "pid": None,
        "process_alive": False,
        "window_responding": None,
        "port_listening": False,
        "protocol_responsive": False,
        "cpu_percent": None,
        "verdict": "dead",
        "details": "",
    }

    pid = find_pid_for_port(port)
    if pid is None:
        if is_port_open(port):
            result["port_listening"] = True
            result["verdict"] = "unknown"
            result["details"] = f"port {port} listening but PID unknown"
        else:
            result["details"] = "nothing listening on this port"
        return result

    result["pid"] = pid
    result["process_alive"] = True
    result["port_listening"] = is_port_open(port)

    proto = [False]
    cpu: list[float | None] = [None]
    win: list[bool | None] = [None]

    def do_proto():
        if ping_fn and result["port_listening"]:
            proto[0] = _ping_with_timeout(ping_fn, timeout=3)

    def do_cpu():
        cpu[0] = sample_cpu_percent(pid)

    def do_win():
        win[0] = check_window_responding(pid)

    threads = [threading.Thread(target=f, daemon=True) for f in (do_proto, do_cpu, do_win)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    result["protocol_responsive"] = proto[0]
    result["cpu_percent"] = cpu[0]
    result["window_responding"] = win[0]

    responding = win[0]
    proto_ok = proto[0]
    port_ok = result["port_listening"]
    c = cpu[0]

    if proto_ok:
        if responding is False:
            result["verdict"] = "busy"
            result["details"] = "GUI frozen but protocol responsive — likely computing"
        else:
            result["verdict"] = "healthy"
            result["details"] = "responsive"
    elif port_ok:
        if responding is False and (c is not None and c > 10):
            result["verdict"] = "busy"
            result["details"] = f"GUI/protocol unresponsive, CPU {c}% — heavy compute"
        elif responding is False:
            result["verdict"] = "hung"
            result["details"] = f"GUI/protocol unresponsive, CPU {c if c is not None else '?'}% — hung"
        else:
            result["verdict"] = "no_protocol"
            result["details"] = "window ok but protocol not answering"
    else:
        result["verdict"] = "no_protocol" if responding is not None else "dead"
        result["details"] = "process found but port not listening"

    return result
