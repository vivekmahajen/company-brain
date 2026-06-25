"""Self-serve source connections + onboarding (Phase 2, Slice 1).

All routes are tenant-scoped via the resolved org (TenantMiddleware). A tenant can
only connect/sync/delete its own sources; credentials are stored in the vault.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.models.db import get_session
from apps.api.services.connections import (
    connect_source,
    delete_tenant_source,
    list_connectors,
    onboarding_status,
    sync_tenant_source,
)

router = APIRouter()


@router.get("/connectors")
def connectors_list():
    """Available connector kinds + what each needs to authenticate."""
    return list_connectors()


class ConnectBody(BaseModel):
    kind: str
    name: str
    config: dict | None = None
    secrets: dict | None = None  # credentials → vault, never echoed back


@router.post("/sources/connect")
def sources_connect(body: ConnectBody, db: Session = Depends(get_session)):
    res = connect_source(db, current_org(), kind=body.kind, name=body.name,
                         config=body.config, secrets=body.secrets)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/sources/{source_id}/sync")
def sources_sync(source_id: str, db: Session = Depends(get_session)):
    res = sync_tenant_source(db, current_org(), source_id)
    if res.get("error"):
        raise HTTPException(status_code=404, detail="source not found in this tenant")
    return res


@router.delete("/sources/{source_id}")
def sources_delete(source_id: str, db: Session = Depends(get_session)):
    res = delete_tenant_source(db, current_org(), source_id)
    if res.get("error"):
        raise HTTPException(status_code=404, detail="source not found in this tenant")
    return res


@router.get("/onboarding")
def onboarding(db: Session = Depends(get_session)):
    return onboarding_status(db, current_org())
