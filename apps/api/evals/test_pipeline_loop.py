"""§9: connectors land artifacts with provenance; extraction is idempotent."""
from sqlalchemy import select

from apps.api.models.tables import Artifact, KnowledgeUnit, KUProvenance
from apps.api.services.ingest import sync_default_sources


def test_artifacts_landed(seeded, db, org_id):
    arts = db.scalars(select(Artifact).where(Artifact.org_id == org_id)).all()
    assert len(arts) == 5  # 3 slack + 2 notion
    assert all(a.content_hash for a in arts)


def test_no_orphan_knowledge_units(seeded, db, org_id):
    kus = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.org_id == org_id)).all()
    assert kus, "expected knowledge units"
    for ku in kus:
        prov = db.scalars(select(KUProvenance).where(KUProvenance.knowledge_unit_id == ku.id)).all()
        assert prov, f"KU {ku.id} has no provenance (no fact without provenance)"


def test_ingest_idempotent(seeded, db, org_id):
    before = len(db.scalars(select(Artifact).where(Artifact.org_id == org_id)).all())
    results = sync_default_sources(db, org_id)
    after = len(db.scalars(select(Artifact).where(Artifact.org_id == org_id)).all())
    assert after == before
    assert all(r["inserted"] == 0 for r in results)
