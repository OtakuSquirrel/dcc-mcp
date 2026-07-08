"""End-to-end tunnel test — relay + daemon client + fake DCC + agent.

Runs the real relay and real daemon-side TunnelClient in-process over a
loopback WebSocket, with a fake DCC (the shared DCCServer) behind the
daemon. Verifies:
  * token auth (daemon accepted, agent accepted, bad tokens rejected),
  * a full agent → relay → daemon → DCC → back round-trip,
  * DCC error propagation across the tunnel,
  * request routing by id.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time

import pytest
import websockets

from dcc_socket_server import DCCServer, default_info
from dcc_daemon.core import DaemonCore
from dcc_daemon.tunnel import protocol as p
from dcc_daemon.tunnel.client import TunnelClient
from dcc_daemon.tunnel.relay import Relay
from dcc_daemon.tunnel.tokens import TokenStore

_DCC_PORT = 18815  # within the default pool so discovery scans it
_DAEMON_ID = "dccbox-test"


@pytest.fixture
def fake_dcc(monkeypatch):
    # Pin the scanned pool to this port so list_instances is deterministic
    # regardless of the machine's ~/.dcc-mcp/config.toml.
    monkeypatch.setattr("dcc_daemon.registry.config.dcc_ports", lambda: [_DCC_PORT])
    jobs: "queue.Queue[tuple]" = queue.Queue()
    stop = threading.Event()

    def run_on_main(fn):
        box: dict = {}
        ev = threading.Event()
        jobs.put((fn, box, ev))
        ev.wait(timeout=10)
        if "err" in box:
            raise box["err"]
        return box["res"]

    def loop():
        while not stop.is_set():
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

    threading.Thread(target=loop, daemon=True).start()
    server = DCCServer(
        kind="blender",
        run_on_main=run_on_main,
        get_info=lambda: default_info("blender", "4.2.0", "scene.blend"),
        exec_globals=lambda: {"STATE": {"n": 41}},
    )
    server.start(_DCC_PORT)
    time.sleep(0.2)
    yield
    server.stop()
    stop.set()


async def _agent_call(url, access_token, method, params, req_id=1):
    """Connect as an agent, do one request, return the response frame."""
    async with websockets.connect(url) as ws:
        await ws.send(p.encode(p.make_hello(p.ROLE_AGENT, _DAEMON_ID, access_token)))
        ack = p.decode(await ws.recv())
        if not ack.get("ok"):
            return {"_rejected": ack.get("error")}
        await ws.send(p.encode(p.make_request(req_id, method, params)))
        return p.decode(await ws.recv())


async def _run_scenario():
    # Provision tokens in-memory.
    store = TokenStore(data={"daemons": {}})
    _, pair_token = store.register_daemon(_DAEMON_ID)
    access_token = store.issue_access_token(_DAEMON_ID)

    # Start the relay on an ephemeral loopback port.
    relay = Relay(store)
    server = await websockets.serve(relay.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    # Start the daemon-side tunnel client.
    tc = TunnelClient(url, _DAEMON_ID, pair_token, core=DaemonCore())
    tc_task = asyncio.create_task(tc.run_forever())
    await asyncio.sleep(0.4)  # let the daemon register

    results = {}
    try:
        results["exec"] = await _agent_call(
            url, access_token, "execute_python",
            {"port": _DCC_PORT, "code": "result = STATE['n'] + 1"})
        results["list"] = await _agent_call(
            url, access_token, "list_instances", {"refresh": True}, req_id=2)
        results["err"] = await _agent_call(
            url, access_token, "execute_python",
            {"port": _DCC_PORT, "code": "raise ValueError('boom')"}, req_id=3)
        results["badtoken"] = await _agent_call(
            url, "wrong-token", "list_instances", {}, req_id=4)
    finally:
        tc_task.cancel()
        try:
            await tc_task
        except asyncio.CancelledError:
            pass
        server.close()
        await server.wait_closed()
    return results


def test_tunnel_end_to_end(fake_dcc):
    r = asyncio.run(_run_scenario())

    # round-trip result
    assert r["exec"]["id"] == 1
    assert r["exec"]["result"] == {"port": _DCC_PORT, "result": 42}

    # list_instances routed back to the right request id
    assert r["list"]["id"] == 2
    assert any(i["port"] == _DCC_PORT for i in r["list"]["result"])

    # DCC error propagated across the tunnel with traceback
    assert r["err"]["id"] == 3
    assert "boom" in r["err"]["error"]
    assert r["err"].get("traceback")

    # bad access token rejected at handshake
    assert r["badtoken"].get("_rejected")


def test_token_store_validation():
    store = TokenStore(data={"daemons": {}})
    daemon_id, pair = store.register_daemon("dccbox-x")
    access = store.issue_access_token(daemon_id)

    assert store.check_daemon(daemon_id, pair)
    assert not store.check_daemon(daemon_id, "nope")
    assert not store.check_daemon("other", pair)
    assert store.check_agent(daemon_id, access)
    assert not store.check_agent(daemon_id, "nope")
