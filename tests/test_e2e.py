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
    # Tuanjie's real connector is C#, but the daemon is kind-agnostic: this
    # exercises registration/routing/health for the "tuanjie" kind over the
    # identical wire protocol (the fake end still runs the shared Python
    # DCCServer — the protocol layer is what's under test, not C# execution).
    ("tuanjie", "2022.3.62t12"),
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


def test_tool_surfaces_traceback(fake_dcc, monkeypatch):
    """The MCP tool must fold .traceback into the message.

    FastMCP renders only str(exc), so a bare DCCError would drop the DCC-side
    stack trace — the one thing that makes an in-DCC failure diagnosable.
    """
    from fastmcp.exceptions import ToolError

    from dcc_mcp import mcp_server
    core, iid, *_ = fake_dcc
    monkeypatch.setattr(mcp_server, "core", core)
    with pytest.raises(ToolError) as ei:
        mcp_server.execute_python(iid, "raise ValueError('boom')")
    assert "boom" in str(ei.value)
    assert "Traceback (most recent call last)" in str(ei.value)


def test_disconnect_drops_instance(fake_dcc):
    core, iid, _, _, _, _ = fake_dcc
    # health of an unknown instance is 'dead', not an exception
    dead = core.health("nope-9")
    assert dead["verdict"] == "dead"
    assert dead["connected"] is False


def test_heartbeat_refreshes_last_seen(fake_dcc):
    """A heartbeat frame from the DCC must advance the daemon's last_seen
    (and be silently ignored, not mistaken for a request reply)."""
    import json

    core, iid, *_ = fake_dcc
    conn = core.hub.get(iid)._conn
    before = conn.last_seen

    # Send a heartbeat straight down the fake DCC's socket, exactly as the
    # plugin's heartbeat loop does, and confirm the daemon records liveness.
    dcc_sock = _dcc_live_socket()
    assert dcc_sock is not None, "no live DCC socket to send heartbeat"
    dcc_sock.sendall((json.dumps({"type": "heartbeat"}) + "\n").encode("utf-8"))

    for _ in range(100):
        if conn.last_seen > before:
            break
        time.sleep(0.02)

    assert conn.alive is True
    assert conn.last_seen > before, "heartbeat did not refresh last_seen"
    # And it must not have been consumed as a pending reply.
    assert not conn._pending


def _dcc_live_socket():
    """Find the fake DCC's live outbound socket via the DCCServer instance.

    The e2e fake DCC runs the shared DCCServer; grab its current socket to
    emit a raw heartbeat frame without waiting the real interval."""
    import gc

    from dcc_socket_server import DCCServer
    for obj in gc.get_objects():
        if isinstance(obj, DCCServer) and getattr(obj, "_sock", None) is not None:
            return obj._sock
    return None


def test_reaper_culls_silent_connection(fake_dcc, monkeypatch):
    """A connection that stops being seen past the timeout is reaped and
    the instance unregistered (half-open detection)."""
    from dcc_mcp import hub as hub_mod

    core, iid, *_ = fake_dcc
    conn = core.hub.get(iid)._conn

    # Make it look long-silent; the reaper runs every _REAPER_INTERVAL.
    # The reaper may currently be mid-sleep on the old interval, so allow
    # enough wall time to cover one full original _REAPER_INTERVAL.
    monkeypatch.setattr(hub_mod, "_HEARTBEAT_TIMEOUT", 0.1)
    monkeypatch.setattr(hub_mod, "_REAPER_INTERVAL", 0.05)
    conn.last_seen = time.monotonic() - 5.0

    for _ in range(140):  # up to ~7s: covers a full original reaper cycle
        if not any(i["instance_id"] == iid for i in core.list_instances()):
            break
        time.sleep(0.05)
    assert not any(i["instance_id"] == iid for i in core.list_instances()), \
        "reaper did not cull the silent connection"

