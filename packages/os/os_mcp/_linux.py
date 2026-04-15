"""Linux backend — stubs for Phase 1a.

Every OS-level entry point raises NotImplementedError. Real Linux
implementations (/proc, xdotool, lsof) are deferred to a later phase.

`is_port_open` is implemented because it's a pure socket call.
"""

from __future__ import annotations

import socket

_PLATFORM = "Linux"


def _ni(fn_name: str):
    raise NotImplementedError(
        f"os-mcp: {_PLATFORM} support not yet implemented for {fn_name}()"
    )


def is_port_open(port: int, host: str = "localhost", timeout: float = 0.3) -> bool:
    """Check if a TCP port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def find_pid_for_port(port: int) -> int | None:
    _ni("find_pid_for_port")


def list_listening_ports(port_min: int, port_max: int) -> dict[int, int]:
    _ni("list_listening_ports")


def get_exe_path(pid: int) -> str | None:
    _ni("get_exe_path")


def get_main_window_title(pid: int) -> str | None:
    _ni("get_main_window_title")


def get_window_rect(pid: int) -> tuple[int, int, int, int] | None:
    _ni("get_window_rect")


def check_window_responding(pid: int) -> bool | None:
    _ni("check_window_responding")


def detect_modal_dialogs(pid: int) -> list[dict]:
    _ni("detect_modal_dialogs")


def sample_cpu_percent(pid: int, interval: float = 0.5) -> float | None:
    _ni("sample_cpu_percent")


def get_process_info(pid: int) -> dict:
    _ni("get_process_info")


def kill_process(pid: int, force: bool = False) -> dict:
    _ni("kill_process")


def bring_window_to_front(pid: int) -> dict:
    _ni("bring_window_to_front")


def read_clipboard() -> str:
    _ni("read_clipboard")


def write_clipboard(text: str) -> None:
    _ni("write_clipboard")
