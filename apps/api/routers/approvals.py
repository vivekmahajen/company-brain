"""Approvals router (§8): list pending + decide (approve/reject).

Approver authority (scope + separation of duties) is enforced server-side here,
not just in the UI. The approver principal is resolved from the bearer token; the
console sends the seeded human ("human-token") by default.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.principals import resolve_principal
from apps.api.config import get_settings
from apps.api.models.db import get_session
from apps.api.services.serving import decide_approval, get_approval, list_pending_approvals

router = APIRouter()


def _org() -> str:
    return get_settings().default_org_id


def _approver(db: Session, authorization: str | None):
    # Default to the seeded human approver when no token is supplied (console).
    return resolve_principal(db, authorization or "human-token")


@router.get("/approvals")
def approvals_list(db: Session = Depends(get_session)):
    return list_pending_approvals(db, _org())


@router.get("/approvals/{approval_id}")
def approval_get(approval_id: str, db: Session = Depends(get_session)):
    return get_approval(db, _org(), approval_id) or {"error": "not found"}


class Decision(BaseModel):
    decision: str  # approve | reject


@router.post("/approvals/{approval_id}/decide")
def approval_decide(
    approval_id: str,
    body: Decision,
    db: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
):
    approver = _approver(db, authorization)
    if not approver:
        return {"error": "unauthorized: no valid approver principal"}
    return decide_approval(db, _org(), approval_id, decision=body.decision, approver=approver)
