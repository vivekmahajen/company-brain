"""FastAPI app: the REST surface for the console + non-MCP agents."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import logging

from apps.api.config import get_settings
from apps.api.models.db import init_db
from apps.api.routers import brain

logger = logging.getLogger("company_brain")
app = FastAPI(title="Company Brain API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(brain.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    settings = get_settings()
    if settings.seed_on_startup:
        from sqlalchemy import select

        from apps.api.models.db import SessionLocal
        from apps.api.models.tables import Skill
        from apps.api.services.pipeline import run_full_pipeline

        db = SessionLocal()
        try:
            already = db.scalar(select(Skill).where(Skill.org_id == settings.default_org_id))
            if not already:
                report = run_full_pipeline(db, settings.default_org_id)
                logger.info("Seeded brain on startup: %s", report.get("skill"))
        except Exception:  # noqa: BLE001 - never block boot on seeding
            logger.exception("startup seed failed")
        finally:
            db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
