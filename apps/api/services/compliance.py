"""Data portability + right-to-erasure (Phase 5 / GDPR).

export_tenant: a portable JSON dump of a tenant's data (credentials redacted).
delete_tenant: irreversibly purge every row belonging to an org — child tables first
(FK-safe), then all org_id-scoped tables, then the org record itself.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.tables import (
    Artifact,
    KnowledgeUnit,
    KUProvenance,
    Org,
    Policy,
    Skill,
    SkillBinding,
    Source,
)


def export_tenant(db: Session, org_id: str) -> dict:
    from apps.api.audit.log import list_audit
    from apps.api.billing.metering import get_plan, usage_summary
    from apps.api.compiler.registry import get_templates
    from apps.api.services.connections import _source_view

    sources = db.scalars(select(Source).where(Source.org_id == org_id)).all()
    kus = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.org_id == org_id).limit(5000)).all()
    skills = db.scalars(select(Skill).where(Skill.org_id == org_id)).all()
    policies = db.scalars(select(Policy).where(Policy.org_id == org_id)).all()
    custom = [t for t in get_templates(db, org_id).values() if t.get("custom")]

    return {
        "org_id": org_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "plan": get_plan(db, org_id),
        "usage": usage_summary(db, org_id)["usage"],
        "sources": [_source_view(db, s) for s in sources],  # secrets never included
        "knowledge_units": [{"type": k.type, "statement": k.statement, "status": k.status,
                             "topic": k.topic, "confidence": k.confidence} for k in kus],
        "skills": [{"slug": s.slug, "version": s.version, "status": s.status, "body_md": s.body_md}
                   for s in skills],
        "policies": [{"name": p.name, "rule": p.rule_jsonb, "enforcement": p.enforcement} for p in policies],
        "custom_capabilities": custom,
        "audit": list_audit(db, org_id, limit=1000),
    }


def delete_tenant(db: Session, org_id: str) -> dict:
    """Irreversibly delete all data for an org. Returns per-table deleted counts."""
    from apps.api.models.db import Base
    from apps.api.models.serving import EvalResult, EvalRun

    # 1) child tables that lack org_id — delete via their org-scoped parents (FK-safe).
    ku_ids = select(KnowledgeUnit.id).where(KnowledgeUnit.org_id == org_id)
    art_ids = select(Artifact.id).where(Artifact.org_id == org_id)
    skill_ids = select(Skill.id).where(Skill.org_id == org_id)
    run_ids = select(EvalRun.id).where(EvalRun.org_id == org_id)
    kup = KUProvenance.__table__
    db.execute(kup.delete().where(kup.c.knowledge_unit_id.in_(ku_ids) | kup.c.artifact_id.in_(art_ids)))
    sb = SkillBinding.__table__
    db.execute(sb.delete().where(sb.c.skill_id.in_(skill_ids)))
    er = EvalResult.__table__
    db.execute(er.delete().where(er.c.eval_run_id.in_(run_ids)))

    # 2) every org_id-scoped table, children before parents.
    deleted: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):
        if "org_id" in table.columns.keys():
            res = db.execute(table.delete().where(table.c.org_id == org_id))
            if res.rowcount:
                deleted[table.name] = res.rowcount

    # 3) the org record itself.
    res = db.execute(Org.__table__.delete().where(Org.__table__.c.id == org_id))
    if res.rowcount:
        deleted["org"] = res.rowcount

    db.commit()
    return {"org_id": org_id, "deleted": deleted}
