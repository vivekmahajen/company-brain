"""Bottom-up visibility propagation along the derivation chain (§4, VIS-3).

A derived object's audience is the MOST RESTRICTIVE intersection of its inputs:
a viewer must be able to read EVERY source a skill draws on. Computed at serve
time against current ACLs (VIS-4); `visibility_label` is only a display cache.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.access.acl import source_allow_groups
from apps.api.models.tables import Artifact, KnowledgeUnit, KUProvenance, Skill


def ku_sources(db: Session, ku_id: str) -> set[str]:
    rows = db.scalars(select(KUProvenance).where(KUProvenance.knowledge_unit_id == ku_id)).all()
    out = set()
    for p in rows:
        art = db.get(Artifact, p.artifact_id)
        if art:
            out.add(art.source_id)
    return out


def skill_sources(db: Session, skill: Skill) -> set[str]:
    """The set of sources the skill draws on (the conjunction it requires)."""
    sources: set[str] = set()
    for ku_id in skill.source_ku_ids_jsonb or []:
        sources |= ku_sources(db, ku_id)
    return sources


def lineage_hash(db: Session, org_id: str, sources: set[str]) -> str:
    """Hash of sources + their current allow-groups; changes on any ACL edit so a
    cached label is invalidated (VIS-4)."""
    parts = []
    for sid in sorted(sources):
        groups = sorted(source_allow_groups(db, org_id, sid))
        parts.append(f"{sid}:{','.join(groups)}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def ku_audience_sources(db: Session, ku: KnowledgeUnit) -> set[str]:
    return ku_sources(db, ku.id)
