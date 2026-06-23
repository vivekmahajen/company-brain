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
import traceback


def _text(result) -> str:
    return result.content[0].text if result.content else ""


async def run(url: str, token: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {token}"}
    print(f"[1/5] connecting to {url} ...", flush=True)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            print("[2/5] initializing session ...", flush=True)
            await session.initialize()

            print("[3/5] listing tools ...", flush=True)
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"      tools/list ({len(names)}): {names}", flush=True)
            if not names:
                print("      ⚠ no tools — the live DB likely isn't seeded "
                      "(run POST /api/pipeline/run) or the token is wrong.", flush=True)

            print("[4/5] resolve('angry customer wants their money back') ...", flush=True)
            r = await session.call_tool("resolve", {"task": "angry customer wants their money back"})
            print("      resolve:", _text(r), flush=True)

            print("[5/5] governed execution ...", flush=True)
            under = await session.call_tool(
                "handle-refund__stripe_refund",
                {"order_id": "55", "amount": 200, "idempotency_key": "http-a1"},
            )
            print("      under-threshold ($200/#55):", json.loads(_text(under)).get("status"), flush=True)

            over = await session.call_tool(
                "handle-refund__stripe_refund",
                {"order_id": "1234", "amount": 620, "idempotency_key": "http-b1"},
            )
            print("      over-threshold ($620/#1234):", json.loads(_text(over)).get("status"), flush=True)
    print("DONE.", flush=True)


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    url, token = sys.argv[1], sys.argv[2]
    try:
        asyncio.run(asyncio.wait_for(run(url, token), timeout=60))
    except asyncio.TimeoutError:
        print("\nERROR: timed out after 60s — the server didn't respond (wrong URL, /mcp not "
              "deployed, or transport not mounted).")
    except Exception as e:  # noqa: BLE001
        print(f"\nERROR: {type(e).__name__}: {e}\n")
        traceback.print_exc()


if __name__ == "__main__":
    main()
