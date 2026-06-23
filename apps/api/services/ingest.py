"""M1 ingestion service: run a connector and land artifacts idempotently."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.connectors.registry import get_connector
from apps.api.models.tables import Artifact, Source


def ensure_source(db: Session, *, org_id: str, kind: str, name: str, config: dict | None = None) -> Source:
    src = db.scalar(select(Source).where(Source.org_id == org_id, Source.kind == kind, Source.name == name))
    if src:
        return src
    src = Source(org_id=org_id, kind=kind, name=name, config_jsonb=config or {})
    db.add(src)
    db.flush()
    return src


def sync_source(db: Session, source: Source, *, org_id: str | None = None) -> dict:
    """Pull from the connector and insert only new artifacts (idempotent)."""
    org_id = org_id or source.org_id
    connector = get_connector(source.kind, source.config_jsonb)
    artifacts = connector.pull(since=None)  # full pull; dedupe below makes it idempotent

    inserted = 0
    skipped = 0
    for na in artifacts:
        existing = db.scalar(
            select(Artifact).where(
                Artifact.org_id == org_id,
                Artifact.source_id == source.id,
                Artifact.external_id == na.external_id,
            )
        )
        if existing:
            skipped += 1
            continue
        db.add(
            Artifact(
                org_id=org_id,
                source_id=source.id,
                external_id=na.external_id,
                kind=na.kind,
                raw_jsonb=na.raw,
                content_text=na.content_text,
                content_hash=na.content_hash,
                author=na.author,
                occurred_at=na.occurred_at,
            )
        )
        inserted += 1
    source.last_synced_at = datetime.now(timezone.utc)
    db.flush()
    return {"source": source.name, "kind": source.kind, "inserted": inserted, "skipped": skipped}


import os

# Default fixture sources spanning all connector kinds. Each entry:
# (kind, display name, fixture file, mirrored ACL groups). The ACL groups make
# the multi-source skills role-restricted (refund→support, pricing→sales,
# incident→eng) — see access/seed.py.
_DEFAULT_SOURCES = [
    ("slack", "#support", "slack/support.json", ["support-team"]),
    ("notion", "Refund Policy Space", "notion/refund-policy.json", ["all-staff"]),
    ("notion", "Pricing Policy Space", "notion/pricing-policy.json", ["all-staff"]),
    ("notion", "Incident Runbook Space", "notion/incident-runbook.json", ["all-staff"]),
    ("github", "acme/platform (incidents)", "github/incident.json", ["eng-team"]),
    ("linear", "core team (incidents)", "linear/incidents.json", ["eng-team"]),
    ("transcript", "Incident retros", "transcript/incident-retro.json", ["eng-team"]),
    ("transcript", "Sales calls", "transcript/sales-call.json", ["sales-team"]),
    ("gmail", "deal-desk@acme.com", "gmail/deal-desk.json", ["sales-team"]),
    ("postgres", "pricing & orders DB", "postgres/pricing.json", ["all-staff"]),
    ("zendesk", "support tickets", "zendesk/tickets.json", ["support-team"]),
]


def sync_default_sources(db: Session, org_id: str | None = None) -> list[dict]:
    """Connect + sync the bundled fixture sources across all connector kinds."""
    org_id = org_id or get_settings().default_org_id
    fixtures_dir = get_settings().fixtures_dir
    results = []
    for kind, name, rel, acl_groups in _DEFAULT_SOURCES:
        config = {"fixture_path": os.path.join(fixtures_dir, rel), "acl_groups": acl_groups}
        src = ensure_source(db, org_id=org_id, kind=kind, name=name, config=config)
        if src.config_jsonb != config:  # keep config current if it already existed
            src.config_jsonb = config
            db.flush()
        results.append(sync_source(db, src, org_id=org_id))
    db.commit()
    return results
