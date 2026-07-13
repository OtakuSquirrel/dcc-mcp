"""dcc-daemon — unified local entry point for agent → DCC control.

A single long-lived process that:
  * exposes four meta-tools to local agents over MCP-over-HTTP,
  * routes every request down to a DCC instance via ONE channel:
    ``execute_python(instance_id, code)`` over newline-delimited TCP+JSON.

The daemon assigns each registered DCC an ``instance_id``; callers never
address DCC-specific ports or transports.
All DCC domain knowledge lives in Skills, not in tool schemas.
"""

__version__ = "0.1.0"
