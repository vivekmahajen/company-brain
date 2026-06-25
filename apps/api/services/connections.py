"""Per-tenant source connections + onboarding — Phase 2, Slice 1.

A company connects *their own* sources (with *their own* credentials) instead of
only the bundled fixtures. Credentials go to the encrypted vault, never to
`config_jsonb`. Sync reuses the existing idempotent `sync_source` path. Everything
is org-scoped, so a tenant can only see/sync/delete its own sources.

OAuth (Slice 2) layers on top: the callback just produces a token that lands here
via `connect_source(..., secrets={"access_token": ...})`. Background workers
(later) just call `sync_tenant_source` on a schedule.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.connectors.registry import REGISTRY
from apps.api.models.tables import Artifact, Source, SourceSecret
from apps.api.secrets.vault import get_vault

# What each connector kind needs to authenticate. Drives the connect UI and tells
# Slice 2 which kinds get an OAuth dance vs. a pasted token. `auth`:
#   oauth   — needs an OAuth app (Slice 2); a pasted access_token works today.
#   token   — a personal/API token the user pastes.
#   dsn     — a read-only connection string.
#   none    — fixture/push only, no credentials.
CONNECTOR_CATALOG = {
    "slack":      {"auth": "oauth", "secret_fields": ["access_token"]},
    "notion":     {"auth": "oauth", "secret_fields": ["access_token"]},
    "gmail":      {"auth": "oauth", "secret_fields": ["access_token"]},
    "github":     {"auth": "token", "secret_fields": ["access_token"]},
    "linear":     {"auth": "token", "secret_fields": ["api_key"]},
    "zendesk":    {"auth": "token", "secret_fields": ["api_token", "subdomain"]},
    "postgres":   {"auth": "dsn",   "secret_fields": ["dsn"]},
    "transcript": {"auth": "none",  "secret_fields": []},
    "manual":     {"auth": "none",  "secret_fields": []},
}


def list_connectors() -> list[dict]:
    """Connector kinds + how each authenticates. For OAuth kinds, report whether an
    OAuth app is configured so the UI can show 'Connect' vs. 'Paste a token'."""
    from apps.api.connectors import oauth

    out = []
    for k in sorted(REGISTRY):
        meta = {"kind": k, **CONNECTOR_CATALOG.get(k, {"auth": "none", "secret_fields": []})}
        if oauth.supports_oauth(k):
            meta["oauth_configured"] = oauth.is_configured(k)
            meta["authorize_path"] = f"/api/connect/{k}/authorize"
        out.append(meta)
    return out


# --- credential storage (vault-backed) ------------------------------------
def store_source_secret(db: Session, org_id: str, source_id: str, secrets: dict) -> None:
    vault = get_vault()
    ct = vault.encrypt(secrets)
    row = db.scalar(select(SourceSecret).where(
        SourceSecret.org_id == org_id, SourceSecret.source_id == source_id))
    if row:
        row.ciphertext, row.backend = ct, vault.backend
    else:
        db.add(SourceSecret(org_id=org_id, source_id=source_id, ciphertext=ct, backend=vault.backend))
    db.flush()


def load_source_secret(db: Session, org_id: str, source_id: str) -> dict | None:
    row = db.scalar(select(SourceSecret).where(
        SourceSecret.org_id == org_id, SourceSecret.source_id == source_id))
    if not row:
        return None
    return get_vault().decrypt(row.ciphertext)


def merged_source_config(db: Session, org_id: str, source: Source) -> dict:
    """Source config_jsonb + decrypted vault credentials. Used to build a connector
    that can actually talk to a live provider; the merge is in-memory only."""
    cfg = dict(source.config_jsonb or {})
    secrets = load_source_secret(db, org_id, source.id)
    if secrets:
        cfg.update(secrets)
    return cfg


def _has_secret(db: Session, org_id: str, source_id: str) -> bool:
    return db.scalar(select(SourceSecret.id).where(
        SourceSecret.org_id == org_id, SourceSecret.source_id == source_id)) is not None


# --- connect / sync / delete (all tenant-scoped) --------------------------
def _source_view(db: Session, s: Source) -> dict:
    return {"id": s.id, "kind": s.kind, "name": s.name, "status": s.status,
            "mode": s.config_jsonb.get("mode", "fixture"),
            "has_credentials": _has_secret(db, s.org_id, s.id),
            "acl_groups": s.config_jsonb.get("acl_groups", []),
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None}


def connect_source(db: Session, org_id: str, *, kind: str, name: str,
                   config: dict | None = None, secrets: dict | None = None) -> dict:
    """Register a tenant-owned source. Non-secret settings go in config_jsonb;
    credentials go to the vault. Returns the source view (never the secrets)."""
    if kind not in REGISTRY:
        return {"error": f"unknown connector kind: {kind}", "known": sorted(REGISTRY)}
    cfg = dict(config or {})
    # Label the source: real credentials → live; a fixture_path → fixture; otherwise
    # live (awaiting credentials). Purely informational — the connector uses whatever
    # config/secrets it's given at sync time.
    cfg["mode"] = "live" if secrets else cfg.get("mode", "fixture" if cfg.get("fixture_path") else "live")
    src = Source(org_id=org_id, kind=kind, name=name, config_jsonb=cfg, status="connected")
    db.add(src)
    db.flush()
    if secrets:
        store_source_secret(db, org_id, src.id, secrets)
    db.commit()
    return _source_view(db, src)


def sync_tenant_source(db: Session, org_id: str, source_id: str) -> dict:
    from apps.api.services.ingest import sync_source

    src = db.scalar(select(Source).where(Source.org_id == org_id, Source.id == source_id))
    if not src:
        return {"error": "not found"}  # 404 at the router; no cross-tenant leak
    result = sync_source(db, src, org_id=org_id)
    # Mirror the source's native ACLs (e.g. private repo → eng-team) so a runtime-
    # connected source's data is governed by its real audience, not default-deny.
    try:
        from apps.api.access.seed import mirror_source_acls

        mirror_source_acls(db, org_id, src, merged_source_config(db, org_id, src))
    except Exception:  # noqa: BLE001 - ACL mirror failure must not fail the sync
        pass
    db.commit()
    return result


def delete_tenant_source(db: Session, org_id: str, source_id: str) -> dict:
    src = db.scalar(select(Source).where(Source.org_id == org_id, Source.id == source_id))
    if not src:
        return {"error": "not found"}
    db.query(Artifact).filter(Artifact.org_id == org_id, Artifact.source_id == source_id).delete()
    db.query(SourceSecret).filter(SourceSecret.org_id == org_id,
                                  SourceSecret.source_id == source_id).delete()
    db.delete(src)
    db.commit()
    return {"deleted": source_id}


# --- onboarding status ----------------------------------------------------
def onboarding_status(db: Session, org_id: str) -> dict:
    from apps.api.models.tables import KnowledgeUnit, Skill

    sources = db.scalars(select(Source).where(Source.org_id == org_id)).all()
    n_sources = len(sources)
    n_artifacts = db.scalar(select(Artifact.id).where(Artifact.org_id == org_id).limit(1)) is not None
    n_kus = db.scalar(select(KnowledgeUnit.id).where(KnowledgeUnit.org_id == org_id).limit(1)) is not None
    skills = db.scalars(select(Skill).where(Skill.org_id == org_id)).all()
    needs_review = sum(1 for s in skills if s.status == "needs_review")

    steps = [
        {"key": "connect_source", "label": "Connect a source", "done": n_sources > 0},
        {"key": "first_sync", "label": "Sync artifacts", "done": bool(n_artifacts)},
        {"key": "first_skill", "label": "Compile a skill", "done": len(skills) > 0},
        {"key": "review", "label": "Review & approve", "done": len(skills) > 0 and needs_review == 0},
    ]
    next_step = next((s["key"] for s in steps if not s["done"]), None)
    return {"org_id": org_id, "sources": n_sources, "skills": len(skills),
            "needs_review": needs_review, "steps": steps, "next_step": next_step,
            "complete": next_step is None}
