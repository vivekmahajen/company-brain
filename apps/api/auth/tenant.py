"""Per-request tenant (org) resolution — Phase 1 of the SaaS roadmap.

The whole data model is already `org_id`-scoped; this is the seam that decides
*which* org a request belongs to, instead of always using the default.

Resolution order (first hit wins):
  1. `Authorization: Bearer <token>` → the principal it maps to → `principal.org_id`.
  2. `X-Org-Id: <org_id>` header → that org, if it exists and is active.
  3. Fallback to `default_org_id` — UNLESS `multi_tenant_strict` is on, in which
     case an unresolved tenant is rejected (fail closed).

The resolved id lives in a contextvar set by `TenantMiddleware` (pure-ASGI, so the
value reliably reaches the endpoint), and `current_org()` reads it. Every existing
`_org()` call site now returns the per-request tenant with no signature change.
"""
from __future__ import annotations

import contextvars

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.principals import resolve_principal
from apps.api.config import get_settings

# The org id for the in-flight request. Unset → callers use the default org.
current_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_org_id", default=None
)

# Paths that must work WITHOUT a resolved tenant even in strict mode: tenant
# creation/listing, health, and API docs. (Prefix match.)
_STRICT_ALLOWLIST = ("/api/orgs", "/health", "/docs", "/openapi.json", "/redoc")


def current_org() -> str:
    """The resolved tenant for this request, or the default org if none was set."""
    return current_org_id.get() or get_settings().default_org_id


def org_exists(db: Session, org_id: str) -> bool:
    from apps.api.models.tables import Org

    s = get_settings()
    if org_id == s.default_org_id:
        return True  # the configured default is always valid
    o = db.scalar(select(Org).where(Org.id == org_id))
    return bool(o and o.status == "active")


def resolve_org_id(
    db: Session,
    *,
    authorization: str | None,
    x_org_id: str | None,
    path: str = "",
) -> tuple[str, str, bool]:
    """Return (org_id, how, ok). `ok=False` only happens in strict mode when the
    tenant can't be resolved and the path isn't allowlisted — the caller 401s."""
    s = get_settings()

    # 1) credential → principal → org
    if authorization:
        p = resolve_principal(db, authorization)
        if p:
            return p.org_id, "token", True

    # 2) explicit org header (validated)
    if x_org_id and org_exists(db, x_org_id):
        return x_org_id, "header", True

    # 3) fallback / strict fail-closed
    if s.multi_tenant_strict and not any(path.startswith(p) for p in _STRICT_ALLOWLIST):
        return s.default_org_id, "unresolved", False
    return s.default_org_id, "default", True
