"""FastAPI app: REST surface + mounted MCP Streamable HTTP transport."""
from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.models.db import init_db
from apps.api.routers import approvals, billing, brain, connections, oauth, orgs, security, templates

logger = logging.getLogger("company_brain")


class TenantMiddleware:
    """Pure-ASGI middleware that resolves the request's tenant (org) and binds it
    to a contextvar for the lifetime of the request. Pure-ASGI (not BaseHTTPMiddleware)
    so the contextvar reliably reaches the endpoint. Fails closed in strict mode."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        from apps.api.auth.tenant import current_org_id, resolve_org_id
        from apps.api.models.db import SessionLocal

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        db = SessionLocal()
        try:
            org_id, _how, ok = resolve_org_id(
                db,
                authorization=headers.get("authorization"),
                x_org_id=headers.get("x-org-id"),
                path=scope.get("path", ""),
            )
        finally:
            db.close()

        if not ok:
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body",
                        "body": b'{"error":"tenant unresolved: send a valid token or X-Org-Id"}'})
            return

        token = current_org_id.set(org_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_org_id.reset(token)


def _seed_if_empty() -> None:
    settings = get_settings()
    if not settings.seed_on_startup:
        return
    from sqlalchemy import select

    from apps.api.models.db import SessionLocal
    from apps.api.models.tables import Skill
    from apps.api.services.pipeline import run_full_pipeline

    db = SessionLocal()
    try:
        if not db.scalar(select(Skill).where(Skill.org_id == settings.default_org_id)):
            from apps.api.services.serving import approve_demo_skills

            report = run_full_pipeline(db, settings.default_org_id)
            approve_demo_skills(db, settings.default_org_id)  # make demo skills servable
            logger.info("Seeded brain on startup: %s", report.get("skills"))
    except Exception:  # noqa: BLE001 - never block boot on seeding
        logger.exception("startup seed failed")
    finally:
        db.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_if_empty()
    # Run the MCP Streamable HTTP session manager for the app lifetime, if mounted.
    try:
        from apps.api.mcp.http import mcp_run_context

        async with mcp_run_context():
            yield
    except Exception as e:  # noqa: BLE001 - app must serve REST even if MCP fails
        logger.warning("MCP HTTP transport unavailable: %s", e)
        yield


app = FastAPI(title="Company Brain API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Tenant resolution wraps the routers so every endpoint sees the resolved org.
# It's added last (→ outermost), so it runs first; CORS preflight (OPTIONS) is
# passed straight through inside the middleware so cross-origin still works.
app.add_middleware(TenantMiddleware)
app.include_router(orgs.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(brain.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")

# Mount the MCP Streamable HTTP transport at /mcp (§11).
try:
    from apps.api.mcp.http import mount_mcp

    mount_mcp(app)
except Exception as _mcp_err:  # noqa: BLE001 - MCP transport optional
    logger.warning("MCP HTTP transport not mounted: %s", _mcp_err)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
