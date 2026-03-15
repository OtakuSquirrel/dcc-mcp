"""Health check utilities for DCC processes (Windows).

All checks have hard timeouts and will NEVER hang, even if the DCC
process is completely frozen. Pure OS-level queries — no DCC API calls.

These are standalone functions that can be used by any DCC MCP server.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


def find_pid_for_port(port: int, sessions: list[dict] | None = None) -> int | None:
    """Find the PID of the process listening on a TCP port.

    Checks the session list first (instant), then falls back
    to OS-level port query.

    Args:
        port: TCP port to query.
        sessions: Optional pre-fetched session list for fast lookup.
    """
    # Fast path: session registry
    if sessions:
        for s in sessions:
            if s.get("port") == port and s.get("dcc_pid"):
                return s["dcc_pid"]

    # Fallback: query OS
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
                 f"-ErrorAction SilentlyContinue).OwningProcess"],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip():
                return int(r.stdout.strip().split()[0])
        except Exception:
            pass
    return None


def check_window_responding(pid: int) -> bool | None:
    """Check if a process's window is responding via Win32 IsHungAppWindow.

    Returns True (responding), False (hung), or None (no window found).
    Pure Win32 API — queries the OS, never contacts the DCC. Cannot hang.
    """
    if os.name != "nt":
        return None  # Not supported on non-Windows

    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    found = False
    responding = None

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        nonlocal found, responding
        if not _user32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        if _user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        found = True
        hung = _user32.IsHungAppWindow(hwnd)
        responding = not hung
        return hung  # Stop on first responding window
    _user32.EnumWindows(callback, 0)
    return responding if found else None


def sample_cpu_percent(pid: int, interval: float = 0.5) -> float | None:
    """Sample CPU usage % via Win32 GetProcessTimes.

    Returns total CPU % (sum of all cores), or None on failure.
    Pure Win32 API — queries the OS kernel. Cannot hang.
    """
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None

    def _cpu_time():
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
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


def is_port_open(port: int, host: str = "localhost", timeout: float = 0.3) -> bool:
    """Check if a TCP port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def tcp_ping_with_timeout(
    host: str,
    port: int,
    connect_fn: callable,
    timeout: float = 3.0,
) -> bool:
    """Run a DCC-specific ping in a daemon thread with hard timeout.

    NEVER hangs. If the thread gets stuck inside a frozen DCC,
    the daemon flag ensures cleanup on process exit.

    Args:
        host: Host to connect to.
        port: Port to connect to.
        connect_fn: Callable(host, port) -> bool. Should connect, ping, close.
        timeout: Max seconds to wait.

    Returns:
        True if ping succeeded within timeout.
    """
    result = [False]

    def _ping():
        try:
            result[0] = connect_fn(host, port)
        except Exception:
            pass

    t = threading.Thread(target=_ping, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


def check_health(
    port: int,
    ping_fn: callable | None = None,
    sessions: list[dict] | None = None,
) -> dict:
    """Comprehensive health check for a DCC on a given port.

    Combines OS-level and protocol-level signals to produce a verdict:
    - healthy: GUI responsive + protocol working
    - busy: GUI frozen but protocol OK (or high CPU)
    - hung: GUI frozen + protocol unresponsive + low CPU
    - dead: No process found on this port
    - no_protocol: DCC running but port not listening

    Args:
        port: TCP port to check.
        ping_fn: Optional callable(host, port) -> bool for protocol ping.
        sessions: Optional pre-fetched session list.

    Returns:
        Dict with verdict, individual check results, and details.
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

    # Find PID
    pid = find_pid_for_port(port, sessions)
    if pid is None:
        if is_port_open(port):
            result["port_listening"] = True
            result["verdict"] = "unknown"
            result["details"] = f"Port {port} listening but cannot determine PID."
        else:
            result["verdict"] = "dead"
            result["details"] = "No process listening on this port."
        return result

    result["pid"] = pid
    result["process_alive"] = True
    result["port_listening"] = is_port_open(port)

    # Run checks in parallel (max ~3s wall time)
    protocol_result = [False]
    cpu_result = [None]
    window_result = [None]

    def do_protocol():
        if ping_fn and result["port_listening"]:
            protocol_result[0] = tcp_ping_with_timeout("localhost", port, ping_fn, timeout=3)

    def do_cpu():
        cpu_result[0] = sample_cpu_percent(pid, interval=0.5)

    def do_window():
        window_result[0] = check_window_responding(pid)

    threads = [
        threading.Thread(target=do_protocol, daemon=True),
        threading.Thread(target=do_cpu, daemon=True),
        threading.Thread(target=do_window, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    result["protocol_responsive"] = protocol_result[0]
    result["cpu_percent"] = cpu_result[0]
    result["window_responding"] = window_result[0]

    # Verdict
    responding = result["window_responding"]
    proto_ok = result["protocol_responsive"]
    port_ok = result["port_listening"]
    cpu = result["cpu_percent"]

    if proto_ok:
        if responding is False:
            result["verdict"] = "busy"
            result["details"] = "GUI frozen but protocol responsive — likely computing"
        else:
            result["verdict"] = "healthy"
            result["details"] = "DCC is responsive"
    elif port_ok:
        if responding is False:
            if cpu is not None and cpu > 10:
                result["verdict"] = "busy"
                result["details"] = (
                    f"GUI and protocol unresponsive, CPU at {cpu}% — "
                    f"likely heavy computation, may recover"
                )
            else:
                cpu_str = f"{cpu}%" if cpu is not None else "unknown"
                result["verdict"] = "hung"
                result["details"] = (
                    f"GUI and protocol unresponsive, CPU {cpu_str} — "
                    f"appears hung"
                )
        else:
            result["verdict"] = "protocol_stuck"
            result["details"] = "Window responding but protocol not answering"
    else:
        if responding is not None:
            result["verdict"] = "no_protocol"
            result["details"] = "DCC running but port not listening"
        else:
            result["verdict"] = "dead"
            result["details"] = "Process found by PID but no window and no protocol"

    return result
