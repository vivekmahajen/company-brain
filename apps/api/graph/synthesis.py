"""M3 — Knowledge graph: dedup & synthesis.

Collapse the noisy KU stream into a single, current, non-contradictory map:
  - Deduplicate equivalent rules (same canonical signature + equal thresholds):
    merge provenance onto one canonical, retire the others.
  - Resolve conflicts (same signature, different thresholds): the most recent /
    highest-provenance unit wins; the loser is retired bitemporally
    (valid_to=now, superseded_by=winner) — never silently dropped.
Supersession is auditable via `superseded_by` + a staleness/audit record.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.llm.embeddings import cosine
from apps.api.models.tables import KnowledgeUnit, KUProvenance

ACTIVE = ("approved", "needs_review", "draft")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _signature(ku: KnowledgeUnit) -> tuple:
    p = ku.payload_jsonb or {}
    topic = ku.topic or "_"
    if ku.type == "policy_rule":
        if p.get("action"):
            return (topic, "policy_rule", p["action"])
        if p.get("kind") == "guardrail":
            return (topic, "guardrail", _norm(p.get("constraint", ku.statement)))
    if ku.type == "procedure_step":
        return (topic, "procedure_step", p.get("step_number"))
    return (topic, ku.type, _norm(ku.statement))


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _thresholds(ku: KnowledgeUnit) -> dict:
    p = ku.payload_jsonb or {}
    return {
        "amount": p.get("amount_threshold", p.get("amount_gt", p.get("amount"))),
        "days": p.get("days_window", p.get("days")),
    }


def _equivalent(a: KnowledgeUnit, b: KnowledgeUnit) -> bool:
    return _thresholds(a) == _thresholds(b)


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rank_key(ku: KnowledgeUnit):
    """Winner = most recent, then highest confidence, then most provenance."""
    return (_aware(ku.valid_from), ku.confidence, len(ku.provenance))


def _retire(db: Session, loser: KnowledgeUnit, winner: KnowledgeUnit, reason: str) -> None:
    loser.status = "superseded"
    loser.valid_to = _now()
    loser.superseded_by = winner.id
    # merge provenance onto the winner so no source citation is lost
    for prov in list(loser.provenance):
        db.add(
            KUProvenance(
                knowledge_unit_id=winner.id,
                artifact_id=prov.artifact_id,
                quote_span=prov.quote_span,
                extracted_by=f"merged:{reason}",
            )
        )


def synthesize(db: Session, org_id: str) -> dict:
    kus = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id, KnowledgeUnit.status.in_(ACTIVE)
        )
    ).all()

    groups: dict[tuple, list[KnowledgeUnit]] = {}
    for ku in kus:
        groups.setdefault(_signature(ku), []).append(ku)

    merged = 0
    superseded = 0
    audit: list[dict] = []
    for sig, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=_rank_key, reverse=True)
        winner = members[0]
        for loser in members[1:]:
            if _equivalent(winner, loser):
                _retire(db, loser, winner, "duplicate")
                merged += 1
                audit.append({"winner": winner.id, "loser": loser.id, "kind": "duplicate", "signature": list(sig)})
            else:
                _retire(db, loser, winner, "conflict")
                superseded += 1
                audit.append(
                    {
                        "winner": winner.id,
                        "loser": loser.id,
                        "kind": "conflict",
                        "signature": list(sig),
                        "winner_thresholds": _thresholds(winner),
                        "loser_thresholds": _thresholds(loser),
                    }
                )
    db.commit()
    return {"groups": len(groups), "merged_duplicates": merged, "superseded_conflicts": superseded, "audit": audit}


def resolve_entities(db: Session, org_id: str, threshold: float = 0.82) -> dict:
    """Lightweight entity clustering placeholder for Phase 1 (extend in Phase 2)."""
    return {"clustered": 0, "threshold": threshold}
