"""Relay server — the public rendezvous between cloud agents and home
daemons. Deployed on a host with a public address; both sides dial IN to
it over WSS.

The relay executes nothing. For each ``daemon_id`` it keeps at most one
connected daemon and any number of agents; it forwards agent→daemon
request frames and daemon→agent response frames verbatim, routing
responses back to the right agent by a relay-assigned connection tag it
adds to the frame ``id``.

Security surface: a daemon must present a valid ``pair_token``; an agent
a valid ``access_token`` for that ``daemon_id`` (see :class:`TokenStore`).
Everything rides WSS (TLS terminated by the deploying reverse proxy, or
pass an ssl context to :func:`serve`).
"""

from __future__ import annotations

import asyncio
import logging

import websockets
from websockets.asyncio.server import ServerConnection, serve as ws_serve

from dcc_daemon.tunnel import protocol as p
from dcc_daemon.tunnel.tokens import TokenStore

logger = logging.getLogger(__name__)


class _Room:
    """State for one daemon_id: its daemon socket + attached agents."""

    def __init__(self):
        self.daemon: ServerConnection | None = None
        self.agents: dict[int, ServerConnection] = {}
        self._next_agent_tag = 1

    def add_agent(self, ws: ServerConnection) -> int:
        tag = self._next_agent_tag
        self._next_agent_tag += 1
        self.agents[tag] = ws
        return tag


class Relay:
    def __init__(self, tokens: TokenStore):
        self._tokens = tokens
        self._rooms: dict[str, _Room] = {}

    def _room(self, daemon_id: str) -> _Room:
        return self._rooms.setdefault(daemon_id, _Room())

    async def handle(self, ws: ServerConnection) -> None:
        try:
            hello = p.decode(await ws.recv())
        except (ValueError, websockets.ConnectionClosed):
            await self._reject(ws, "bad handshake")
            return

        role = hello.get("role")
        daemon_id = str(hello.get("daemon_id", ""))
        token = str(hello.get("token", ""))

        if role == p.ROLE_DAEMON:
            if not self._tokens.check_daemon(daemon_id, token):
                await self._reject(ws, "daemon auth failed")
                return
            await self._run_daemon(daemon_id, ws)
        elif role == p.ROLE_AGENT:
            if not self._tokens.check_agent(daemon_id, token):
                await self._reject(ws, "agent auth failed")
                return
            await self._run_agent(daemon_id, ws)
        else:
            await self._reject(ws, "unknown role")

    async def _reject(self, ws: ServerConnection, why: str) -> None:
        try:
            await ws.send(p.encode({"ok": False, "error": why}))
            await ws.close()
        except websockets.ConnectionClosed:
            pass
        logger.info("relay rejected connection: %s", why)

    async def _accept(self, ws: ServerConnection) -> None:
        await ws.send(p.encode({"ok": True}))

    # ── daemon side ──

    async def _run_daemon(self, daemon_id: str, ws: ServerConnection) -> None:
        room = self._room(daemon_id)
        if room.daemon is not None:
            await self._reject(ws, "daemon already connected")
            return
        room.daemon = ws
        await self._accept(ws)
        logger.info("daemon connected: %s", daemon_id)
        try:
            async for raw in ws:
                await self._daemon_to_agent(room, raw)
        except websockets.ConnectionClosed:
            pass
        finally:
            room.daemon = None
            logger.info("daemon disconnected: %s", daemon_id)

    async def _daemon_to_agent(self, room: _Room, raw) -> None:
        """Route a daemon response back to the agent named in the tag.

        The daemon echoes the tagged id we injected; we split it back into
        (agent_tag, original_id) and forward to that agent only.
        """
        try:
            frame = p.decode(raw)
        except ValueError:
            return
        tagged = frame.get("id")
        if not isinstance(tagged, str) or ":" not in tagged:
            return
        tag_str, _, orig = tagged.partition(":")
        try:
            tag = int(tag_str)
        except ValueError:
            return
        agent = room.agents.get(tag)
        if agent is None:
            return
        frame["id"] = int(orig) if orig.isdigit() else orig
        try:
            await agent.send(p.encode(frame))
        except websockets.ConnectionClosed:
            pass

    # ── agent side ──

    async def _run_agent(self, daemon_id: str, ws: ServerConnection) -> None:
        room = self._room(daemon_id)
        tag = room.add_agent(ws)
        await self._accept(ws)
        logger.info("agent %d attached to %s", tag, daemon_id)
        try:
            async for raw in ws:
                await self._agent_to_daemon(room, tag, raw)
        except websockets.ConnectionClosed:
            pass
        finally:
            room.agents.pop(tag, None)
            logger.info("agent %d detached from %s", tag, daemon_id)

    async def _agent_to_daemon(self, room: _Room, tag: int, raw) -> None:
        """Forward an agent request to the daemon, tagging the id so the
        response can be routed back to this agent."""
        try:
            frame = p.decode(raw)
        except ValueError:
            return
        if room.daemon is None:
            try:
                await room.agents[tag].send(
                    p.encode(p.make_error(frame.get("id"), "daemon offline"))
                )
            except (websockets.ConnectionClosed, KeyError):
                pass
            return
        frame["id"] = f"{tag}:{frame.get('id')}"
        try:
            await room.daemon.send(p.encode(frame))
        except websockets.ConnectionClosed:
            pass


async def serve(tokens: TokenStore, host: str = "0.0.0.0", port: int = 12099,
                ssl=None) -> None:
    """Run the relay until cancelled."""
    relay = Relay(tokens)
    async with ws_serve(relay.handle, host, port, ssl=ssl):
        logger.info("relay listening on %s:%d", host, port)
        await asyncio.Future()  # run forever
