"""Entry point: python -m dcc_mcp_core.webui [--port PORT]"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="dcc-mcp Dashboard")
    parser.add_argument("--port", type=int, default=8420, help="HTTP port (default: 8420)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    args = parser.parse_args()

    import uvicorn
    print(f"dcc-mcp Dashboard: http://{args.host}:{args.port}")
    uvicorn.run(
        "dcc_mcp_core.webui.app:app",
        host=args.host,
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
