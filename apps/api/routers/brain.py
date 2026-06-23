"""REST mirror of the agent + console surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.freshness.engine import open_signals
from apps.api.models.db import get_session
from apps.api.models.tables import (
    Artifact,
    Edge,
    Entity,
    KnowledgeUnit,
    KUProvenance,
    Skill,
    Source,
)
from apps.api.governance.policy import create_policy, delete_policy, list_policies
from apps.api.monitor.drift import list_drift, record_observed_outcome
from apps.api.resolver.resolver import lint_resolver
from apps.api.services.execution import execute_tool, get_skill, list_skills, resolve_task
from apps.api.services.knowledge import add_text_knowledge
from apps.api.services.pipeline import run_full_pipeline

router = APIRouter()


def _org() -> str:
    return get_settings().default_org_id


# --- pipeline / sources ----------------------------------------------------
@router.post("/pipeline/run")
def pipeline_run(db: Session = Depends(get_session)):
    return run_full_pipeline(db, _org())


@router.post("/admin/reseed-serving")
def admin_reseed_serving(db: Session = Depends(get_session)):
    """Make the deployed server MCP-ready: (re)build the brain, seed principals +
    order facts, and approve the demo skills so they're servable. Idempotent."""
    from apps.api.services.serving import approve_demo_skills, seed_serving

    org = _org()
    report = run_full_pipeline(db, org)
    seed_serving(db, org)
    approve_demo_skills(db, org)
    return {"reseeded": True, "org": org, "skills": report.get("skills")}


@router.get("/sources")
def sources(db: Session = Depends(get_session)):
    rows = db.scalars(select(Source).where(Source.org_id == _org())).all()
    return [
        {
            "id": s.id,
            "kind": s.kind,
            "name": s.name,
            "status": s.status,
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None,
        }
        for s in rows
    ]


@router.get("/artifacts")
def artifacts(db: Session = Depends(get_session)):
    rows = db.scalars(select(Artifact).where(Artifact.org_id == _org())).all()
    return [
        {"id": a.id, "kind": a.kind, "author": a.author, "content_text": a.content_text}
        for a in rows
    ]


# --- knowledge -------------------------------------------------------------
@router.get("/knowledge")
def knowledge(db: Session = Depends(get_session)):
    rows = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.org_id == _org())).all()
    out = []
    for k in rows:
        prov = db.scalars(select(KUProvenance).where(KUProvenance.knowledge_unit_id == k.id)).all()
        out.append(
            {
                "id": k.id,
                "type": k.type,
                "statement": k.statement,
                "payload": k.payload_jsonb,
                "confidence": k.confidence,
                "status": k.status,
                "topic": k.topic,
                "valid_to": k.valid_to.isoformat() if k.valid_to else None,
                "superseded_by": k.superseded_by,
                "provenance": [{"artifact_id": p.artifact_id, "span": p.quote_span} for p in prov],
            }
        )
    return out


@router.get("/graph")
def graph(db: Session = Depends(get_session)):
    ents = db.scalars(select(Entity).where(Entity.org_id == _org())).all()
    edges = db.scalars(select(Edge).where(Edge.org_id == _org())).all()
    return {
        "entities": [{"id": e.id, "type": e.type, "name": e.canonical_name} for e in ents],
        "edges": [{"src": e.src_entity_id, "dst": e.dst_entity_id, "relation": e.relation} for e in edges],
    }


# --- skills ----------------------------------------------------------------
@router.get("/skills")
def skills(db: Session = Depends(get_session)):
    return list_skills(db, _org())


@router.get("/skills/{slug}")
def skill_detail(slug: str, db: Session = Depends(get_session)):
    return get_skill(db, slug, _org())


@router.get("/skills/{slug}/versions")
def skill_versions(slug: str, db: Session = Depends(get_session)):
    rows = db.scalars(
        select(Skill).where(Skill.org_id == _org(), Skill.slug == slug).order_by(Skill.version)
    ).all()
    return [{"version": s.version, "status": s.status, "body_md": s.body_md} for s in rows]


class ReviewDecision(BaseModel):
    decision: str  # approve | deprecate


@router.post("/skills/{slug}/review")
def review_skill(slug: str, body: ReviewDecision, db: Session = Depends(get_session)):
    s = db.scalars(
        select(Skill).where(Skill.org_id == _org(), Skill.slug == slug).order_by(Skill.version.desc())
    ).first()
    if not s:
        return {"error": "not found"}
    s.status = "approved" if body.decision == "approve" else "deprecated"
    db.commit()
    return {"slug": slug, "version": s.version, "status": s.status}


# --- resolver --------------------------------------------------------------
class ResolveBody(BaseModel):
    task: str


@router.post("/resolve")
def resolve_endpoint(body: ResolveBody, db: Session = Depends(get_session)):
    return {"task": body.task, "routes": resolve_task(db, body.task, _org())}


@router.get("/resolver/lint")
def resolver_lint(db: Session = Depends(get_session)):
    unroutable = lint_resolver(db, _org())
    return {"unroutable_skills": unroutable, "ok": not unroutable}


# --- execution -------------------------------------------------------------
class ExecBody(BaseModel):
    slug: str
    tool: str
    inputs: dict
    agent_id: str = "rest-agent"


@router.post("/execute")
def execute_endpoint(body: ExecBody, db: Session = Depends(get_session)):
    return execute_tool(db, body.slug, body.tool, body.inputs, agent_id=body.agent_id, org_id=_org())


# --- governance: policies (M8) --------------------------------------------
@router.get("/policies")
def policies_list(db: Session = Depends(get_session)):
    return list_policies(db, _org())


class PolicyBody(BaseModel):
    name: str
    tool: str
    when: str  # e.g. "amount > 500" or "discount_percent > 20"
    require: str = "human_approval"
    enforcement: str = "block"  # block | warn | log


@router.post("/policies")
def policies_create(body: PolicyBody, db: Session = Depends(get_session)):
    return create_policy(
        db,
        _org(),
        name=body.name,
        tool=body.tool,
        when=body.when,
        require=body.require,
        enforcement=body.enforcement,
    )


@router.delete("/policies/{policy_id}")
def policies_delete(policy_id: str, db: Session = Depends(get_session)):
    return delete_policy(db, _org(), policy_id)


# --- knowledge: manual add ------------------------------------------------
class AddKnowledgeBody(BaseModel):
    text: str
    source_name: str = "Manual entry"


@router.post("/knowledge/add")
def knowledge_add(body: AddKnowledgeBody, db: Session = Depends(get_session)):
    return add_text_knowledge(db, _org(), text=body.text, source_name=body.source_name)


# --- evals (CBE scorecard) ------------------------------------------------
@router.get("/evals/latest")
def evals_latest(db: Session = Depends(get_session)):
    from apps.api.models.serving import EvalRun

    run = db.scalars(select(EvalRun).order_by(EvalRun.started_at.desc())).first()
    return run.scorecard_jsonb if run else {"error": "no eval runs yet — run `make eval`"}


@router.get("/evals/runs")
def evals_runs(db: Session = Depends(get_session)):
    from apps.api.models.serving import EvalRun

    rows = db.scalars(select(EvalRun).order_by(EvalRun.started_at.desc())).all()[:50]
    return [
        {
            "id": r.id,
            "commit_sha": r.commit_sha,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "GAR": (r.scorecard_jsonb or {}).get("headline", {}).get("GAR"),
            "SEC": (r.scorecard_jsonb or {}).get("headline", {}).get("SEC"),
        }
        for r in rows
    ]


@router.get("/evals/runs/{run_id}/failures")
def evals_failures(run_id: str, db: Session = Depends(get_session)):
    from apps.api.models.serving import EvalResult

    rows = db.scalars(
        select(EvalResult).where(EvalResult.eval_run_id == run_id, EvalResult.passed.is_(False))
    ).all()
    return [
        {"stage": r.eval_stage, "case_id": r.case_id, "tier": r.tier, "error": r.error, "detail": r.metric_jsonb}
        for r in rows
    ]


# --- governance / monitoring ----------------------------------------------
@router.get("/staleness")
def staleness(db: Session = Depends(get_session)):
    return open_signals(db, _org())


@router.get("/drift")
def drift(db: Session = Depends(get_session)):
    return list_drift(db, _org())


class ObservedOutcome(BaseModel):
    tool: str
    inputs: dict
    actual_outcome: str
    skill_slug: str | None = None


@router.post("/monitor/observe")
def observe(body: ObservedOutcome, db: Session = Depends(get_session)):
    skill_id = None
    if body.skill_slug:
        s = get_skill(db, body.skill_slug, _org())
        skill_id = s.get("slug") if s else None
    return record_observed_outcome(
        db,
        org_id=_org(),
        skill_id=skill_id,
        tool_name=body.tool,
        inputs=body.inputs,
        actual_outcome=body.actual_outcome,
    )
