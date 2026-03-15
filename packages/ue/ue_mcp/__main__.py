"""Entry point: python -m ue_mcp"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="UE MCP Server — control Unreal Engine via MCP + Remote Execution",
    )
    parser.add_argument("--port", type=int, default=None, help="UE Remote Execution port")
    parser.add_argument("--session-id", type=str, default=None, help="Session ID")

    args = parser.parse_args()

    from ue_mcp.server import mcp, set_port, set_session_id

    if args.port is not None:
        set_port(args.port)
    if args.session_id is not None:
        set_session_id(args.session_id)

    mcp.run()


if __name__ == "__main__":
    main()
