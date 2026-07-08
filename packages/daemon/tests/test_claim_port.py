"""Tests for the shared socket server's port-claiming behavior.

``claim_and_start`` is how a DCC plugin picks its port at launch: scan
the pool, bind the first free one. These verify it skips a port already
held by another instance and errors when the whole pool is taken.
"""

from __future__ import annotations

import socket

import pytest

from dcc_socket_server import DCCServer, default_info


def _server(kind: str = "blender") -> DCCServer:
    return DCCServer(
        kind=kind,
        run_on_main=lambda fn: fn(),  # inline; no real DCC main thread here
        get_info=lambda: default_info(kind, "1.0"),
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_claims_first_free_port():
    p1, p2 = _free_port(), _free_port()
    srv = _server()
    try:
        claimed = srv.claim_and_start([p1, p2])
        assert claimed == p1
        assert srv.port == p1
    finally:
        srv.stop()


def test_skips_taken_port():
    taken = _free_port()
    nxt = _free_port()
    # Hold `taken` so the server must move to `nxt`.
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", taken))
    holder.listen(1)
    srv = _server()
    try:
        claimed = srv.claim_and_start([taken, nxt])
        assert claimed == nxt
    finally:
        srv.stop()
        holder.close()


def test_raises_when_pool_exhausted():
    taken = _free_port()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", taken))
    holder.listen(1)
    srv = _server()
    try:
        with pytest.raises(RuntimeError):
            srv.claim_and_start([taken])
    finally:
        srv.stop()
        holder.close()


def test_read_dcc_ports_defaults(monkeypatch, tmp_path):
    # Point HOME at an empty dir → no config → defaults.
    import dcc_socket_server as m
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ports = m.read_dcc_ports()
    assert ports == list(range(18811, 18831))
