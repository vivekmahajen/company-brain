"""Per-tenant brain scorecard (Phase 8 / GTM differentiation).

Every competitor reports recall on a public benchmark. We report *each customer's*
brain health and governance posture on *their* data: how complete, fresh, governed,
and routable their knowledge is, plus a single readiness score. This is the closing
argument — a number on the buyer's own brain, not ours.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models.tables import KnowledgeUnit, KUProvenance, Policy, Skill, Source


def _latest_skills(db: Session, org_id: str) -> list[Skill]:
    rows = db.scalars(select(Skill).where(Skill.org_id == org_id).order_by(Skill.version.desc())).all()
    seen, out = set(), []
    for s in rows:
        if s.slug in seen or s.status == "deprecated":
            continue
        seen.add(s.slug)
        out.append(s)
    return out


def _ratio(n: int, d: int) -> float:
    return round(n / d, 3) if d else 0.0


def tenant_scorecard(db: Session, org_id: str) -> dict:
    from apps.api.compiler.registry import get_templates
    from apps.api.freshness.engine import detect_supersession_staleness
    from apps.api.resolver.resolver import lint_resolver

    skills = _latest_skills(db, org_id)
    approved_skills = [s for s in skills if s.status == "approved"]
    needs_review_skills = [s for s in skills if s.status == "needs_review"]

    # knowledge by status
    def kcount(**w):
        q = select(func.count(KnowledgeUnit.id)).where(KnowledgeUnit.org_id == org_id)
        for k, v in w.items():
            q = q.where(getattr(KnowledgeUnit, k) == v)
        return db.scalar(q) or 0

    ku_total = kcount()
    ku_approved = kcount(status="approved")
    ku_review = kcount(status="needs_review")
    ku_superseded = kcount(status="superseded")

    # provenance coverage over approved KUs
    approved_ids = select(KnowledgeUnit.id).where(
        KnowledgeUnit.org_id == org_id, KnowledgeUnit.status == "approved")
    with_prov = db.scalar(select(func.count(func.distinct(KUProvenance.knowledge_unit_id)))
                          .where(KUProvenance.knowledge_unit_id.in_(approved_ids))) or 0
    prov_coverage = _ratio(with_prov, ku_approved)

    # guardrails (governance signal)
    guardrails = sum(1 for k in db.scalars(select(KnowledgeUnit).where(
        KnowledgeUnit.org_id == org_id, KnowledgeUnit.status == "approved")).all()
        if (k.payload_jsonb or {}).get("kind") == "guardrail")
    policies = db.scalar(select(func.count(Policy.id)).where(Policy.org_id == org_id)) or 0

    # capabilities coverage
    templates = get_templates(db, org_id)
    compiled_slugs = {s.slug for s in skills}
    capabilities_compiled = sum(1 for t in templates.values() if t["slug"] in compiled_slugs)

    # sources
    sources = db.scalars(select(Source).where(Source.org_id == org_id)).all()
    synced = sum(1 for s in sources if s.last_synced_at)

    # health flags
    unroutable = lint_resolver(db, org_id)
    staleness = detect_supersession_staleness(db, org_id)

    # sub-scores → readiness
    review_score = _ratio(len(approved_skills), len(approved_skills) + len(needs_review_skills)) if skills else 0.0
    coverage_score = _ratio(capabilities_compiled, len(templates))
    routable_score = 1.0 if skills and not unroutable else (0.0 if skills else 0.0)
    governance_score = min(1.0, (1.0 if guardrails else 0.0) * 0.5 + (1.0 if policies else 0.0) * 0.5)
    fresh_score = 1.0 if not staleness else max(0.0, 1.0 - 0.2 * len(staleness))
    readiness = round(100 * (review_score + coverage_score + routable_score + governance_score + fresh_score) / 5, 1)

    return {
        "org_id": org_id,
        "readiness": readiness,  # 0..100
        "skills": {"total": len(skills), "approved": len(approved_skills),
                   "needs_review": len(needs_review_skills)},
        "knowledge": {"total": ku_total, "approved": ku_approved, "needs_review": ku_review,
                      "superseded": ku_superseded, "provenance_coverage": prov_coverage},
        "capabilities": {"total": len(templates), "compiled": capabilities_compiled},
        "governance": {"guardrails": guardrails, "policies": int(policies)},
        "sources": {"total": len(sources), "synced": synced},
        "health": {"unroutable_skills": unroutable, "staleness_signals": len(staleness)},
        "subscores": {"review": review_score, "coverage": coverage_score,
                      "routable": routable_score, "governance": governance_score, "freshness": fresh_score},
    }
