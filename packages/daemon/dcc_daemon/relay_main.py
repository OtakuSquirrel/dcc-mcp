"""Entry point: `dcc-relay` — run the public relay, or provision tokens.

Deploy on a host with a public address (put a TLS-terminating proxy in
front, or point --certfile/--keyfile at real certs). The relay itself
executes nothing; it only pairs authenticated daemons and agents.

    dcc-relay serve --tokens tokens.json --port 8787
    dcc-relay add-daemon --tokens tokens.json            # -> daemon_id + pair_token
    dcc-relay add-agent  --tokens tokens.json --daemon-id dccbox-...  # -> access_token
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import ssl
from pathlib import Path

from dcc_daemon.tunnel.relay import serve
from dcc_daemon.tunnel.tokens import TokenStore


def main() -> None:
    parser = argparse.ArgumentParser(description="dcc-relay — rendezvous for the daemon tunnel")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("serve", help="run the relay server")
    ps.add_argument("--tokens", type=Path, required=True, help="token store JSON path")
    ps.add_argument("--host", default="0.0.0.0")
    ps.add_argument("--port", type=int, default=8787)
    ps.add_argument("--certfile", help="TLS cert (enables wss:// directly)")
    ps.add_argument("--keyfile", help="TLS key")
    ps.add_argument("--log-level", default="INFO")

    pd = sub.add_parser("add-daemon", help="register a daemon; prints id + pair_token")
    pd.add_argument("--tokens", type=Path, required=True)
    pd.add_argument("--daemon-id", default=None)

    pa = sub.add_parser("add-agent", help="issue an access token for a daemon")
    pa.add_argument("--tokens", type=Path, required=True)
    pa.add_argument("--daemon-id", required=True)

    args = parser.parse_args()

    if args.cmd == "serve":
        logging.basicConfig(level=args.log_level.upper())
        ssl_ctx = None
        if args.certfile and args.keyfile:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(args.certfile, args.keyfile)
        store = TokenStore(args.tokens)
        asyncio.run(serve(store, host=args.host, port=args.port, ssl=ssl_ctx))
    elif args.cmd == "add-daemon":
        store = TokenStore(args.tokens)
        daemon_id, pair_token = store.register_daemon(args.daemon_id)
        print(f"daemon_id  = {daemon_id}")
        print(f"pair_token = {pair_token}")
    elif args.cmd == "add-agent":
        store = TokenStore(args.tokens)
        token = store.issue_access_token(args.daemon_id)
        print(f"access_token = {token}")


if __name__ == "__main__":
    main()
