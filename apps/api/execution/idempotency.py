"""Idempotency helpers (INV-5)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.serving import ApprovalRequest
from apps.api.models.tables import ExecutionLog


def find_completed(db: Session, org_id: str, key: str) -> ExecutionLog | None:
    """An already-executed (or idempotent-replayed) log for this key, if any."""
    return db.scalar(
        select(ExecutionLog)
        .where(
            ExecutionLog.org_id == org_id,
            ExecutionLog.idempotency_key == key,
            ExecutionLog.outcome.in_(("executed", "idempotent_replay")),
        )
        .order_by(ExecutionLog.occurred_at.asc())
    )


def find_pending_approval(db: Session, org_id: str, key: str) -> ApprovalRequest | None:
    return db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.org_id == org_id,
            ApprovalRequest.idempotency_key == key,
            ApprovalRequest.status == "pending",
        )
    )
