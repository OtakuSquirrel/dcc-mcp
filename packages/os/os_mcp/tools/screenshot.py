"""Screenshot tools — full desktop and per-window."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from os_mcp.server import mcp
from os_mcp._platform import get_window_rect


def _default_screenshot_path() -> Path:
    cache = Path.home() / ".dcc-mcp" / "cache" / "screenshots"
    cache.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return cache / f"screenshot_{ts}.png"


@mcp.tool()
def take_screenshot(save_to: str | None = None) -> dict:
    """Capture the full desktop as a PNG file.

    Uses Pillow's ImageGrab — works on Windows and macOS out of the box.
    Linux requires an X server (untested on Phase 1a).

    Args:
        save_to: Output file path. If None, saves to
                 ~/.dcc-mcp/cache/screenshots/screenshot_<timestamp>.png

    Returns:
        {"path": str, "width": int, "height": int}
    """
    from PIL import ImageGrab

    path = Path(save_to) if save_to else _default_screenshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab()
    img.save(str(path), "PNG")
    return {"path": str(path), "width": img.width, "height": img.height}


@mcp.tool()
def take_window_screenshot(pid: int, save_to: str | None = None) -> dict:
    """Capture the main window of a specific process.

    Finds the process's primary visible window, gets its bounding rect,
    and grabs that region. Fails if the window is minimized, off-screen,
    or if the process has no visible titled window.

    Args:
        pid: Process ID whose main window to capture.
        save_to: Output file path. If None, saves to
                 ~/.dcc-mcp/cache/screenshots/.

    Returns:
        {"path": str, "width": int, "height": int, "window_rect": [x, y, w, h]}
    """
    from PIL import ImageGrab

    rect = get_window_rect(pid)
    if rect is None:
        raise ValueError(f"No visible titled window found for PID {pid}")
    x, y, w, h = rect
    path = Path(save_to) if save_to else _default_screenshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(str(path), "PNG")
    return {
        "path": str(path),
        "width": img.width,
        "height": img.height,
        "window_rect": [x, y, w, h],
    }
