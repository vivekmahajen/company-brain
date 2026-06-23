"""Access audit log writer (VIS-8)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.models.access import AccessLog


def log_decision(db: Session, *, org_id: str, principal_id: str | None, action: str,
                 target_type: str, target_id: str, decision: str, reason: str) -> None:
    db.add(AccessLog(org_id=org_id, principal_id=principal_id, action=action,
                     target_type=target_type, target_id=target_id, decision=decision, reason=reason))
    db.commit()
