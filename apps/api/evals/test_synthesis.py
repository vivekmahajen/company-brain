"""§9: dedup collapses duplicates; a later decision supersedes auditably."""
from sqlalchemy import select

from apps.api.models.tables import KnowledgeUnit


def test_auto_approve_rules_collapsed(seeded, db, org_id):
    # The two differently-worded 30-day auto-approve rules collapse to one active.
    active = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id,
            KnowledgeUnit.type == "policy_rule",
            KnowledgeUnit.valid_to.is_(None),
        )
    ).all()
    auto = [k for k in active if (k.payload_jsonb or {}).get("action") == "auto_approve"]
    assert len(auto) == 1, f"expected 1 canonical auto-approve rule, got {len(auto)}"


def test_threshold_supersession_auditable(seeded, db, org_id):
    # The legacy $300 manager-approval rule was superseded by the $500 rule.
    superseded = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id,
            KnowledgeUnit.status == "superseded",
        )
    ).all()
    assert superseded, "expected at least one superseded KU"
    for k in superseded:
        assert k.valid_to is not None
        assert k.superseded_by, "supersession must record the winning KU (auditable)"

    # The winning manager-approval rule carries the $500 threshold.
    active = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id,
            KnowledgeUnit.valid_to.is_(None),
        )
    ).all()
    mgr = [k for k in active if (k.payload_jsonb or {}).get("action") == "manager_approval"]
    assert any((k.payload_jsonb or {}).get("amount_threshold") == 500 for k in mgr)
