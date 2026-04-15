"""Platform dispatcher.

Re-exports the correct backend module based on `sys.platform`. The
platform-specific modules (`_windows.py`, `_macos.py`, `_linux.py`) all
expose the same function surface. `_windows.py` touches `ctypes.WinDLL`
at import time, which would crash on non-Windows — the conditional
import below ensures it is never loaded off Windows.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from ._windows import (  # noqa: F401
        is_port_open,
        find_pid_for_port,
        list_listening_ports,
        get_exe_path,
        get_main_window_title,
        get_window_rect,
        check_window_responding,
        detect_modal_dialogs,
        sample_cpu_percent,
        get_process_info,
        kill_process,
        bring_window_to_front,
        read_clipboard,
        write_clipboard,
    )
elif sys.platform == "darwin":
    from ._macos import (  # noqa: F401
        is_port_open,
        find_pid_for_port,
        list_listening_ports,
        get_exe_path,
        get_main_window_title,
        get_window_rect,
        check_window_responding,
        detect_modal_dialogs,
        sample_cpu_percent,
        get_process_info,
        kill_process,
        bring_window_to_front,
        read_clipboard,
        write_clipboard,
    )
elif sys.platform.startswith("linux"):
    from ._linux import (  # noqa: F401
        is_port_open,
        find_pid_for_port,
        list_listening_ports,
        get_exe_path,
        get_main_window_title,
        get_window_rect,
        check_window_responding,
        detect_modal_dialogs,
        sample_cpu_percent,
        get_process_info,
        kill_process,
        bring_window_to_front,
        read_clipboard,
        write_clipboard,
    )
else:
    raise RuntimeError(f"os-mcp: unsupported platform {sys.platform}")
