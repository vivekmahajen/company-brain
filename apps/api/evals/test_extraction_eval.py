"""§7/§9: extraction precision/recall, low-confidence routes to review."""
from sqlalchemy import select

from apps.api.evals.golden import extraction_metrics
from apps.api.models.tables import KnowledgeUnit


def _active(db, org_id):
    rows = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id, KnowledgeUnit.valid_to.is_(None)
        )
    ).all()
    return [(k.type, k.statement) for k in rows]


def test_extraction_recall(seeded, db, org_id):
    metrics = extraction_metrics(_active(db, org_id))
    print("\nEXTRACTION METRICS:", metrics)
    assert metrics["recall"] == 1.0, f"missed expected KUs: {metrics}"
    assert metrics["precision"] >= 0.9


def test_low_confidence_routes_to_review(seeded, db, org_id):
    # KUs below the confidence threshold must not be auto-approved.
    rows = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.org_id == org_id)).all()
    from apps.api.config import get_settings

    thr = get_settings().confidence_review_threshold
    for k in rows:
        if k.status == "approved":
            assert k.confidence >= thr
