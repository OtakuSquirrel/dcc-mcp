"""Entry point: python -m blender_mcp

Supports CLI arguments:
  --port PORT        Blender addon socket port (auto-discovers if omitted)
  --session-id ID    Session ID for this MCP server instance
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Blender MCP Server — control Blender via MCP + TCP/JSON",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Blender addon socket port (auto-discovers if omitted)",
    )
    parser.add_argument(
        "--session-id", type=str, default=None,
        help="Session ID for this MCP server instance",
    )

    args = parser.parse_args()

    from blender_mcp.server import mcp, set_port, set_session_id

    if args.port is not None:
        set_port(args.port)

    if args.session_id is not None:
        set_session_id(args.session_id)

    mcp.run()


if __name__ == "__main__":
    main()
