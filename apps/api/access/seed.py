"""Seed the access model: groups, memberships, and mirrored source ACLs (§6).

Mirrors each source's native permissions via the connector's `pull_acls()`.
Idempotent; safe to re-run (revocation tests delete memberships explicitly).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.principals import hash_token
from apps.api.config import get_settings
from apps.api.connectors.registry import get_connector
from apps.api.models.access import Group, Membership, SourceACL
from apps.api.models.serving import Principal
from apps.api.models.tables import Source

GROUPS = ["all-staff", "support-team", "sales-team", "eng-team"]

# token (base) → group names. Default-org tokens are clean; other orgs prefixed.
# Admin (agent/human) belong to every group; role agents to their domain only.
TOKEN_GROUPS = {
    "agent-token": ["support-team", "all-staff", "sales-team", "eng-team"],
    "agent-readonly-token": ["support-team", "all-staff"],
    "human-token": ["support-team", "all-staff", "sales-team", "eng-team"],
    "agent-support-token": ["support-team", "all-staff"],
    "agent-sales-token": ["sales-team", "all-staff"],
    "agent-eng-token": ["eng-team", "all-staff"],
}


def _ensure_group(db: Session, org_id: str, name: str) -> Group:
    g = db.scalar(select(Group).where(Group.org_id == org_id, Group.name == name))
    if not g:
        g = Group(org_id=org_id, name=name, kind="mirrored")
        db.add(g)
        db.flush()
    return g


def _token_for(org_id: str, base: str) -> str:
    settings = get_settings()
    return base if org_id == settings.default_org_id else f"{org_id}:{base}"


def seed_access(db: Session, org_id: str | None = None) -> None:
    org_id = org_id or get_settings().default_org_id
    groups = {name: _ensure_group(db, org_id, name) for name in GROUPS}

    # Memberships (idempotent).
    for base, group_names in TOKEN_GROUPS.items():
        p = db.scalar(
            select(Principal).where(Principal.org_id == org_id,
                                    Principal.token_hash == hash_token(_token_for(org_id, base)))
        )
        if not p:
            continue
        for gname in group_names:
            gid = groups[gname].id
            exists = db.scalar(select(Membership).where(
                Membership.org_id == org_id, Membership.principal_id == p.id, Membership.group_id == gid))
            if not exists:
                db.add(Membership(org_id=org_id, principal_id=p.id, group_id=gid,
                                  source_of_truth="mirror"))
    db.commit()

    # Mirror source-native ACLs (re-sync each run, VIS-7).
    for src in db.scalars(select(Source).where(Source.org_id == org_id)).all():
        try:
            acl_groups = get_connector(src.kind, src.config_jsonb).pull_acls().get("groups", [])
        except Exception:  # noqa: BLE001 - unknown connector ⇒ default-deny
            acl_groups = []
        for gname in acl_groups:
            gid = _ensure_group(db, org_id, gname).id
            exists = db.scalar(select(SourceACL).where(
                SourceACL.org_id == org_id, SourceACL.source_id == src.id,
                SourceACL.subject_id == gid, SourceACL.origin == "mirror"))
            if not exists:
                db.add(SourceACL(org_id=org_id, source_id=src.id, subject_id=gid,
                                 subject_kind="group", access="allow", origin="mirror"))
    db.commit()
