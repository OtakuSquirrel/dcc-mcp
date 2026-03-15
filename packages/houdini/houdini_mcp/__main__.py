"""Entry point: python -m houdini_mcp"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Houdini MCP Server — control Houdini via MCP + RPyC",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="RPyC port to connect to (auto-discovers if omitted)",
    )
    parser.add_argument(
        "--session-id", type=str, default=None,
        help="Session ID for this MCP server instance",
    )

    args = parser.parse_args()

    from houdini_mcp.server import mcp, set_port, set_session_id

    if args.port is not None:
        set_port(args.port)
    if args.session_id is not None:
        set_session_id(args.session_id)

    mcp.run()


if __name__ == "__main__":
    main()
