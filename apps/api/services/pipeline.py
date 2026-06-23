"""End-to-end orchestrator: ingest → extract → synthesize → compile → route.

This is the loop the build prompt asks to prove. Idempotent: safe to re-run.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.compiler.skill_compiler import compile_skill
from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.config import get_settings
from apps.api.extraction.extractor import extract_pending
from apps.api.freshness.engine import detect_supersession_staleness
from apps.api.governance.policy import seed_default_policies
from apps.api.graph.synthesis import synthesize
from apps.api.resolver.resolver import lint_resolver, sync_resolver
from apps.api.services.ingest import sync_default_sources


def run_full_pipeline(db: Session, org_id: str | None = None) -> dict:
    org_id = org_id or get_settings().default_org_id
    seed_default_policies(db, org_id)

    ingest = sync_default_sources(db, org_id)
    extract = extract_pending(db, org_id)
    synth = synthesize(db, org_id)

    # Compile every capability that has knowledge (data-driven, not refund-only).
    skills = []
    for topic in SKILL_TEMPLATES:
        s = compile_skill(db, org_id, topic)
        if s:
            skills.append({"slug": s.slug, "version": s.version, "status": s.status})

    resolver = sync_resolver(db, org_id)
    staleness = detect_supersession_staleness(db, org_id)
    unroutable = lint_resolver(db, org_id)

    # Serving layer: principals + server-side order facts + approve demo skills.
    from apps.api.services.serving import seed_serving

    seed_serving(db, org_id)

    return {
        "ingest": ingest,
        "extract": extract,
        "synthesis": synth,
        # Back-compat: `skill` is the refund skill; `skills` is all compiled.
        "skill": next((s for s in skills if s["slug"] == "handle-refund"), None),
        "skills": skills,
        "resolver": resolver,
        "staleness_signals": len(staleness),
        "unroutable_skills": unroutable,
    }
