"""Seed + helpers for the MCP serving layer.

Seeds demo orders (server-side facts), principals, and approves the compiled
demo skills so they are servable over MCP. Also the approval-decision workflow
(§8) with INV-4 enforced server-side.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.principals import has_scope, seed_principals
from apps.api.config import get_settings
from apps.api.execution.executor import GovernedExecutor
from apps.api.models.serving import ApprovalRequest, Order, Principal
from apps.api.models.tables import ExecutionLog, Skill

# (order_id, original_charge, age_days) — server ground truth for the gate.
_DEMO_ORDERS = [
    ("1234", 620.0, 40),   # over threshold -> approval
    ("55", 200.0, 12),     # under threshold -> executes
    ("9001", 200.0, 100),  # >90 days -> soft guardrail escalation
    ("7777", 100.0, 5),    # used to test hard guardrail (refund > charge)
]


def seed_orders(db: Session, org_id: str) -> None:
    for oid, charge, age in _DEMO_ORDERS:
        if db.scalar(select(Order).where(Order.org_id == org_id, Order.order_id == oid)):
            continue
        db.add(Order(org_id=org_id, order_id=oid, original_charge=charge, age_days=age))
    db.commit()


def approve_demo_skills(db: Session, org_id: str) -> None:
    """Mark the latest compiled demo skills `approved` so the server can expose
    them. (In real use a human approves each skill in the console.)"""
    rows = db.scalars(select(Skill).where(Skill.org_id == org_id)).all()
    latest: dict[str, Skill] = {}
    for s in rows:
        if s.slug not in latest or s.version > latest[s.slug].version:
            latest[s.slug] = s
    for s in latest.values():
        if s.status in ("needs_review", "draft"):
            s.status = "approved"
    db.commit()


def seed_serving(db: Session, org_id: str | None = None) -> None:
    """Principals + server-side order facts. Skill approval is a SEPARATE,
    explicit governance step (`approve_demo_skills`) so the compiler's
    needs_review default stays observable."""
    org_id = org_id or get_settings().default_org_id
    seed_principals(db, org_id)
    seed_orders(db, org_id)


# --- approval decision (§8) ------------------------------------------------
def list_pending_approvals(db: Session, org_id: str) -> list[dict]:
    rows = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.org_id == org_id, ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at.desc())
    ).all()
    out = []
    for ar in rows:
        requester = db.get(Principal, ar.requested_by_principal)
        out.append(
            {
                "id": ar.id,
                "tool_name": ar.tool_name,
                "requested_by": requester.display_name if requester else ar.requested_by_principal,
                "input": ar.input_jsonb,
                "resolved_facts": ar.resolved_facts_jsonb,
                "gate_reason": ar.gate_reason,
                "created_at": ar.created_at.isoformat() if ar.created_at else None,
                "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
            }
        )
    return out


def get_approval(db: Session, org_id: str, approval_id: str) -> dict | None:
    ar = db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.org_id == org_id, ApprovalRequest.id == approval_id)
    )
    if not ar:
        return None
    return {
        "approval_id": ar.id,
        "status": ar.status,
        "tool_name": ar.tool_name,
        "gate_reason": ar.gate_reason,
        "result": ar.result_jsonb if ar.status == "executed" else None,
    }


def decide_approval(
    db: Session, org_id: str, approval_id: str, *, decision: str, approver: Principal
) -> dict:
    """Approve or reject a held action. Enforces INV-4 + approver scope."""
    ar = db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.org_id == org_id, ApprovalRequest.id == approval_id)
    )
    if not ar:
        return {"error": "approval not found"}
    if ar.status != "pending":
        return {"error": f"approval already {ar.status}"}
    if ar.expires_at and _aware(ar.expires_at) < datetime.now(timezone.utc):
        ar.status = "expired"
        db.commit()
        return {"error": "approval expired"}

    # INV-4: requester cannot approve their own request.
    if ar.requested_by_principal == approver.id:
        return {"error": "requester cannot approve their own request (separation of duties)"}
    if not has_scope(approver, f"approve:{ar.tool_name}"):
        return {"error": f"principal lacks approve:{ar.tool_name}"}

    ar.decided_by_principal = approver.id
    ar.decided_at = datetime.now(timezone.utc)

    if decision == "reject":
        ar.status = "rejected"
        db.add(
            ExecutionLog(
                org_id=org_id, skill_id=ar.skill_id, principal_id=approver.id,
                idempotency_key=ar.idempotency_key, approval_request_id=ar.id,
                outcome="rejected", gate_decision="rejected",
                input_jsonb=ar.input_jsonb, output_jsonb={"reason": "rejected by approver"},
            )
        )
        db.commit()
        return {"approval_id": ar.id, "status": "rejected"}

    # approve -> server executes the held action (default path a)
    ar.status = "approved"
    db.commit()
    result = GovernedExecutor(db).execute_held(ar, approver)
    return {"approval_id": ar.id, "status": ar.status, "execution": result}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
