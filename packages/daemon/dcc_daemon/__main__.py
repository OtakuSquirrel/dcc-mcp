"""Entry point: `dcc-daemon`.

Starts the long-lived local daemon. By default it serves MCP over HTTP
on 127.0.0.1 (local agents connect with {"type":"http", "url":...}).
The optional WebUI and the Phase-2 cloud WebSocket tunnel attach to the
same DaemonCore.
"""

from __future__ import annotations

import argparse
import logging

from dcc_daemon import config


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
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())

    # Import late so --help stays fast and import errors surface clearly.
    import uvicorn

    from dcc_daemon.app import build_app

    app = build_app(mcp_path=args.path, webui=not args.no_webui)

    log = logging.getLogger(__name__)
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
