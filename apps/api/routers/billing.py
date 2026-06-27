"""Billing, plans & usage (Phase 6). Tenant-scoped.

Usage metering is real (extraction spend per tenant per period); plan changes here
are the self-serve upgrade path. Charging via Stripe is a later slice — this is the
metering + quota + plan layer it will sit on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.billing.metering import set_plan, usage_summary
from apps.api.billing.plans import PLANS
from apps.api.models.db import get_session

router = APIRouter()


@router.get("/billing/plans")
def billing_plans():
    """The plan catalog (limits + display price)."""
    return PLANS


@router.get("/usage")
def usage(db: Session = Depends(get_session)):
    """This tenant's plan, current-period usage, limits, and what's remaining."""
    return usage_summary(db, current_org())


class PlanBody(BaseModel):
    plan: str


@router.post("/billing/plan")
def change_plan(body: PlanBody, db: Session = Depends(get_session)):
    """Self-serve upgrade/downgrade. (Stripe checkout wraps this in a later slice.)"""
    res = set_plan(db, current_org(), body.plan)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res
