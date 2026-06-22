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


def sync_default_sources(db: Session, org_id: str | None = None) -> list[dict]:
    """Convenience: connect + sync the Phase-1 Slack + Notion fixture sources."""
    org_id = org_id or get_settings().default_org_id
    results = []
    for kind, name in (("slack", "#support"), ("notion", "Refund Policy Space")):
        src = ensure_source(db, org_id=org_id, kind=kind, name=name)
        results.append(sync_source(db, src, org_id=org_id))
    db.commit()
    return results
