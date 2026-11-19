"""Copyable client configurations for the daemon's HTTP MCP endpoint."""

from __future__ import annotations

import json


def integration_examples(endpoint: str, origin: str) -> dict:
    """Keep transport differences explicit; all examples use the live address."""
    http_server = {"type": "http", "url": endpoint}

    def config(root: str, server: dict) -> str:
        return json.dumps({root: {"dcc": server}}, ensure_ascii=False, indent=2)

    return {
        "endpoint": endpoint,
        "clients": [
            {
                "id": "claude-code",
                "name": "Claude Code",
                "path": "<项目目录>/.mcp.json",
                "note": "合并到 mcpServers；重新连接后，在 /mcp 中查看 dcc。",
                "language": "JSON",
                "code": config("mcpServers", http_server),
                "docs": "https://code.claude.com/docs/en/mcp",
            },
            {
                "id": "codex",
                "name": "Codex",
                "path": "~/.codex/config.toml",
                "note": "追加此 TOML 配置段；已有 mcp_servers.dcc 时修改原配置段。",
                "language": "TOML",
                "code": f'[mcp_servers.dcc]\nurl = {json.dumps(endpoint)}\n',
                "docs": "https://developers.openai.com/codex/mcp/",
            },
            {
                "id": "cursor",
                "name": "Cursor",
                "path": "<项目目录>/.cursor/mcp.json",
                "note": "全局配置也可放在 ~/.cursor/mcp.json；保存后在 MCP 设置中启用 dcc。",
                "language": "JSON",
                "code": config("mcpServers", {"url": endpoint}),
                "docs": "https://cursor.com/docs/context/mcp",
            },
            {
                "id": "vscode",
                "name": "VS Code / Copilot（Local）",
                "path": "<项目目录>/.vscode/mcp.json",
                "note": "适用于 Local 配置，根键为 servers。使用 Copilot harness 时，通过 MCP: Add Server 添加 HTTP 地址。",
                "language": "JSON",
                "code": config("servers", http_server),
                "docs": "https://code.visualstudio.com/docs/agents/reference/mcp-configuration",
            },
            {
                "id": "codebuddy",
                "name": "CodeBuddy CLI",
                "path": "<项目目录>/.mcp.json",
                "note": "用户级配置可放在 ~/.codebuddy/.mcp.json；合并到 mcpServers。",
                "language": "JSON",
                "code": config("mcpServers", http_server),
                "docs": "https://www.codebuddy.ai/docs/cli/mcp",
            },
        ],
        "api": [
            {
                "id": "python",
                "name": "Python / MCP SDK",
                "path": "connect_dcc.py",
                "note": "安装依赖：pip install fastmcp。通过 MCP 会话调用工具。",
                "language": "Python",
                "code": (
                    "import asyncio\n"
                    "from fastmcp import Client\n\n"
                    "async def main():\n"
                    f"    async with Client({json.dumps(endpoint)}) as client:\n"
                    '        result = await client.call_tool("list_instances", {})\n'
                    "        print(result)\n\n"
                    "asyncio.run(main())\n"
                ),
            },
            {
                "id": "http",
                "name": "HTTP API",
                "path": "Terminal / PowerShell",
                "note": "这些 GET 接口用于读取监控数据；执行 DCC 代码需通过 MCP 的 execute_python 工具。Windows 可将 curl 换成 curl.exe。",
                "language": "Shell",
                "code": "\n".join(
                    f'curl "{origin}{path}"'
                    for path in ("/api/instances", "/api/tools", "/api/diagnostics")
                ),
            },
        ],
    }
