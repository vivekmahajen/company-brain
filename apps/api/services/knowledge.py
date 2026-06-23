"""Add ad-hoc knowledge to the Brain.

Paste arbitrary text (a policy, a decision, a runbook note) -> land it as an
artifact -> extract typed KUs with provenance -> synthesize -> recompile any
affected capability -> refresh the resolver. The same path the connectors use,
exposed for manual entry.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.skill_compiler import compile_skill
from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.config import get_settings
from apps.api.extraction.extractor import _detect_topic, extract_artifact
from apps.api.graph.synthesis import synthesize
from apps.api.models.tables import Artifact, KnowledgeUnit, KUProvenance, Source
from apps.api.resolver.resolver import sync_resolver
from apps.api.services.ingest import ensure_source


def add_text_knowledge(
    db: Session,
    org_id: str | None = None,
    *,
    text: str,
    source_name: str = "Manual entry",
    author: str = "console",
) -> dict:
    org_id = org_id or get_settings().default_org_id
    text = (text or "").strip()
    if not text:
        return {"error": "empty text"}

    src: Source = ensure_source(db, org_id=org_id, kind="manual", name=source_name)
    external_id = "manual-" + hashlib.sha256(text.encode()).hexdigest()[:16]

    existing = db.scalar(
        select(Artifact).where(
            Artifact.org_id == org_id, Artifact.source_id == src.id, Artifact.external_id == external_id
        )
    )
    if existing:
        artifact = existing
    else:
        artifact = Artifact(
            org_id=org_id,
            source_id=src.id,
            external_id=external_id,
            kind="manual_note",
            raw_jsonb={"title": source_name},
            content_text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            author=author,
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(artifact)
        db.flush()

    # Only (re)extract if this artifact has no KUs yet.
    has_kus = db.scalar(select(KUProvenance).where(KUProvenance.artifact_id == artifact.id)) is not None
    units = [] if has_kus else extract_artifact(db, artifact)
    db.commit()

    synthesize(db, org_id)

    topic = _detect_topic(text)
    recompiled = []
    topics = [topic] if topic in SKILL_TEMPLATES else list(SKILL_TEMPLATES)
    for t in topics:
        s = compile_skill(db, org_id, t)
        if s:
            recompiled.append({"slug": s.slug, "version": s.version, "status": s.status})
    sync_resolver(db, org_id)

    return {
        "artifact_id": artifact.id,
        "detected_topic": topic,
        "units_created": [
            {"type": u.type, "statement": u.statement, "status": u.status, "confidence": u.confidence}
            for u in units
        ],
        "recompiled": recompiled,
    }
