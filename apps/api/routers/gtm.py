"""GTM surface (Phase 8): per-tenant brain scorecard + vertical capability packs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.models.db import get_session
from apps.api.packs.catalog import install_pack, list_packs
from apps.api.services.scorecard import tenant_scorecard

router = APIRouter()


@router.get("/scorecard")
def scorecard(db: Session = Depends(get_session)):
    """This tenant's brain health + governance posture + readiness score."""
    return tenant_scorecard(db, current_org())


@router.get("/packs")
def packs():
    """The vertical capability-pack catalog."""
    return list_packs()


@router.post("/packs/{pack_id}/install")
def packs_install(pack_id: str, db: Session = Depends(get_session)):
    """Install a pack's capabilities into this tenant (quota-checked, dedup'd)."""
    res = install_pack(db, current_org(), pack_id)
    if res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return res
