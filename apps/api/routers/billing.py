"""Billing, plans & usage (Phase 6). Tenant-scoped.

Usage metering is real (extraction spend per tenant per period); plan changes here
are the self-serve upgrade path. Charging via Stripe is a later slice — this is the
metering + quota + plan layer it will sit on.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.billing.checkout import confirm_stub, create_checkout, handle_webhook
from apps.api.billing.metering import set_plan, usage_summary
from apps.api.billing.plans import PLANS
from apps.api.config import get_settings
from apps.api.models.db import SessionLocal, get_session

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
    """Direct plan set (downgrades; demo). Paid upgrades should go via /billing/checkout."""
    res = set_plan(db, current_org(), body.plan)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


class CheckoutBody(BaseModel):
    plan: str
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/billing/checkout")
def checkout(body: CheckoutBody, db: Session = Depends(get_session)):
    """Start an upgrade. Returns a Checkout URL (real Stripe when configured, else a
    stub confirm URL). A 'free' plan downgrades immediately."""
    res = create_checkout(current_org(), body.plan, success_url=body.success_url, cancel_url=body.cancel_url)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    if res.get("mode") == "direct":  # free downgrade — apply now
        set_plan(db, current_org(), body.plan)
    return res


@router.get("/billing/checkout/confirm")
def checkout_confirm(state: str, db: Session = Depends(get_session)):
    """Stub-mode checkout completion (no Stripe). Applies the sealed plan, redirects
    to the console billing page."""
    res = confirm_stub(db, state)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    base = (get_settings().oauth_redirect_base or "").rstrip("/")
    return RedirectResponse(url=f"{base}/billing?upgraded={res['plan']}" if base else "/", status_code=302)


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Stripe → us. Verifies the signature (when STRIPE_WEBHOOK_SECRET is set) then
    applies plan changes. Not tenant-scoped — the org rides in event metadata."""
    payload = await request.body()
    secret = get_settings().stripe_webhook_secret
    if secret:
        import stripe

        try:
            event = stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature"), secret)
            event = json.loads(json.dumps(event, default=str))  # → plain dict
        except Exception:  # noqa: BLE001 - bad signature / parse
            raise HTTPException(status_code=400, detail="invalid webhook signature")
    else:
        event = json.loads(payload or b"{}")  # dev: no secret configured
    db = SessionLocal()
    try:
        return handle_webhook(db, event)
    finally:
        db.close()
