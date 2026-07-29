"""Entry point: `dcc-mcp`.

Starts the long-lived local daemon. By default it serves MCP over HTTP
on 127.0.0.1 (local agents connect with {"type":"http", "url":...}) plus
the monitoring WebUI. DCC applications connect to its registration port
and are addressed by ``instance_id``.
"""

from __future__ import annotations

import argparse
import logging

from dcc_mcp import config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="dcc-mcp — unified local entry point for agent → DCC control",
    )
    default_host, default_port = config.http_bind()
    default_register_host, default_register_port = config.register_bind()
    parser.add_argument("--host", default=default_host,
                        help=f"HTTP bind host (default {default_host})")
    parser.add_argument("--port", type=int, default=default_port,
                        help=f"HTTP bind port (default {default_port})")
    parser.add_argument("--path", default="/mcp",
                        help="MCP HTTP path (default /mcp)")
    parser.add_argument("--register-port", type=int, default=default_register_port,
                        help=f"DCC registration port (default {default_register_port})")
    parser.add_argument("--no-webui", action="store_true",
                        help="Serve MCP only; disable the monitoring dashboard")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())
    log = logging.getLogger(__name__)

    # Import late so --help stays fast and import errors surface clearly.
    import uvicorn

    from dcc_mcp.app import build_app

    app = build_app(
        mcp_path=args.path,
        webui=not args.no_webui,
        registration_bind=(default_register_host, args.register_port),
    )

    log.info("dcc-mcp: MCP at http://%s:%d%s", args.host, args.port, args.path)
    if not args.no_webui:
        log.info("dcc-mcp: dashboard at http://%s:%d/", args.host, args.port)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        http="h11",
    )


if __name__ == "__main__":
    main()
