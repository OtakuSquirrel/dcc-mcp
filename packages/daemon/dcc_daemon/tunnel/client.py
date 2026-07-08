"""Daemon-side tunnel client — dials OUT to the relay and serves requests.

This is what makes remote access work without opening a port at home:
the daemon initiates the connection to the relay (outbound WSS, allowed
through NAT/firewalls like any web request), authenticates with its
``pair_token``, then answers request frames by dispatching them to the
local :class:`DaemonCore` — the same core the local MCP tools use.

Reconnects with backoff if the relay or network drops. Runs blocking
DCC calls in a thread so the event loop keeps serving other frames.
"""

from __future__ import annotations

import asyncio
import logging
import traceback

import websockets

from dcc_daemon.core import DaemonCore, DCCError
from dcc_daemon.tunnel import protocol as p

logger = logging.getLogger(__name__)

_BACKOFF_START = 1.0
_BACKOFF_MAX = 30.0


class TunnelClient:
    def __init__(self, relay_url: str, daemon_id: str, pair_token: str,
                 core: DaemonCore | None = None):
        self._url = relay_url
        self._daemon_id = daemon_id
        self._token = pair_token
        self._core = core or DaemonCore()

    async def run_forever(self) -> None:
        """Connect, serve, and reconnect with backoff until cancelled."""
        backoff = _BACKOFF_START
        while True:
            try:
                await self._session()
                backoff = _BACKOFF_START  # clean exit → reset
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — keep the daemon alive
                logger.warning("tunnel session ended (%s); retrying in %.0fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _session(self) -> None:
        async with websockets.connect(self._url) as ws:
            await ws.send(p.encode(p.make_hello(p.ROLE_DAEMON, self._daemon_id, self._token)))
            ack = p.decode(await ws.recv())
            if not ack.get("ok"):
                raise RuntimeError(f"relay refused daemon: {ack.get('error')}")
            logger.info("tunnel up: %s via %s", self._daemon_id, self._url)
            async for raw in ws:
                # Serve each request without blocking the read loop.
                asyncio.create_task(self._handle(ws, raw))

    async def _handle(self, ws, raw) -> None:
        try:
            frame = p.decode(raw)
        except ValueError:
            return
        req_id = frame.get("id")
        method = frame.get("method")
        params = frame.get("params") or {}
        if method not in p.METHODS:
            await self._send(ws, p.make_error(req_id, f"unknown method: {method}"))
            return
        try:
            result = await asyncio.to_thread(self._dispatch, method, params)
            await self._send(ws, p.make_result(req_id, result))
        except DCCError as e:
            await self._send(ws, p.make_error(req_id, str(e), traceback=e.traceback))
        except Exception as e:  # noqa: BLE001
            await self._send(ws, p.make_error(req_id, f"{type(e).__name__}: {e}",
                                              traceback=traceback.format_exc()))

    def _dispatch(self, method: str, params: dict):
        if method == "list_instances":
            return self._core.list_instances(refresh=bool(params.get("refresh", False)))
        if method == "execute_python":
            return self._core.execute_python(str(params["instance_id"]), str(params["code"]))
        if method == "health":
            return self._core.health(str(params["instance_id"]))
        if method == "screenshot":
            return self._core.screenshot(str(params["instance_id"]))
        raise ValueError(f"unhandled method: {method}")

    async def _send(self, ws, frame: dict) -> None:
        try:
            await ws.send(p.encode(frame))
        except websockets.ConnectionClosed:
            pass
