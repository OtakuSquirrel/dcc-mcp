"""End-to-end tests for the daemon using a fake in-process DCC.

The fake DCC runs the real shared ``DCCServer`` with a queue-based
main-thread simulation, so these exercise the actual wire protocol,
transport pool, registry discovery, health, and error propagation —
everything except a real bpy/hou/unreal runtime.

Parametrized over a Blender-range and a Unreal-range port: both use the
JSON-socket adapter, so the same suite validates the UE path (which
shares Blender's vendored socket server and ``JsonSocketAdapter``).
"""

from __future__ import annotations

import os
import queue
import threading
import time

import pytest

from dcc_socket_server import DCCServer, default_info
from dcc_daemon.core import DaemonCore

# (kind, port, version). Port ranges pick the adapter: 19811+ and 20811+
# both route to JsonSocketAdapter, so this covers Blender and UE.
_CASES = [
    ("blender", 19877, "4.2.0"),
    ("ue", 20877, "5.4.0"),
]


@pytest.fixture(params=_CASES, ids=lambda c: c[0])
def fake_dcc(request):
    """Start a fake DCC on a test port; yield (core, port, state, kind, version)."""
    kind, port, version = request.param
    jobs: "queue.Queue[tuple]" = queue.Queue()
    stop_flag = threading.Event()

    def run_on_main(fn):
        box: dict = {}
        ev = threading.Event()
        jobs.put((fn, box, ev))
        ev.wait(timeout=10)
        if "err" in box:
            raise box["err"]
        return box["res"]

    def main_loop():
        while not stop_flag.is_set():
            try:
                fn, box, ev = jobs.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                box["res"] = fn()
            except Exception as e:  # noqa: BLE001
                box["err"] = e
            finally:
                ev.set()

    t = threading.Thread(target=main_loop, daemon=True)
    t.start()

    state = {"objects": ["Cube"]}
    server = DCCServer(
        kind=kind,
        run_on_main=run_on_main,
        get_info=lambda: default_info(kind, version, "scene.file"),
        exec_globals=lambda: {"STATE": state},
        screenshot=lambda: "aVZCT1J3MEtHZ28=",
    )
    server.start(port)
    time.sleep(0.2)

    yield DaemonCore(), port, state, kind, version

    server.stop()
    stop_flag.set()


def test_get_info(fake_dcc):
    core, port, _, kind, version = fake_dcc
    info = core.get_info(port)
    assert info["kind"] == kind
    assert info["version"] == version
    assert info["pid"] == os.getpid()


def test_execute_python_returns_result(fake_dcc):
    core, port, *_ = fake_dcc
    out = core.execute_python(port, "result = STATE['objects'] + ['Sphere']")
    assert out == {"port": port, "result": ["Cube", "Sphere"]}


def test_execute_python_mutates_state(fake_dcc):
    core, port, state, *_ = fake_dcc
    core.execute_python(port, "STATE['objects'].append('Light')")
    assert state["objects"] == ["Cube", "Light"]


def test_health_verdict(fake_dcc):
    core, port, *_ = fake_dcc
    h = core.health(port)
    assert h["verdict"] == "healthy"
    assert h["protocol_responsive"] is True


def test_screenshot_base64(fake_dcc):
    core, port, *_ = fake_dcc
    b64 = core.screenshot(port)
    assert b64 == "aVZCT1J3MEtHZ28="


def test_list_instances_discovers(fake_dcc):
    core, port, _, kind, _ = fake_dcc
    found = [i for i in core.list_instances(refresh=True) if i["port"] == port]
    assert found and found[0]["kind"] == kind


def test_error_propagation(fake_dcc):
    from dcc_daemon.transport import DCCError
    core, port, *_ = fake_dcc
    with pytest.raises(DCCError) as ei:
        core.execute_python(port, "raise ValueError('boom')")
    assert "boom" in str(ei.value)
    assert ei.value.traceback  # plugin sent a traceback


def test_unknown_command_errors(fake_dcc):
    from dcc_daemon.transport import DCCError
    core, port, *_ = fake_dcc
    with pytest.raises(DCCError):
        core.transport._get_or_open(port)._send("frobnicate")
