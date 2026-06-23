"""stdio MCP entrypoint (§11) for local agents (Claude Desktop, Cursor).

The credential is read from BRAIN_MCP_TOKEN at launch. Run:
    BRAIN_MCP_TOKEN=agent-token python -m apps.api.mcp.stdio
"""
from __future__ import annotations

import os

import anyio
from mcp.server.stdio import stdio_server

from apps.api.mcp.context import current_credential
from apps.api.mcp.server import build_server
from apps.api.models.db import init_db


async def _run() -> None:
    init_db()
    current_credential.set(os.environ.get("BRAIN_MCP_TOKEN", "agent-token"))
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
