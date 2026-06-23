"""Identity & authorization for the serving layer (§9).

A credential (bearer token / stdio env token) resolves to a Principal carrying an
org, role, and scopes. Scopes drive both `invoke:<tool>` and `approve:<tool>`
checks; `*` wildcards are supported (e.g. `invoke:*`, `approve:*`).

This is the seam where per-source / per-skill ACLs will later slot in.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.serving import Principal


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_principal(db: Session, credential: str | None) -> Principal | None:
    """Map a raw credential to an active principal, or None."""
    if not credential:
        return None
    token = credential
    if token.lower().startswith("bearer "):
        token = token[7:]
    token = token.strip()
    p = db.scalar(select(Principal).where(Principal.token_hash == hash_token(token)))
    if not p or p.status != "active":
        return None
    return p


def has_scope(principal: Principal, scope: str) -> bool:
    """`invoke:stripe_refund` is granted by exact match or a `invoke:*` wildcard."""
    scopes = principal.scopes_jsonb or []
    if scope in scopes:
        return True
    verb = scope.split(":", 1)[0]
    return f"{verb}:*" in scopes or "*" in scopes


# Demo principals seeded for the bundled flow + tests. Tokens are NOT secrets in
# sandbox; in production, principals are provisioned with real hashed tokens.
SEED_PRINCIPALS = [
    {
        "kind": "agent",
        "display_name": "Demo agent (full invoke)",
        "role": "agent",
        "scopes": ["invoke:*"],
        "token": "agent-token",
    },
    {
        "kind": "agent",
        "display_name": "Limited agent (no refunds)",
        "role": "agent",
        "scopes": ["invoke:update_support_ticket"],
        "token": "agent-readonly-token",
    },
    {
        "kind": "human",
        "display_name": "Refund approver",
        "role": "approver",
        "scopes": ["approve:*", "invoke:*"],
        "token": "human-token",
    },
]


def seed_principals(db: Session, org_id: str | None = None) -> None:
    settings = get_settings()
    org_id = org_id or settings.default_org_id
    for spec in SEED_PRINCIPALS:
        # Tokens are globally unique → one credential maps to exactly one
        # principal/org. The default org keeps the clean demo tokens; other orgs
        # get an org-prefixed token so multi-tenant data never collides.
        token = spec["token"] if org_id == settings.default_org_id else f"{org_id}:{spec['token']}"
        th = hash_token(token)
        if db.scalar(select(Principal).where(Principal.token_hash == th)):
            continue
        db.add(
            Principal(
                org_id=org_id,
                kind=spec["kind"],
                display_name=spec["display_name"],
                role=spec["role"],
                scopes_jsonb=spec["scopes"],
                token_hash=th,
            )
        )
    db.commit()
