"""Entry point: blender-mcp CLI.

Stateless — no --port (Claude passes port per tool call) and no
--session-id (no session concept in the new architecture).
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Blender MCP Server — control Blender via MCP + TCP/JSON",
    )
    parser.parse_args()

    from blender_mcp.server import mcp
    mcp.run()


if __name__ == "__main__":
    main()
