"""ACL resolution with default-deny / fail-closed (VIS-1).

`can_access_source` is the atomic permission predicate: a principal may read a
source iff a current `source_acl` allow matches one of their groups/identity and
no deny matches. No ACL rows ⇒ no access (default-deny).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.access import Membership, SourceACL


def caller_groups(db: Session, org_id: str, principal_id: str) -> set[str]:
    rows = db.scalars(
        select(Membership).where(Membership.org_id == org_id, Membership.principal_id == principal_id)
    ).all()
    return {r.group_id for r in rows}


def _source_acls(db: Session, org_id: str, source_id: str) -> list[SourceACL]:
    return db.scalars(
        select(SourceACL).where(SourceACL.org_id == org_id, SourceACL.source_id == source_id)
    ).all()


def source_allow_groups(db: Session, org_id: str, source_id: str) -> set[str]:
    """Groups explicitly allowed on a source (for console/audience display)."""
    return {a.subject_id for a in _source_acls(db, org_id, source_id)
            if a.access == "allow" and a.subject_kind == "group"}


def can_access_source(db: Session, org_id: str, principal_id: str, groups: set[str], source_id: str) -> bool:
    acls = _source_acls(db, org_id, source_id)
    if not acls:
        return False  # default-deny (VIS-1)
    # explicit deny wins
    for a in acls:
        if a.access != "deny":
            continue
        if (a.subject_kind == "principal" and a.subject_id == principal_id) or (
            a.subject_kind == "group" and a.subject_id in groups
        ):
            return False
    for a in acls:
        if a.access != "allow":
            continue
        if (a.subject_kind == "principal" and a.subject_id == principal_id) or (
            a.subject_kind == "group" and a.subject_id in groups
        ):
            return True
    return False
