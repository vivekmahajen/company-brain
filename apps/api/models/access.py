"""Access-control schema (§3): groups, memberships, source/skill ACLs, the
visibility-label cache, and the access audit log. Permissions propagate along the
derivation chain and are enforced at serve time (see apps/api/access/)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Group(Base):
    __tablename__ = "group_"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="mirrored")  # mirrored | brain


class Membership(Base):
    __tablename__ = "membership"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    principal_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    group_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    source_of_truth: Mapped[str] = mapped_column(String, default="brain")  # mirror:slack | brain


class RoleGrant(Base):
    __tablename__ = "role_grant"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    principal_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)


class SourceACL(Base):
    __tablename__ = "source_acl"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)  # group_id or principal_id
    subject_kind: Mapped[str] = mapped_column(String, default="group")  # group | principal
    access: Mapped[str] = mapped_column(String, default="allow")  # allow | deny
    origin: Mapped[str] = mapped_column(String, default="mirror")  # mirror | brain


class SkillACL(Base):
    """Brain-level narrowing grant on a compiled skill — can only RESTRICT further."""

    __tablename__ = "skill_acl"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)
    subject_kind: Mapped[str] = mapped_column(String, default="group")
    access: Mapped[str] = mapped_column(String, default="allow")


class VisibilityLabel(Base):
    """Materialized audience cache (NOT source of truth, VIS-4). lineage_hash
    invalidates it when source ACLs / lineage change."""

    __tablename__ = "visibility_label"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    # list of required source-audience group-sets (a conjunction; viewer must
    # satisfy each) — stored for console display + fast filtering.
    requirements_jsonb: Mapped[list] = mapped_column(JSON, default=list)
    lineage_hash: Mapped[str] = mapped_column(String, default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AccessLog(Base):
    __tablename__ = "access_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    principal_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, default="")  # resolve|get_skill|invoke|...
    target_type: Mapped[str] = mapped_column(String, default="")
    target_id: Mapped[str] = mapped_column(String, default="")
    decision: Mapped[str] = mapped_column(String, default="")  # allow | deny
    reason: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
