"""Tenant lifecycle: create an org and provision its brain. Phase 1.

Creating a tenant = an `Org` row + the full seeded brain for that `org_id`
(sources → KUs → skills → principals → access). Everything downstream already
filters by `org_id`, so two provisioned orgs are isolated by construction; the
isolation test asserts it.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.principals import SEED_PRINCIPALS
from apps.api.config import get_settings
from apps.api.models.tables import Org


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return base[:48]


def ensure_default_org(db: Session) -> Org:
    """Make sure the configured default org has a registry row (idempotent)."""
    s = get_settings()
    o = db.scalar(select(Org).where(Org.id == s.default_org_id))
    if o:
        return o
    o = Org(id=s.default_org_id, name="Default", slug="default", status="active")
    db.add(o)
    db.commit()
    return o


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, i = base, 2
    while db.scalar(select(Org).where(Org.slug == slug)):
        slug = f"{base}-{i}"
        i += 1
    return slug


def list_orgs(db: Session) -> list[dict]:
    ensure_default_org(db)
    rows = db.scalars(select(Org).order_by(Org.created_at)).all()
    return [{"id": o.id, "name": o.name, "slug": o.slug, "status": o.status,
             "created_at": o.created_at.isoformat() if o.created_at else None} for o in rows]


def org_tokens(org_id: str) -> dict[str, str]:
    """The seeded access tokens for an org. Non-default orgs get org-prefixed
    tokens (so credentials never collide across tenants) — mirrors seed_principals."""
    s = get_settings()
    out = {}
    for spec in SEED_PRINCIPALS:
        tok = spec["token"] if org_id == s.default_org_id else f"{org_id}:{spec['token']}"
        out[spec["token"]] = tok
    return out


def create_org(db: Session, *, name: str) -> dict:
    """Create a tenant and provision its full brain. Returns the org + its tokens."""
    from apps.api.services.pipeline import run_full_pipeline
    from apps.api.services.serving import approve_demo_skills, seed_serving

    ensure_default_org(db)
    org = Org(name=name.strip() or "Untitled", slug=_unique_slug(db, name), status="active")
    db.add(org)
    db.commit()

    # Provision the brain for this org_id (offline/free on the fixture provider).
    report = run_full_pipeline(db, org.id)
    seed_serving(db, org.id)
    approve_demo_skills(db, org.id)

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "status": org.status,
        "skills": report.get("skills"),
        "tokens": org_tokens(org.id),
        "how_to_call": "send Authorization: Bearer <agent token>, or X-Org-Id: <id>",
    }
