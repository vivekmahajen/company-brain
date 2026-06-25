"""OAuth connect endpoints (Phase 2, Slice 2).

GET  /api/connect/{kind}/authorize  → consent URL (or `configured: false`)
GET  /api/connect/{kind}/callback   → exchange code, store token in vault, create source

The tenant is captured at `authorize` time and sealed into `state`, so the callback
(which carries no Authorization header — the browser is redirected from the provider)
provisions the credential to the right org.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.config import get_settings
from apps.api.connectors import oauth
from apps.api.models.db import get_session
from apps.api.services.connections import connect_source

router = APIRouter()


@router.get("/connect/{kind}/authorize")
def connect_authorize(kind: str):
    if not oauth.supports_oauth(kind):
        return {"configured": False, "kind": kind, "reason": "kind has no OAuth provider"}
    if not oauth.is_configured(kind):
        return {"configured": False, "kind": kind,
                "reason": "OAuth app not configured for this provider",
                "needed_env": oauth.needed_env(kind)}
    state = oauth.seal_state(current_org(), kind)
    return {"configured": True, "kind": kind, "authorize_url": oauth.authorize_url(kind, state)}


@router.get("/connect/{kind}/callback")
def connect_callback(
    kind: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_session),
):
    if error:
        return {"connected": False, "error": error}
    if not code or not state:
        return {"connected": False, "error": "missing code or state"}
    try:
        org_id = oauth.unseal_state(state, kind)  # tenant binding + CSRF + expiry
    except Exception:  # noqa: BLE001 - any seal failure is a rejected callback
        return {"connected": False, "error": "invalid or expired state"}

    secrets = oauth.exchange_code(kind, code)  # the one network call (mockable)
    source = connect_source(db, org_id, kind=kind, name=f"{kind} (oauth)", secrets=secrets)

    success = get_settings().oauth_success_redirect
    if success:
        return RedirectResponse(url=f"{success}?connected={kind}", status_code=302)
    return {"connected": True, "kind": kind, "org_id": org_id, "source": source}
