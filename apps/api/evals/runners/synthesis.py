"""E2 — Synthesis. Deterministic checks on the REAL synthesizer: dedup collapses,
supersession retires bitemporally + auditably, conflicts resolve, no false merges.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.evals.loader import load_cases
from apps.api.graph.synthesis import synthesize
from apps.api.llm.embeddings import embed
from apps.api.models.tables import Artifact, KnowledgeUnit, KUProvenance, Source


def _parse_dt(s: str | None):
    if not s:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _seed_inputs(db: Session, org: str, inputs: list[dict]) -> None:
    src = Source(org_id=org, kind="manual", name="synth-eval")
    db.add(src)
    db.flush()
    art = Artifact(org_id=org, source_id=src.id, external_id="synth", kind="manual_note",
                   content_text="x", content_hash=f"hash-{org}")
    db.add(art)
    db.flush()
    for u in inputs:
        ku = KnowledgeUnit(
            org_id=org, type=u["type"], statement=u["statement"], payload_jsonb=u.get("payload", {}),
            embedding=embed(u["statement"]), confidence=u.get("confidence", 0.9), status="approved",
            valid_from=_parse_dt(u.get("occurred_at")), topic=u.get("topic"),
        )
        db.add(ku)
        db.flush()
        db.add(KUProvenance(knowledge_unit_id=ku.id, artifact_id=art.id, quote_span=u["statement"]))
    db.commit()


def _active(db, org):
    return db.scalars(select(KnowledgeUnit).where(
        KnowledgeUnit.org_id == org, KnowledgeUnit.valid_to.is_(None))).all()


def _check(db: Session, case: dict, run_tag: str = "") -> tuple[bool, dict]:
    org = f"eval-synth-{run_tag}-{case['id']}"
    _seed_inputs(db, org, case["inputs"])
    synthesize(db, org)
    exp = case["expected"]
    active = _active(db, org)
    detail = {}

    if "canonical_amount_threshold" in exp:
        mgr = [k for k in active if (k.payload_jsonb or {}).get("action") == "manager_approval"]
        thr = (mgr[0].payload_jsonb or {}).get("amount_threshold") if mgr else None
        detail["threshold"] = thr
        if thr != exp["canonical_amount_threshold"]:
            return False, detail
    if "canonical_percent_threshold" in exp:
        mgr = [k for k in active if (k.payload_jsonb or {}).get("action") == "manager_approval"]
        thr = (mgr[0].payload_jsonb or {}).get("percent_threshold") if mgr else None
        detail["percent"] = thr
        if thr != exp["canonical_percent_threshold"]:
            return False, detail
    if exp.get("superseded_retired"):
        sup = db.scalars(select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org, KnowledgeUnit.status == "superseded")).all()
        if not sup or any(s.valid_to is None for s in sup):
            return False, {**detail, "superseded": len(sup)}
        if exp.get("supersession_auditable") and any(not s.superseded_by for s in sup):
            return False, {**detail, "audit": "missing superseded_by"}
    if "active_count_for_action" in exp:
        n = sum(1 for k in active if (k.payload_jsonb or {}).get("action") == exp["canonical_action"])
        detail["active_count"] = n
        if n != exp["active_count_for_action"]:
            return False, detail
    if "merged_provenance_min" in exp:
        winner = [k for k in active if (k.payload_jsonb or {}).get("action") == exp["canonical_action"]]
        prov = len(db.scalars(select(KUProvenance).where(
            KUProvenance.knowledge_unit_id == winner[0].id)).all()) if winner else 0
        detail["provenance"] = prov
        if prov < exp["merged_provenance_min"]:
            return False, detail
    if "distinct_active_actions" in exp:
        actions = sorted({(k.payload_jsonb or {}).get("action") for k in active
                          if (k.payload_jsonb or {}).get("action")})
        detail["actions"] = actions
        if actions != sorted(exp["distinct_active_actions"]):
            return False, detail
    return True, detail


def run(db: Session, split: str | None = "test", run_tag: str = "") -> list[dict]:
    results = []
    for case in load_cases("synthesis", split):
        try:
            ok, detail = _check(db, case, run_tag)
            results.append({
                "stage": "synthesis", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": ok, "judge_used": False, "error": None, "detail": detail,
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "synthesis", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
