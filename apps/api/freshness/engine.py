"""M6 — Freshness / currency engine.

Keeps the Brain current: when new knowledge supersedes a KU that backs an
approved skill, raise a staleness_signal and recompile (producing a new
needs_review version diffed against the old). Also time-based TTL staleness and a
nightly full recompile pass (the "wiki compiler").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.models.tables import KnowledgeUnit, Skill, StalenessSignal


def _open_signal_exists(db: Session, org_id: str, target_type: str, target_id: str, reason: str) -> bool:
    return (
        db.scalar(
            select(StalenessSignal).where(
                StalenessSignal.org_id == org_id,
                StalenessSignal.target_type == target_type,
                StalenessSignal.target_id == target_id,
                StalenessSignal.reason == reason,
                StalenessSignal.resolved_at.is_(None),
            )
        )
        is not None
    )


def detect_supersession_staleness(db: Session, org_id: str) -> list[StalenessSignal]:
    """Flag skills whose constituent KUs have been superseded/retired."""
    signals: list[StalenessSignal] = []
    rows = db.scalars(select(Skill).where(Skill.org_id == org_id)).all()
    seen = set()
    for skill in rows:
        if skill.slug in seen:
            continue
        seen.add(skill.slug)
        for ku_id in skill.source_ku_ids_jsonb or []:
            ku = db.get(KnowledgeUnit, ku_id)
            if ku and (ku.valid_to is not None or ku.status == "superseded"):
                reason = f"source KU {ku_id[:8]} superseded; recompile required"
                if not _open_signal_exists(db, org_id, "skill", skill.id, reason):
                    sig = StalenessSignal(org_id=org_id, target_type="skill", target_id=skill.id, reason=reason)
                    db.add(sig)
                    signals.append(sig)
                break
    db.commit()
    return signals


def detect_ttl_staleness(db: Session, org_id: str) -> list[StalenessSignal]:
    ttl = timedelta(days=get_settings().skill_ttl_days)
    cutoff = datetime.now(timezone.utc) - ttl
    signals = []
    for skill in db.scalars(select(Skill).where(Skill.org_id == org_id)).all():
        compiled = skill.compiled_at
        if compiled and compiled.tzinfo is None:
            compiled = compiled.replace(tzinfo=timezone.utc)
        if compiled and compiled < cutoff:
            reason = f"skill exceeded TTL of {get_settings().skill_ttl_days}d"
            if not _open_signal_exists(db, org_id, "skill", skill.id, reason):
                sig = StalenessSignal(org_id=org_id, target_type="skill", target_id=skill.id, reason=reason)
                db.add(sig)
                signals.append(sig)
    db.commit()
    return signals


def open_signals(db: Session, org_id: str | None = None) -> list[dict]:
    org_id = org_id or get_settings().default_org_id
    rows = db.scalars(
        select(StalenessSignal).where(StalenessSignal.org_id == org_id, StalenessSignal.resolved_at.is_(None))
    ).all()
    return [
        {
            "id": s.id,
            "target_type": s.target_type,
            "target_id": s.target_id,
            "reason": s.reason,
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
        }
        for s in rows
    ]
