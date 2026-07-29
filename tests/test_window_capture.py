from dcc_mcp.window_capture import WindowCandidate, _select_main_window


def _candidate(hwnd, width, height, *, owned=False, minimized=False):
    return WindowCandidate(
        hwnd=hwnd,
        title=f"window-{hwnd}",
        rect=(0, 0, width, height),
        owned=owned,
        minimized=minimized,
    )


def test_select_main_window_prefers_unowned_normal_window():
    selected = _select_main_window(
        [
            _candidate(1, 2000, 1200, owned=True),
            _candidate(2, 1200, 800),
            _candidate(3, 1600, 900, minimized=True),
        ]
    )
    assert selected is not None
    assert selected.hwnd == 2


def test_select_main_window_uses_largest_usable_window():
    selected = _select_main_window(
        [_candidate(1, 50, 50), _candidate(2, 800, 600), _candidate(3, 1200, 800)]
    )
    assert selected is not None
    assert selected.hwnd == 3


def test_select_main_window_rejects_tiny_surfaces():
    assert _select_main_window([_candidate(1, 50, 50)]) is None


def test_select_main_window_accepts_minimized_placeholder_bounds():
    selected = _select_main_window([_candidate(1, 219, 39, minimized=True)])
    assert selected is not None
    assert selected.hwnd == 1
