"""Registration hub — the daemon side of the reversed DCC connection.

DCCs dial the daemon and register (see
``plugins/common/dcc_socket_server.py``); this hub accepts those
connections, keeps a live table keyed by a daemon-assigned
``instance_id``, and pushes request frames down each held connection,
matching replies by request id.

Replaces the old scan-the-port-pool ``InstanceRegistry`` +
``TransportPool``. The daemon no longer initiates DCC connections and no
longer scans ports; liveness is simply "is the socket still here."

Threading: one reader thread per DCC connection drains replies and
resolves the waiting request's Event. ``send`` is synchronous to the
caller (blocks until the reply frame arrives or the connection drops),
which matches the daemon's request/response tools.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_RECV_SIZE = 1024 * 1024
_DEFAULT_TIMEOUT = 600.0  # execute_python can be long (renders, sims)

# Reaper: DCCs send an application-level heartbeat every few seconds (see
# plugins/common/dcc_socket_server.py). A connection that goes silent for
# longer than this is treated as half-open (TCP dead with no FIN/RST) and
# closed, which unregisters the stale instance. Must comfortably exceed
# the DCC heartbeat interval so a single missed beat doesn't reap a live
# DCC, yet be short enough that a truly dead link clears quickly.
_HEARTBEAT_TIMEOUT = 20.0
_REAPER_INTERVAL = 5.0


class HubError(RuntimeError):
    """The DCC ran the command but it raised inside the DCC process."""

    def __init__(self, message: str, traceback: str | None = None):
        super().__init__(message)
        self.traceback = traceback


@dataclass
class Registration:
    """One live DCC connection + its self-reported identity."""

    instance_id: str
    kind: str
    pid: int | None
    version: str
    file: str
    _conn: "_Connection" = field(repr=False, default=None)  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "kind": self.kind,
            "pid": self.pid,
            "version": self.version,
            "file": self.file,
            "connected": self._conn is not None and self._conn.alive,
        }


class _Connection:
    """Wraps one DCC socket: register handshake, request multiplexing."""

    def __init__(self, sock: socket.socket, hub: "RegistrationHub"):
        self._sock = sock
        self._hub = hub
        self.alive = True
        self._send_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, tuple[threading.Event, dict]] = {}
        self._pending_lock = threading.Lock()
        self.instance_id: str | None = None
        # Updated on every frame received; the reaper closes connections
        # that go silent past the heartbeat timeout (half-open detection).
        self.last_seen = time.monotonic()

    # ── lifecycle ──

    def serve(self) -> None:
        """Read the register frame, then drain replies until the socket
        closes. Runs in its own thread (one per DCC)."""
        buffer = b""
        try:
            # First frame must be the registration.
            while b"\n" not in buffer:
                chunk = self._sock.recv(_RECV_SIZE)
                if not chunk:
                    return
                self.last_seen = time.monotonic()
                buffer += chunk
            line, buffer = buffer.split(b"\n", 1)
            reg = json.loads(line.decode("utf-8"))
            if reg.get("type") != "register":
                return
            self.instance_id = self._hub._register(self, reg)
            self._sock.sendall(
                (json.dumps({"type": "registered",
                             "instance_id": self.instance_id}) + "\n").encode("utf-8"))

            # Then: every subsequent frame is a reply to a request we sent
            # (or a heartbeat keepalive). Any received bytes prove liveness.
            while True:
                while b"\n" in buffer:
                    frame_line, buffer = buffer.split(b"\n", 1)
                    if frame_line.strip():
                        self._on_reply(frame_line.decode("utf-8"))
                chunk = self._sock.recv(_RECV_SIZE)
                if not chunk:
                    break
                self.last_seen = time.monotonic()
                logger.debug("[%s] recv returned %d bytes", self.instance_id, len(chunk))
                buffer += chunk
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("connection error for %s: %s", self.instance_id, e)
        finally:
            self.close()

    def close(self) -> None:
        self.alive = False
        try:
            self._sock.close()
        except OSError:
            pass
        # Fail any in-flight requests so callers don't hang.
        with self._pending_lock:
            for ev, box in self._pending.values():
                box["error"] = "connection closed"
                ev.set()
            self._pending.clear()
        if self.instance_id is not None:
            logger.debug("closing connection for %s (idle %.1fs)",
                         self.instance_id, time.monotonic() - self.last_seen)
            self._hub._unregister(self.instance_id)

    def _on_reply(self, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        # Heartbeat keepalive: bump last_seen immediately so the reaper
        # never kills a connection whose heartbeats are arriving but
        # whose recv() hasn't returned a fresh chunk yet.
        if frame.get("type") == "heartbeat":
            self.last_seen = time.monotonic()
            return
        req_id = frame.get("id")
        logger.debug("[%s] reply frame id=%s type=%s", self.instance_id, req_id, frame.get("type", ""))
        with self._pending_lock:
            slot = self._pending.pop(req_id, None)
        if slot is None:
            logger.debug("[%s] no pending request for id=%s", self.instance_id, req_id)
            return
        ev, box = slot
        box["frame"] = frame
        ev.set()

    # ── request/response ──

    def request(self, command: str, params: dict | None = None,
                timeout: float = _DEFAULT_TIMEOUT):
        if not self.alive:
            raise ConnectionError("DCC disconnected")
        with self._send_lock:
            req_id = self._next_id
            self._next_id += 1
        ev = threading.Event()
        box: dict = {}
        with self._pending_lock:
            self._pending[req_id] = (ev, box)
        frame = {"id": req_id, "command": command, "params": params or {}}
        try:
            self._sock.sendall((json.dumps(frame) + "\n").encode("utf-8"))
        except OSError as e:
            with self._pending_lock:
                self._pending.pop(req_id, None)
            raise ConnectionError(f"send failed: {e}") from e

        if not ev.wait(timeout=timeout):
            with self._pending_lock:
                self._pending.pop(req_id, None)
            raise TimeoutError(f"{command} timed out after {timeout}s")

        if "error" in box:  # connection dropped mid-flight
            raise ConnectionError(box["error"])
        reply = box["frame"]
        if "error" in reply:
            # Log at the one choke point every DCC and every command passes
            # through: fastmcp's own logger does not propagate to root, so
            # without this a DCC-side fault leaves no trace in the WebUI's
            # /api/logs. The traceback goes in the message — it is a
            # pre-formatted string from another process, not our exc_info.
            tb = reply.get("traceback")
            logger.warning("%s error from %s: %s%s", command, self.instance_id,
                           reply["error"], f"\n{tb}" if tb else "")
            raise HubError(str(reply["error"]), traceback=tb)
        return reply.get("result")


class RegistrationHub:
    """Accepts DCC registrations and routes requests to them by id."""

    def __init__(self):
        self._server_sock: socket.socket | None = None
        self._running = False
        self._lock = threading.Lock()
        self._by_id: dict[str, Registration] = {}
        self._kind_counters: dict[str, int] = {}
        # Persist (kind, pid) → instance_id so a reconnecting DCC reuses its
        # old id instead of getting a new monotonically-increasing one.
        self._pid_to_id: dict[tuple[str, int], str] = {}

    # ── listener ──

    def start(self, host: str, port: int) -> None:
        if self._running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(16)
        self._server_sock = sock
        self._running = True
        threading.Thread(target=self._accept_loop, name="dcc-register-accept",
                         daemon=True).start()
        threading.Thread(target=self._reaper_loop, name="dcc-register-reaper",
                         daemon=True).start()
        logger.info("registration hub listening on %s:%d", host, port)

    def stop(self) -> None:
        self._running = False
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    def _accept_loop(self) -> None:
        while self._running and self._server_sock is not None:
            try:
                client, _ = self._server_sock.accept()
            except OSError:
                break
            conn = _Connection(client, self)
            threading.Thread(target=conn.serve, name="dcc-conn", daemon=True).start()

    def _reaper_loop(self) -> None:
        """Close connections that stopped sending heartbeats.

        Detects half-open TCP links (dead with no FIN/RST) that recv would
        otherwise block on forever. Closing the socket unblocks the
        connection's serve() loop, which unregisters the stale instance.
        """
        while self._running:
            time.sleep(_REAPER_INTERVAL)
            now = time.monotonic()
            with self._lock:
                stale = [
                    r._conn for r in self._by_id.values()
                    if r._conn is not None and r._conn.alive
                    and now - r._conn.last_seen > _HEARTBEAT_TIMEOUT
                ]
            for conn in stale:
                logger.warning(
                    "reaping %s: no heartbeat for %.0fs (half-open?)",
                    conn.instance_id, now - conn.last_seen)
                conn.close()

    # ── registry (called by _Connection) ──

    def _register(self, conn: _Connection, reg: dict) -> str:
        kind = str(reg.get("kind", "dcc"))
        pid = reg.get("pid")
        with self._lock:
            # --- same-PID reconnection: reuse the old instance_id ---
            if pid is not None:
                key = (kind, pid)
                reused_id = self._pid_to_id.get(key)
                if reused_id is not None:
                    # If there is still a live (stale) registration for this
                    # id, disconnect it cleanly before replacing.
                    stale = self._by_id.pop(reused_id, None)
                    if stale is not None and stale._conn is not None:
                        stale._conn.alive = False
                        try:
                            stale._conn._sock.close()
                        except OSError:
                            pass
                    conn.instance_id = reused_id
                    self._by_id[reused_id] = Registration(
                        instance_id=reused_id,
                        kind=kind,
                        pid=pid,
                        version=str(reg.get("version", "")),
                        file=str(reg.get("file", "")),
                        _conn=conn,
                    )
                    logger.info("reconnected %s (pid=%s, %s) — reused instance_id",
                                reused_id, pid, reg.get("version"))
                    return reused_id

            # --- first-time registration ---
            n = self._kind_counters.get(kind, 0) + 1
            self._kind_counters[kind] = n
            instance_id = f"{kind}-{n}"
            self._by_id[instance_id] = Registration(
                instance_id=instance_id,
                kind=kind,
                pid=pid,
                version=str(reg.get("version", "")),
                file=str(reg.get("file", "")),
                _conn=conn,
            )
            if pid is not None:
                self._pid_to_id[(kind, pid)] = instance_id
        logger.info("registered %s (pid=%s, %s)", instance_id, reg.get("pid"),
                    reg.get("version"))
        return instance_id

    def _unregister(self, instance_id: str) -> None:
        with self._lock:
            self._by_id.pop(instance_id, None)
        logger.info("unregistered %s", instance_id)

    # ── public API (used by DaemonCore) ──

    def list(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._by_id.values()]

    def get(self, instance_id: str) -> Registration | None:
        with self._lock:
            return self._by_id.get(instance_id)

    def request(self, instance_id: str, command: str, params: dict | None = None,
                timeout: float = _DEFAULT_TIMEOUT):
        reg = self.get(instance_id)
        if reg is None or reg._conn is None or not reg._conn.alive:
            raise KeyError(f"no live instance: {instance_id}")
        return reg._conn.request(command, params, timeout=timeout)
