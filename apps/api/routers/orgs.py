"""Tenant management (Phase 1): create + list orgs, and report the resolved tenant.

POST /api/orgs creates a company and provisions its brain. It is gated by
`X-Admin-Token` when `admin_token` is configured (open otherwise, for the demo).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.config import get_settings
from apps.api.models.db import get_session
from apps.api.services.orgs import create_org, list_orgs

router = APIRouter()


class CreateOrgBody(BaseModel):
    name: str


def _require_admin(x_admin_token: str | None) -> None:
    configured = get_settings().admin_token
    if configured and x_admin_token != configured:
        raise HTTPException(status_code=403, detail="invalid or missing X-Admin-Token")


@router.post("/orgs")
def orgs_create(
    body: CreateOrgBody,
    db: Session = Depends(get_session),
    x_admin_token: str | None = Header(default=None),
):
    _require_admin(x_admin_token)
    return create_org(db, name=body.name)


@router.get("/orgs")
def orgs_list(db: Session = Depends(get_session)):
    return list_orgs(db)


@router.get("/orgs/current")
def orgs_current():
    """Which tenant did this request resolve to? Useful to confirm token/header routing."""
    return {"org_id": current_org()}
