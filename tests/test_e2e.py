"""End-to-end tests for the daemon in the registration model.

A fake DCC runs the real shared ``DCCServer`` (from ``plugins/common/``),
which dials a real ``RegistrationHub`` on loopback, registers, and serves
pushed requests — exercising the actual wire protocol, hub routing,
request multiplexing, health, and error propagation, everything except a
real bpy/hou/unreal/maya runtime.

Parametrized over all four DCC kinds (one protocol for all).
"""

from __future__ import annotations

import os
import queue
import threading
import time

import pytest

from dcc_socket_server import DCCServer, default_info
from dcc_mcp.core import DaemonCore
from dcc_mcp.hub import RegistrationHub

_CASES = [
    ("blender", "4.2.0"),
    ("houdini", "20.5.0"),
    ("ue", "5.4.0"),
    ("maya", "2025"),
]


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(params=_CASES, ids=lambda c: c[0])
def fake_dcc(request):
    """Start a hub + a fake DCC that registers; yield (core, instance_id, state, kind, version)."""
    kind, version = request.param

    # Real hub listening on an ephemeral port.
    hub = RegistrationHub()
    reg_port = _free_port()
    hub.start("127.0.0.1", reg_port)
    captured_pids: list[int] = []

    def capture_window(pid: int) -> bytes:
        captured_pids.append(pid)
        return b"\x89PNG\r\n\x1a\nwindow-capture"

    core = DaemonCore(hub=hub, window_capturer=capture_window)

    # Fake DCC main-thread bridge (queue + worker, like bpy.app.timers).
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

    threading.Thread(target=main_loop, daemon=True).start()

    state = {"objects": ["Cube"]}
    server = DCCServer(
        kind=kind,
        run_on_main=run_on_main,
        get_info=lambda: default_info(kind, version, "scene.file"),
        exec_globals=lambda: {"STATE": state},
    )
    server.start(reg_port)  # dial the hub

    # Wait for registration to land.
    instance_id = None
    for _ in range(100):
        insts = core.list_instances()
        if insts:
            instance_id = insts[0]["instance_id"]
            break
        time.sleep(0.05)
    assert instance_id, "DCC did not register in time"

    yield core, instance_id, state, kind, version, captured_pids

    server.stop()
    stop_flag.set()
    hub.stop()


def test_registration_metadata(fake_dcc):
    core, iid, _, kind, version, _ = fake_dcc
    inst = next(i for i in core.list_instances() if i["instance_id"] == iid)
    assert inst["kind"] == kind
    assert inst["version"] == version
    assert inst["pid"] == os.getpid()
    assert inst["connected"] is True
    assert iid == f"{kind}-1"


def test_get_info(fake_dcc):
    core, iid, _, kind, version, _ = fake_dcc
    info = core.get_info(iid)
    assert info["kind"] == kind
    assert info["version"] == version


def test_execute_python_returns_result(fake_dcc):
    core, iid, *_ = fake_dcc
    out = core.execute_python(iid, "result = STATE['objects'] + ['Sphere']")
    assert out == {"instance_id": iid, "result": ["Cube", "Sphere"]}


def test_execute_python_mutates_state(fake_dcc):
    core, iid, state, *_ = fake_dcc
    core.execute_python(iid, "STATE['objects'].append('Light')")
    assert state["objects"] == ["Cube", "Light"]


def test_health_verdict(fake_dcc):
    core, iid, *_ = fake_dcc
    h = core.health(iid)
    assert h["verdict"] == "healthy"
    assert h["connected"] is True
    assert h["responsive"] is True


def test_screenshot_uses_registered_process_window(fake_dcc):
    core, iid, _, _, _, captured_pids = fake_dcc
    assert core.screenshot(iid) == b"\x89PNG\r\n\x1a\nwindow-capture"
    assert captured_pids == [os.getpid()]


def test_error_propagation(fake_dcc):
    from dcc_mcp.core import DCCError
    core, iid, *_ = fake_dcc
    with pytest.raises(DCCError) as ei:
        core.execute_python(iid, "raise ValueError('boom')")
    assert "boom" in str(ei.value)
    assert ei.value.traceback


def test_disconnect_drops_instance(fake_dcc):
    core, iid, _, _, _, _ = fake_dcc
    # health of an unknown instance is 'dead', not an exception
    dead = core.health("nope-9")
    assert dead["verdict"] == "dead"
    assert dead["connected"] is False
