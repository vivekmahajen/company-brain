"""FastAPI app: REST surface + mounted MCP Streamable HTTP transport."""
from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.models.db import init_db
from apps.api.routers import (
    approvals,
    billing,
    brain,
    connections,
    gtm,
    oauth,
    orgs,
    security,
    templates,
)

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


class RateLimitMiddleware:
    """Per-credential (or IP) fixed-window rate limit. Disabled unless
    RATE_LIMIT_PER_MIN > 0. Health/metrics paths are exempt."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        limit = get_settings().rate_limit_per_min
        if limit <= 0 or path.startswith("/health") or path == "/api/metrics":
            await self.app(scope, receive, send)
            return
        from apps.api.reliability.ratelimit import limiter

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        key = headers.get("authorization") or (scope.get("client") or ["?"])[0]
        ok, retry = limiter().allow(key, limit)
        if not ok:
            body = b'{"error":"rate_limited"}'
            await send({"type": "http.response.start", "status": 429,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"retry-after", str(retry).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


class ObservabilityMiddleware:
    """Assigns a request id, times the request, records metrics, and tags the
    response with X-Request-ID. Errors are counted (and re-raised for the handler)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import time
        import uuid

        from apps.api.reliability.metrics import metrics

        rid = uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = rid
        route = f"{scope.get('method', 'GET')} {scope.get('path', '')}"
        status_box = {"code": 500}
        t0 = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_box["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            metrics().record(route, 500, (time.perf_counter() - t0) * 1000)
            raise
        metrics().record(route, status_box["code"], (time.perf_counter() - t0) * 1000)


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
# Middleware stack (add order = innermost→outermost). Final run order:
# Observability → RateLimit → Tenant → CORS → routers.
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ObservabilityMiddleware)


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # noqa: ANN001 - structured 500, no stack trace leak
    from fastapi.responses import JSONResponse

    rid = getattr(request, "scope", {}).get("state", {}).get("request_id")
    logger.exception("unhandled error (request_id=%s)", rid)
    return JSONResponse(status_code=500, content={"error": "internal_error", "request_id": rid})


app.include_router(orgs.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(gtm.router, prefix="/api")
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
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness — can we actually serve (DB reachable)? 503 if not."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from apps.api.models.db import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "not_ready", "db": str(e)[:120]})
    finally:
        db.close()


@app.get("/api/metrics")
def api_metrics() -> dict:
    """In-process request metrics (per-route counts, errors, latency) + uptime."""
    from apps.api.reliability.metrics import metrics

    return metrics().snapshot()
