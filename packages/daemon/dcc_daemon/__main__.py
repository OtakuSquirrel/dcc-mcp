"""Entry point: `dcc-daemon`.

Starts the long-lived local daemon. By default it serves MCP over HTTP
on 127.0.0.1 (local agents connect with {"type":"http", "url":...}) plus
the monitoring WebUI. If a relay URL + credentials are given, it also
opens an outbound tunnel so remote agents can reach it (Phase 2).

Local ingress (uvicorn) and the tunnel client share nothing but the
process; each DaemonCore talks to the same DCCs by port.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import threading

from dcc_daemon import config


def _start_tunnel(relay_url: str, daemon_id: str, pair_token: str) -> None:
    """Run the outbound tunnel client in a background thread + loop.

    Uses the SAME DaemonCore (and thus the same registration hub) as the
    local MCP ingress, so remote agents reach the same live DCCs."""
    from dcc_daemon.mcp_server import core
    from dcc_daemon.tunnel.client import TunnelClient

    def _run():
        client = TunnelClient(relay_url, daemon_id, pair_token, core=core)
        asyncio.run(client.run_forever())

    threading.Thread(target=_run, name="dcc-tunnel", daemon=True).start()
    logging.getLogger(__name__).info(
        "dcc-daemon: tunnel dialing %s as %s", relay_url, daemon_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="dcc-daemon — unified local entry point for agent → DCC control",
    )
    default_host, default_port = config.http_bind()
    parser.add_argument("--host", default=default_host,
                        help=f"HTTP bind host (default {default_host})")
    parser.add_argument("--port", type=int, default=default_port,
                        help=f"HTTP bind port (default {default_port})")
    parser.add_argument("--path", default="/mcp",
                        help="MCP HTTP path (default /mcp)")
    parser.add_argument("--no-webui", action="store_true",
                        help="Serve MCP only; disable the monitoring dashboard")
    parser.add_argument("--relay-url", default=os.environ.get("DCC_RELAY_URL"),
                        help="Cloud relay WSS URL; enables the outbound tunnel")
    parser.add_argument("--daemon-id", default=os.environ.get("DCC_DAEMON_ID"),
                        help="This daemon's id registered at the relay")
    parser.add_argument("--pair-token", default=os.environ.get("DCC_PAIR_TOKEN"),
                        help="Secret proving this daemon's identity to the relay")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())
    log = logging.getLogger(__name__)

    # Optional outbound tunnel — only if fully configured.
    if args.relay_url:
        if not (args.daemon_id and args.pair_token):
            parser.error("--relay-url requires --daemon-id and --pair-token")
        _start_tunnel(args.relay_url, args.daemon_id, args.pair_token)

    # Import late so --help stays fast and import errors surface clearly.
    import uvicorn

    from dcc_daemon.app import build_app

    app = build_app(mcp_path=args.path, webui=not args.no_webui)

    log.info("dcc-daemon: MCP at http://%s:%d%s", args.host, args.port, args.path)
    if not args.no_webui:
        log.info("dcc-daemon: dashboard at http://%s:%d/", args.host, args.port)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        http="h11",
    )


if __name__ == "__main__":
    main()
