"""Session registry for DCC MCP servers.

Manages session files in ~/{{app_name}}/sessions/ to track active
DCC instances, their ports, PIDs, and status.

Each MCP server instance registers itself on startup and unregisters
on shutdown. The WebUI and other tools can scan the registry to
discover all active sessions.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionRegistry:
    """File-based session registry parameterized by sessions directory.

    Usage:
        registry = SessionRegistry(config.sessions_dir, config.get_port_range)
    """

    def __init__(self, sessions_dir: Path, get_port_range: callable):
        self.sessions_dir = sessions_dir
        self._get_port_range = get_port_range

    def generate_session_id(self) -> str:
        """Generate a short unique session ID."""
        return uuid.uuid4().hex[:12]

    def _session_file(self, session_id: str) -> Path:
        """Path to a session's JSON file."""
        return self.sessions_dir / f"{session_id}.json"

    def register_session(
        self,
        session_id: str,
        port: int,
        pid: int,
        version: str = "",
        mode: str = "gui",
        launched_by: str = "agent",
        dcc_pid: int | None = None,
        client_name: str = "Agent",
    ) -> dict[str, Any]:
        """Register a new session in the registry.

        Args:
            session_id: Unique session identifier.
            port: Port the DCC instance listens on.
            pid: OS process ID of the MCP server process.
            version: DCC version string.
            mode: 'gui' or 'headless'.
            launched_by: 'agent' or 'human'.
            dcc_pid: OS process ID of the DCC instance (if known).
            client_name: Name of the MCP client (e.g. 'Claude Code').

        Returns:
            The session info dict that was written.
        """
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        session_info = {
            "session_id": session_id,
            "port": port,
            "pid": pid,
            "dcc_pid": dcc_pid,
            "version": version,
            "mode": mode,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "launched_by": launched_by,
            "client_name": client_name,
        }

        path = self._session_file(session_id)
        path.write_text(
            json.dumps(session_info, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Registered session %s on port %d (pid %d)", session_id, port, pid)
        return session_info

    def unregister_session(self, session_id: str) -> bool:
        """Remove a session from the registry."""
        path = self._session_file(session_id)
        if path.exists():
            path.unlink()
            logger.info("Unregistered session %s", session_id)
            return True
        return False

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Read a session's info from the registry."""
        path = self._session_file(session_id)
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read session %s: %s", session_id, e)
            return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all registered sessions."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        sessions = []
        for f in self.sessions_dir.glob("*.json"):
            try:
                text = f.read_text(encoding="utf-8")
                info = json.loads(text)
                sessions.append(info)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Skipping malformed session file %s: %s", f.name, e)
        return sessions

    def cleanup_stale_sessions(self) -> list[str]:
        """Remove sessions whose DCC is no longer listening on the registered port."""
        cleaned = []
        for session in self.list_sessions():
            port = session.get("port")
            if port is not None and not is_port_in_use(port):
                session_id = session["session_id"]
                self.unregister_session(session_id)
                cleaned.append(session_id)
                logger.info("Cleaned stale session %s (port %d not listening)", session_id, port)
        return cleaned

    def allocate_port(self) -> int:
        """Find the next available port in the configured range."""
        min_port, max_port = self._get_port_range()
        used_ports = {s["port"] for s in self.list_sessions() if "port" in s}

        for port in range(min_port, max_port + 1):
            if port in used_ports:
                continue
            if not is_port_in_use(port):
                return port

        raise RuntimeError(
            f"No available ports in range {min_port}-{max_port}. "
            f"Run cleanup_stale_sessions() or increase port_range in config."
        )


# ── Standalone utilities (used by registry and other modules) ──


def is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running.

    On Windows uses ctypes OpenProcess (instant) instead of tasklist (slow).
    """
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def is_port_in_use(port: int, timeout: float = 0.15) -> bool:
    """Check if a TCP port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("localhost", port)) == 0
