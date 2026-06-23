"""Per-request credential propagation + tools/list_changed broadcast."""
from __future__ import annotations

import contextvars

# The credential (bearer token) for the in-flight MCP request. stdio sets it from
# env at launch; the HTTP transport sets it per request from the Authorization
# header.
current_credential: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_credential", default=None
)

# Live server sessions, used to push notifications/tools/list_changed.
ACTIVE_SESSIONS: set = set()


async def broadcast_tools_changed() -> int:
    """Notify connected clients to refresh their tool list. Returns #notified."""
    n = 0
    for session in list(ACTIVE_SESSIONS):
        try:
            await session.send_tool_list_changed()
            n += 1
        except Exception:  # noqa: BLE001 - drop dead sessions silently
            ACTIVE_SESSIONS.discard(session)
    return n
