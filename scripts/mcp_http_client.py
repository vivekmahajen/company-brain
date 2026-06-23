"""Test the deployed MCP server over Streamable HTTP with a real MCP client.

Usage:
    python scripts/mcp_http_client.py https://<your-api>.up.railway.app/mcp agent-token

Lists tools, resolves the refund task, then runs the $200 (executes) and $620
(approval_required) cases — the §1 outcomes — against the live server.
"""
from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _text(result) -> str:
    return result.content[0].text if result.content else ""


async def run(url: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"tools/list ({len(names)}): {names}")

            r = await session.call_tool("resolve", {"task": "angry customer wants their money back"})
            print("resolve:", _text(r))

            under = await session.call_tool(
                "handle-refund__stripe_refund",
                {"order_id": "55", "amount": 200, "idempotency_key": "http-a1"},
            )
            print("under-threshold ($200/#55):", json.loads(_text(under)).get("status"))

            over = await session.call_tool(
                "handle-refund__stripe_refund",
                {"order_id": "1234", "amount": 620, "idempotency_key": "http-b1"},
            )
            print("over-threshold ($620/#1234):", json.loads(_text(over)).get("status"))


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    asyncio.run(run(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
