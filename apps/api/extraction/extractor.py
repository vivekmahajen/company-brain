"""M2 — Extraction & structuring.

Turn raw artifacts into typed knowledge_units with provenance. A cheap Haiku
pre-classifier gates whether an artifact is knowledge-bearing before spending
Opus tokens. Every unit carries an embedding, a confidence, and >=1 provenance
row (quote_span). Below-threshold units land as `needs_review` (M8 gating);
others as `approved`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.llm.base import get_llm
from apps.api.llm.embeddings import embed
from apps.api.llm.prompts import EXTRACTION_SYSTEM
from apps.api.models.tables import KU_TYPES, Artifact, KnowledgeUnit, KUProvenance

# Capability topics, matched by keyword on the artifact. Each maps to a compile
# template in compiler/templates.py. Adding a capability = add a row here + a
# template + (optional) fixtures — no engine changes.
_TOPIC_KEYWORDS = {
    "refund": ("refund", "chargeback", "money back"),
    "pricing": ("discount", "pricing", "price exception", "deal desk"),
    "incident": ("incident", "outage", "on-call", "on call", "sev1", "sev 1", "post-mortem"),
}


def _detect_topic(text: str, keywords: dict | None = None) -> str | None:
    low = text.lower()
    for topic, kws in (keywords or _TOPIC_KEYWORDS).items():
        if any(k in low for k in kws):
            return topic
    return None


def extract_artifact(db: Session, artifact: Artifact, *, llm=None, topic_keywords: dict | None = None) -> list[KnowledgeUnit]:
    llm = llm or get_llm()
    settings = get_settings()

    # Cheap gate: is this artifact knowledge-bearing at all?
    label = llm.classify(text=artifact.content_text, labels=["knowledge", "chatter"])
    if label != "knowledge":
        return []

    # Document-level topic so units that don't repeat the keyword (e.g. a
    # guardrail, a bare procedure step) still attach to the right capability.
    doc_topic = _detect_topic(artifact.content_text, topic_keywords)

    resp = llm.complete_json(
        system=EXTRACTION_SYSTEM,
        prompt="Extract typed knowledge units.",
        model=settings.model_extract,
        context={
            "task": "extract",
            "artifact_text": artifact.content_text,
            "occurred_at": str(artifact.occurred_at) if artifact.occurred_at else None,
            "topic": doc_topic,
        },
    )
    units_raw = resp.data.get("units", []) if isinstance(resp.data, dict) else []

    created: list[KnowledgeUnit] = []
    for u in units_raw:
        ku_type = u.get("type")
        if ku_type not in KU_TYPES:
            continue
        statement = (u.get("statement") or "").strip()
        if not statement:
            continue
        confidence = float(u.get("confidence", 0.5))
        status = "approved" if confidence >= settings.confidence_review_threshold else "needs_review"
        ku = KnowledgeUnit(
            org_id=artifact.org_id,
            type=ku_type,
            statement=statement,
            payload_jsonb=u.get("payload", {}),
            embedding=embed(statement),
            confidence=confidence,
            status=status,
            valid_from=artifact.occurred_at,
            topic=u.get("topic") or doc_topic,
        )
        db.add(ku)
        db.flush()
        # No fact without provenance.
        db.add(
            KUProvenance(
                knowledge_unit_id=ku.id,
                artifact_id=artifact.id,
                quote_span=u.get("quote_span", statement),
                extracted_by=f"{settings.llm_provider}:{settings.model_extract}",
            )
        )
        created.append(ku)
    db.flush()
    return created


def _provider_cost_usd() -> float:
    """Process-wide model spend so far (0.0 on the fixture provider, which never
    instantiates the real client). Used to attribute the extraction's real cost."""
    try:
        from apps.api.llm.anthropic_client import AnthropicClient

        return AnthropicClient.TOTAL.cost_usd
    except Exception:  # noqa: BLE001 - no anthropic client ⇒ no spend
        return 0.0


def extract_pending(db: Session, org_id: str) -> dict:
    """Extract from all artifacts that have no KUs yet. Metered + budget-guarded:
    skips extraction when the tenant is over its monthly extraction budget (Phase 6)."""
    from apps.api.billing.metering import record_usage
    from apps.api.billing.quota import check_quota
    from apps.api.compiler.registry import topic_keywords

    ok, reason = check_quota(db, org_id, "extraction")
    if not ok:
        return {"artifacts_processed": 0, "units_created": 0, "cost_usd": 0.0, "over_budget": reason}

    llm = get_llm()
    tkw = topic_keywords(db, org_id)  # built-in + this tenant's custom topics
    artifacts = db.scalars(select(Artifact).where(Artifact.org_id == org_id)).all()
    existing_artifact_ids = {
        p.artifact_id for p in db.scalars(select(KUProvenance)).all()
    }
    total_units = 0
    processed = 0
    cost_before = _provider_cost_usd()
    for art in artifacts:
        if art.id in existing_artifact_ids:
            continue
        units = extract_artifact(db, art, llm=llm, topic_keywords=tkw)
        total_units += len(units)
        processed += 1
    cost = round(_provider_cost_usd() - cost_before, 6)
    if cost > 0:
        record_usage(db, org_id, "extraction", cost_usd=cost)
    db.commit()
    return {"artifacts_processed": processed, "units_created": total_units, "cost_usd": cost}
