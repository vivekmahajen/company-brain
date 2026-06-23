"""Schema for the MCP serving layer (§4): principals, approval requests, and a
small Order store that provides the *server-side* facts the gates evaluate (INV-2).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Principal(Base):
    """Maps an MCP credential to an org + role + scopes (§9)."""

    __tablename__ = "principal"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="agent")  # agent | human | service
    display_name: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="agent")
    scopes_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    token_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")  # active | disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApprovalRequest(Base):
    """A held side effect awaiting human approval (§4, INV-3/INV-4)."""

    __tablename__ = "approval_request"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_approval_idem"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    skill_id: Mapped[str | None] = mapped_column(String)
    binding_id: Mapped[str | None] = mapped_column(String)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_principal: Mapped[str] = mapped_column(String, nullable=False)
    input_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_facts_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    gate_reason: Mapped[str] = mapped_column(Text, default="")
    # pending | approved | rejected | executed | expired
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    decided_by_principal: Mapped[str | None] = mapped_column(String)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_jsonb: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Order(Base):
    """Server-side ground truth for refund facts (INV-2). In a real deployment this
    is a Postgres reader/connector over the orders DB; here it's a seeded table."""

    __tablename__ = "order_record"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    order_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    original_charge: Mapped[float] = mapped_column(Float, default=0.0)
    age_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="paid")
