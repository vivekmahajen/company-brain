"""Security & compliance (Phase 5): audit log, data export, right-to-erasure."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.audit.log import audit_csv, list_audit
from apps.api.auth.tenant import current_org
from apps.api.config import get_settings
from apps.api.models.db import get_session
from apps.api.services.compliance import delete_tenant, export_tenant

router = APIRouter()


@router.get("/audit")
def audit(format: str = "json", limit: int = 200, db: Session = Depends(get_session)):
    """This tenant's security audit trail. `?format=csv` for a CSV export."""
    rows = list_audit(db, current_org(), limit=limit)
    if format == "csv":
        return PlainTextResponse(audit_csv(rows), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=audit.csv"})
    return rows


@router.get("/export")
def export(db: Session = Depends(get_session)):
    """Portable JSON export of this tenant's data (GDPR data portability). Credentials
    are never included."""
    return export_tenant(db, current_org())


class DeleteBody(BaseModel):
    confirm: bool = False


@router.post("/org/delete")
def org_delete(
    body: DeleteBody,
    db: Session = Depends(get_session),
    x_admin_token: str | None = Header(default=None),
):
    """Irreversibly delete ALL data for the current tenant (GDPR right-to-erasure).
    Requires confirm=true; admin-gated when ADMIN_TOKEN is set; the default/demo org
    is protected."""
    s = get_settings()
    org_id = current_org()
    if s.admin_token and x_admin_token != s.admin_token:
        raise HTTPException(status_code=403, detail="invalid or missing X-Admin-Token")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="set confirm=true to erase this tenant")
    if org_id == s.default_org_id:
        raise HTTPException(status_code=400, detail="the default org is protected from deletion")
    return delete_tenant(db, org_id)
