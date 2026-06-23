"""Streamable HTTP MCP transport, mounted into FastAPI at /mcp (§11).

The session manager must run inside the app lifespan; `mcp_run_context()` is
entered from main.py's lifespan. Each request's Authorization header is bound to
the credential contextvar before dispatch.
"""
from __future__ import annotations

import contextlib

from apps.api.mcp.context import current_credential

_manager = None


def _get_manager():
    global _manager
    if _manager is None:
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        from apps.api.mcp.server import build_server

        _manager = StreamableHTTPSessionManager(app=build_server(), json_response=True, stateless=True)
    return _manager


async def _asgi(scope, receive, send):
    if scope["type"] == "http":
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization")
        current_credential.set(auth.decode() if auth else None)
    await _get_manager().handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def mcp_run_context():
    """Run the streamable-HTTP session manager for the app's lifetime."""
    async with _get_manager().run():
        yield


def mount_mcp(app) -> None:
    """Mount the MCP HTTP transport at /mcp on the given FastAPI app."""
    from starlette.routing import Mount

    app.router.routes.append(Mount("/mcp", app=_asgi))
