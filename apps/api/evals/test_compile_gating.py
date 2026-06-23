"""A freshly compiled side-effecting skill is needs_review (never auto-approved).

Isolated org with NO serving approval step, so we observe the compiler's default.
"""
from apps.api.compiler.skill_compiler import compile_skill
from apps.api.extraction.extractor import extract_pending
from apps.api.graph.synthesis import synthesize
from apps.api.models.db import SessionLocal, init_db
from apps.api.services.ingest import sync_default_sources

ORG = "00000000-0000-0000-0000-0000000000bb"


def test_side_effecting_skill_compiles_needs_review():
    db = SessionLocal()
    try:
        init_db()
        sync_default_sources(db, ORG)
        extract_pending(db, ORG)
        synthesize(db, ORG)
        skill = compile_skill(db, ORG, "refund")
        assert skill.status == "needs_review", "side-effecting skill must not auto-approve"
    finally:
        db.close()
