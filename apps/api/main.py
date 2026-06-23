"""FastAPI app: REST surface + mounted MCP Streamable HTTP transport."""
from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.models.db import init_db
from apps.api.routers import approvals, brain

logger = logging.getLogger("company_brain")


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
