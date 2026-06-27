"""Stripe Checkout + webhook (Phase 6).

Flow:
  POST /api/billing/checkout {plan} → a Checkout URL the console redirects to.
    * Stripe configured (STRIPE_API_KEY + STRIPE_PRICE_<PLAN>): a real Checkout session;
      the plan applies via the webhook on `checkout.session.completed`.
    * Otherwise: STUB mode — a URL to /api/billing/checkout/confirm that applies the
      plan immediately (no charge), so the upgrade flow is demoable without keys.

The tenant + target plan are carried in a vault-sealed token (stub) or Stripe session
metadata (real), so the confirm/webhook — which arrive without an auth header — apply
the change to the right org and can't be tampered.
"""
from __future__ import annotations

import os
import time

from sqlalchemy.orm import Session

from apps.api.billing.metering import set_plan
from apps.api.billing.plans import PLANS, is_valid_plan
from apps.api.config import get_settings
from apps.api.secrets.vault import get_vault

_TTL = 900


def _price_id(plan: str) -> str | None:
    return os.environ.get(f"STRIPE_PRICE_{plan.upper()}")


def stripe_configured(plan: str) -> bool:
    return bool(get_settings().stripe_api_key) and bool(_price_id(plan))


def seal(org_id: str, plan: str) -> str:
    return get_vault().encrypt({"org": org_id, "plan": plan, "exp": int(time.time()) + _TTL})


def unseal(token: str) -> tuple[str, str]:
    d = get_vault().decrypt(token)  # raises on tamper
    if int(d.get("exp", 0)) < int(time.time()):
        raise ValueError("checkout token expired")
    return d["org"], d["plan"]


def create_checkout(org_id: str, plan: str, *, success_url: str | None, cancel_url: str | None) -> dict:
    if not is_valid_plan(plan):
        return {"error": f"unknown plan '{plan}'"}
    if plan in ("free",):
        return {"mode": "direct", "note": "downgrade applies immediately"}
    if plan == "enterprise":
        return {"mode": "contact", "note": "enterprise is custom-priced — contact sales"}

    if stripe_configured(plan):
        import stripe

        stripe.api_key = get_settings().stripe_api_key
        base = (get_settings().oauth_redirect_base or "").rstrip("/")
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": _price_id(plan), "quantity": 1}],
            success_url=success_url or f"{base}/billing?upgraded={plan}",
            cancel_url=cancel_url or f"{base}/billing",
            client_reference_id=org_id,
            metadata={"org_id": org_id, "plan": plan},
        )
        return {"mode": "stripe", "url": session.url}

    # stub: no Stripe configured → confirm endpoint applies the plan (no charge)
    base = (get_settings().oauth_redirect_base or "").rstrip("/")
    return {"mode": "stub", "url": f"{base}/api/billing/checkout/confirm?state={seal(org_id, plan)}"}


def confirm_stub(db: Session, state: str) -> dict:
    """Apply a stub checkout (only valid when Stripe is NOT configured)."""
    if get_settings().stripe_api_key:
        return {"error": "stub checkout disabled while Stripe is configured"}
    org_id, plan = unseal(state)
    set_plan(db, org_id, plan)
    return {"confirmed": True, "org_id": org_id, "plan": plan}


def handle_webhook(db: Session, event: dict) -> dict:
    """Apply plan changes from Stripe events. Signature is verified at the route."""
    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    if etype == "checkout.session.completed":
        md = obj.get("metadata") or {}
        org_id, plan = md.get("org_id"), md.get("plan")
        if org_id and is_valid_plan(plan):
            set_plan(db, org_id, plan)
            return {"applied": plan, "org_id": org_id}
    if etype == "customer.subscription.deleted":
        org_id = obj.get("metadata", {}).get("org_id") or obj.get("client_reference_id")
        if org_id:
            set_plan(db, org_id, "free")  # lapsed subscription → downgrade
            return {"applied": "free", "org_id": org_id}
    return {"ignored": etype}
