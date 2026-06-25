"""SQLAlchemy models for the §3 data model.

Every table is multi-tenant (`org_id`). Provenance tables are append-only.
Knowledge units are bitemporal (`valid_from` / `valid_to`) so the Brain can
answer "what was the policy in March?" and supersede rather than delete.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.db import Base, Embedding


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# WHO the knowledge belongs to (tenant registry)
# --------------------------------------------------------------------------
class Org(Base):
    """A tenant. Every other table is scoped by `org_id` (a string); this is the
    registry of those ids so we can create/list tenants and validate an inbound
    org. The default demo org is `Settings.default_org_id`."""
    __tablename__ = "org"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")  # active|suspended
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------
# WHERE knowledge comes from
# --------------------------------------------------------------------------
class Source(Base):
    __tablename__ = "source"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # slack|notion|...
    name: Mapped[str] = mapped_column(String, nullable=False)
    config_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="connected")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "artifact"
    __table_args__ = (
        UniqueConstraint("org_id", "source_id", "external_id", name="uq_artifact_external"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    raw_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    content_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)
    author: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------
# ATOMIC structured knowledge
# --------------------------------------------------------------------------
KU_TYPES = {
    "entity",
    "relationship",
    "fact",
    "policy_rule",
    "procedure_step",
    "metric_definition",
    "glossary_term",
}


class KnowledgeUnit(Base):
    __tablename__ = "knowledge_unit"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    payload_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding = mapped_column(Embedding, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # draft | needs_review | approved | superseded
    status: Mapped[str] = mapped_column(String, default="draft")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # supersession audit: which KU replaced this one
    superseded_by: Mapped[str | None] = mapped_column(String)
    topic: Mapped[str | None] = mapped_column(String, index=True)  # routing/grouping key

    provenance: Mapped[list["KUProvenance"]] = relationship(
        back_populates="knowledge_unit", cascade="all, delete-orphan"
    )


class KUProvenance(Base):
    """Append-only. EVERY knowledge_unit links to >=1 artifact. No orphan facts."""

    __tablename__ = "ku_provenance"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    knowledge_unit_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_unit.id"), nullable=False, index=True
    )
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifact.id"), nullable=False)
    quote_span: Mapped[str] = mapped_column(Text, default="")
    extracted_by: Mapped[str] = mapped_column(String, default="extractor")
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    knowledge_unit: Mapped[KnowledgeUnit] = relationship(back_populates="provenance")


# --------------------------------------------------------------------------
# TYPED GRAPH
# --------------------------------------------------------------------------
class Entity(Base):
    __tablename__ = "entity"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    aliases_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    attributes_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding = mapped_column(Embedding, nullable=True)


class Edge(Base):
    __tablename__ = "edge"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    src_entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False)
    dst_entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String, nullable=False)
    properties_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


# --------------------------------------------------------------------------
# COMPILED OUTPUT
# --------------------------------------------------------------------------
class Skill(Base):
    __tablename__ = "skill"
    __table_args__ = (UniqueConstraint("org_id", "slug", "version", name="uq_skill_version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    frontmatter_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # draft | needs_review | approved | deprecated
    status: Mapped[str] = mapped_column(String, default="draft")
    compiled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    source_ku_ids_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    # hash of constituent approved KUs -> determinism guard (§7)
    content_signature: Mapped[str] = mapped_column(String, default="")

    bindings: Mapped[list["SkillBinding"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillBinding(Base):
    __tablename__ = "skill_binding"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_schema_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    side_effecting: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # optional expression, e.g. "amount > 500"
    approval_expression: Mapped[str | None] = mapped_column(String)

    skill: Mapped[Skill] = relationship(back_populates="bindings")


class ResolverEntry(Base):
    __tablename__ = "resolver_entry"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    intents_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    keywords_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    embedding = mapped_column(Embedding, nullable=True)


# --------------------------------------------------------------------------
# GOVERNANCE & LIFECYCLE
# --------------------------------------------------------------------------
class Policy(Base):
    __tablename__ = "policy"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    rule_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    enforcement: Mapped[str] = mapped_column(String, default="block")  # block|warn|log


class Review(Base):
    __tablename__ = "review"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    reviewer: Mapped[str] = mapped_column(String, default="")
    decision: Mapped[str] = mapped_column(String, default="")  # approve|reject|defer
    note: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StalenessSignal(Base):
    __tablename__ = "staleness_signal"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionLog(Base):
    __tablename__ = "execution_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    skill_id: Mapped[str | None] = mapped_column(String)
    agent_id: Mapped[str | None] = mapped_column(String)
    input_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    output_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String, default="")
    expected_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    drift_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # MCP serving-layer enrichment (§4)
    principal_id: Mapped[str | None] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String, index=True)
    gate_decision: Mapped[str | None] = mapped_column(String)
    approval_request_id: Mapped[str | None] = mapped_column(String, index=True)
    transport: Mapped[str | None] = mapped_column(String)
    trace_id: Mapped[str | None] = mapped_column(String)
