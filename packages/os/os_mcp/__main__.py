"""Entry point: os-mcp CLI.

os-mcp is a stateless MCP server — no --port, no --session-id. Every tool
call is a self-contained OS query (process info, health check, screenshot,
clipboard). Designed to run alongside DCC-specific MCP servers as a
diagnostic and recovery sibling.
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="os-mcp — OS-level MCP tools for DCC process management",
    )
    parser.parse_args()

    from os_mcp.server import mcp
    mcp.run()


if __name__ == "__main__":
    main()
