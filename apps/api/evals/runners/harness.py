"""Shared execution harness for E5 (SEC) and E6 (GAR).

Drives the REAL GovernedExecutor + sandbox action adapters against an order
store seeded from each scenario's facts. A guardrail leak here is a guardrail
leak in production (§5).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.principals import resolve_principal
from apps.api.execution.executor import GovernedExecutor
from apps.api.models.serving import Order
from apps.api.services.serving import approve_demo_skills

# Isolated org so eval runs never touch demo/prod data.
EVAL_ORG = "00000000-0000-0000-0000-0000000eva15"

AGENT = "agent-token"
LIMITED = "agent-readonly-token"
HUMAN = "human-token"


def setup_brain(db: Session) -> None:
    """Build + approve the brain in the eval org (idempotent)."""
    from apps.api.services.pipeline import run_full_pipeline

    run_full_pipeline(db, EVAL_ORG)
    approve_demo_skills(db, EVAL_ORG)


def _eval_token(token: str) -> str:
    """Eval-org principals use org-prefixed tokens (see seed_principals)."""
    return f"{EVAL_ORG}:{token}"


def principal(db: Session, token: str):
    return resolve_principal(db, _eval_token(token))


def upsert_order(db: Session, order: dict | None) -> None:
    if not order:
        return
    row = db.scalar(
        select(Order).where(Order.org_id == EVAL_ORG, Order.order_id == str(order["id"]))
    )
    if row is None:
        row = Order(org_id=EVAL_ORG, order_id=str(order["id"]))
        db.add(row)
    row.original_charge = float(order["amount"])
    row.age_days = int(order.get("age_days", 0))
    db.commit()


def new_key() -> str:
    return f"eval-{uuid.uuid4()}"


def invoke_refund(db: Session, *, token: str, request: dict, idempotency_key: str | None = None,
                  approval_id: str | None = None) -> dict:
    p = principal(db, token)
    if not p:
        return {"status": "denied", "reason": "no_principal", "detail": f"token {token} not seeded"}
    return GovernedExecutor(db).invoke(
        principal=p,
        skill_slug="handle-refund",
        tool_name="stripe_refund",
        args={k: v for k, v in request.items()},
        idempotency_key=idempotency_key or new_key(),
        approval_id=approval_id,
        transport="eval",
    )
