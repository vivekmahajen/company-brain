"""Audit log — security/compliance trail (Phase 5).

A single recorder the services call after a security-relevant action (auth, billing,
data connect/delete, capability authoring, tenant lifecycle). Append-only, tenant-
scoped, exportable to JSON/CSV. Recording never raises into the caller — an audit
failure must not break the action it's auditing.
"""
from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.tables import AuditEvent


def record_audit(db: Session, org_id: str, action: str, *, actor: str = "system",
                 target_type: str | None = None, target_id: str | None = None,
                 meta: dict | None = None) -> None:
    try:
        db.add(AuditEvent(org_id=org_id, actor=actor, action=action, target_type=target_type,
                          target_id=target_id, meta_jsonb=meta or {}))
        db.flush()
    except Exception:  # noqa: BLE001 - auditing must never break the audited action
        db.rollback()


def list_audit(db: Session, org_id: str, *, limit: int = 200) -> list[dict]:
    rows = db.scalars(
        select(AuditEvent).where(AuditEvent.org_id == org_id)
        .order_by(AuditEvent.created_at.desc()).limit(limit)
    ).all()
    return [{
        "id": r.id, "actor": r.actor, "action": r.action,
        "target_type": r.target_type, "target_id": r.target_id,
        "meta": r.meta_jsonb, "at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


def audit_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["at", "actor", "action", "target_type", "target_id"])
    for r in rows:
        w.writerow([r.get("at"), r.get("actor"), r.get("action"), r.get("target_type"), r.get("target_id")])
    return buf.getvalue()
