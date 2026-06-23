"""Adding governance policies + ad-hoc knowledge (the 'add new policies' flows).

Isolated to its own org so live mutations don't affect the shared seeded org.
"""
from apps.api.governance.policy import check_policies, create_policy, delete_policy, list_policies
from apps.api.models.db import SessionLocal, init_db
from apps.api.services.execution import execute_tool, get_skill
from apps.api.services.knowledge import add_text_knowledge
from apps.api.services.pipeline import run_full_pipeline

ORG = "00000000-0000-0000-0000-0000000000aa"


def _seed(db):
    init_db()
    run_full_pipeline(db, ORG)


def test_governance_policy_crud_and_enforcement():
    db = SessionLocal()
    try:
        _seed(db)
        # Add a brand-new guardrail: refunds over $1000 always blocked.
        res = create_policy(db, ORG, name="refund_ceiling", tool="stripe_refund", when="amount > 1000", require="vp_approval")
        assert "id" in res
        assert any(p["name"] == "refund_ceiling" for p in list_policies(db, ORG))

        # It is enforced at execution time.
        check = check_policies(db, ORG, "stripe_refund", {"amount": 1500})
        assert check["allowed"] is False
        assert check["rule"] in ("refund_ceiling", "refund_high_value")

        # Bad expression is rejected, not stored.
        bad = create_policy(db, ORG, name="oops", tool="x", when="not a real expr")
        assert "error" in bad

        # Delete works.
        assert delete_policy(db, ORG, res["id"])["deleted"] is True
    finally:
        db.close()


def test_add_text_knowledge_recompiles_skill():
    db = SessionLocal()
    try:
        _seed(db)
        before = get_skill(db, "handle-refund", ORG)["version"]

        # A fresh decision raising the auto-approval window to 45 days.
        out = add_text_knowledge(
            db,
            ORG,
            text="Update: refunds within 45 days of purchase are now automatically approved.",
        )
        assert out["detected_topic"] == "refund"
        assert out["units_created"], "expected at least one extracted KU"

        after = get_skill(db, "handle-refund", ORG)["version"]
        assert after > before, "adding knowledge should recompile the skill"
        assert "45 days" in get_skill(db, "handle-refund", ORG)["body_md"]
    finally:
        db.close()
