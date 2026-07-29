"""Read-only local daemon diagnostics for the WebUI."""

from __future__ import annotations

import os
import time

from dcc_mcp import __version__, config

_STARTED_AT = time.monotonic()


def snapshot(instances: list[dict], *, mcp_path: str = "/mcp") -> dict:
    http_host, http_port = config.http_bind()
    register_host, register_port = config.register_bind()
    return {
        "daemon": {
            "version": __version__,
            "pid": os.getpid(),
            "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
            "config_path": str(config.config_path()),
        },
        "services": {
            "mcp": {
                "status": "listening",
                "address": f"http://{http_host}:{http_port}{mcp_path}",
            },
            "dashboard": {
                "status": "listening",
                "address": f"http://{http_host}:{http_port}/",
            },
            "registration": {
                "status": "listening",
                "address": f"{register_host}:{register_port}",
            },
        },
        "mcp_tools": ["list_instances", "execute_python", "health", "screenshot"],
        "instances": instances,
        "summary": {
            "registered_instances": len(instances),
            "connected_instances": sum(bool(item.get("connected")) for item in instances),
        },
    }
