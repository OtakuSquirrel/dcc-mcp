"""dcc-daemon — unified local entry point for agent → DCC control.

A single long-lived process that:
  * exposes ~5 meta-tools to local agents over MCP-over-HTTP,
  * (Phase 2) accepts cloud agents over an outbound WebSocket tunnel,
  * routes every request down to a DCC instance via ONE channel:
    ``execute_python(port, code)`` over newline-delimited TCP+JSON.

Design tenet: "端口 + 命令解决一切" — port + command solves everything.
All DCC domain knowledge lives in Skills, not in tool schemas.
"""

__version__ = "0.1.0"
