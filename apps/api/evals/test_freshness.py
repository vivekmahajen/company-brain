"""§9: editing the policy raises a staleness signal -> recompile path.

Uses a dedicated org so the mutation doesn't pollute the shared seeded fixture.
"""
from datetime import datetime, timezone

from apps.api.compiler.skill_compiler import compile_skill
from apps.api.freshness.engine import detect_supersession_staleness, open_signals
from apps.api.graph.synthesis import synthesize
from apps.api.llm.embeddings import embed
from apps.api.models.db import SessionLocal
from apps.api.models.tables import KnowledgeUnit
from apps.api.services.pipeline import run_full_pipeline

FRESH_ORG = "00000000-0000-0000-0000-0000000000ff"


def test_new_decision_raises_staleness_and_recompiles():
    db = SessionLocal()
    try:
        run_full_pipeline(db, FRESH_ORG)
        before = compile_skill(db, FRESH_ORG, "refund")
        before_version = before.version

        # Simulate a fresh Slack decision: high-value threshold raised to $1000.
        ku = KnowledgeUnit(
            org_id=FRESH_ORG,
            type="policy_rule",
            statement="Going forward, refunds above $1000 require manager sign-off.",
            payload_jsonb={"action": "manager_approval", "amount_threshold": 1000, "amount_gt": 1000},
            embedding=embed("refunds above $1000 require manager sign-off"),
            confidence=0.95,
            status="approved",
            topic="refund",
            valid_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        db.add(ku)
        db.commit()

        synthesize(db, FRESH_ORG)  # supersedes the old $500 rule
        detect_supersession_staleness(db, FRESH_ORG)
        assert open_signals(db, FRESH_ORG), "expected a staleness signal after supersession"

        after = compile_skill(db, FRESH_ORG, "refund")
        assert after.version > before_version, "a changed policy must bump the skill version"
        assert "1000" in after.body_md
    finally:
        db.close()
