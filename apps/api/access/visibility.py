"""VisibilityFilter — the single enforcement choke point (§5, VIS-2).

Every read path (MCP resolve/list/get/invoke, REST reads, console) routes through
this. Default-deny, fail-closed, serve-time authoritative against current ACLs.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.access.acl import can_access_source, caller_groups
from apps.api.access.audit import log_decision
from apps.api.access.propagation import skill_sources
from apps.api.models.access import SkillACL
from apps.api.models.serving import Principal
from apps.api.models.tables import Artifact, KnowledgeUnit, KUProvenance, Skill, Source


class VisibilityFilter:
    def __init__(self, db: Session, principal: Principal) -> None:
        self.db = db
        self.principal = principal
        self.org_id = principal.org_id
        self._groups = caller_groups(db, principal.org_id, principal.id)

    # -- core predicate -----------------------------------------------------
    def _skill_visible(self, skill: Skill) -> tuple[bool, str]:
        sources = skill_sources(self.db, skill)
        if not sources:
            return False, "no lineage (fail-closed)"
        # brain-level narrowing (can only restrict, VIS-3 / §3 skill_acl)
        acls = self.db.scalars(
            select(SkillACL).where(SkillACL.org_id == self.org_id, SkillACL.skill_id == skill.id)
        ).all()
        for a in acls:
            if a.access == "deny" and (a.subject_id in self._groups or a.subject_id == self.principal.id):
                return False, "skill_acl deny"
        allow_acls = [a for a in acls if a.access == "allow"]
        if allow_acls and not any(a.subject_id in self._groups or a.subject_id == self.principal.id for a in allow_acls):
            return False, "skill_acl narrowing (not granted)"
        # intersection: must be able to read EVERY source (VIS-3)
        for sid in sources:
            if not can_access_source(self.db, self.org_id, self.principal.id, self._groups, sid):
                return False, f"cannot read source {sid[:8]} in lineage"
        return True, "all lineage sources accessible"

    def visible(self, target_type: str, target_id: str, *, action: str = "get", log: bool = True) -> bool:
        if target_type == "skill":
            skill = self.db.get(Skill, target_id)
            if not skill:
                ok, reason = False, "not found"
            else:
                ok, reason = self._skill_visible(skill)
        elif target_type == "knowledge_unit":
            ok, reason = self._ku_visible(target_id)
        else:
            ok, reason = False, "unknown target type (fail-closed)"
        if log:
            log_decision(self.db, org_id=self.org_id, principal_id=self.principal.id, action=action,
                         target_type=target_type, target_id=target_id,
                         decision="allow" if ok else "deny", reason=reason)
        return ok

    def visible_slug(self, slug: str, *, action: str = "get", log: bool = True) -> Skill | None:
        skill = self.db.scalars(
            select(Skill).where(Skill.org_id == self.org_id, Skill.slug == slug, Skill.status == "approved")
            .order_by(Skill.version.desc())
        ).first()
        if not skill:
            return None
        return skill if self.visible("skill", skill.id, action=action, log=log) else None

    def _ku_visible(self, ku_id: str) -> tuple[bool, str]:
        ku = self.db.get(KnowledgeUnit, ku_id)
        if not ku:
            return False, "not found"
        sources = set()
        for p in self.db.scalars(select(KUProvenance).where(KUProvenance.knowledge_unit_id == ku_id)).all():
            art = self.db.get(Artifact, p.artifact_id)
            if art:
                sources.add(art.source_id)
        if not sources:
            return False, "no provenance (fail-closed)"
        for sid in sources:
            if not can_access_source(self.db, self.org_id, self.principal.id, self._groups, sid):
                return False, "source restricted"
        return True, "accessible"

    # -- bulk ---------------------------------------------------------------
    def filter_skills(self, skills: list[Skill]) -> list[Skill]:
        return [s for s in skills if self._skill_visible(s)[0]]

    def filter_knowledge(self, kus: list[KnowledgeUnit]) -> list[KnowledgeUnit]:
        return [k for k in kus if self._ku_visible(k.id)[0]]

    # -- provenance (VIS-6) -------------------------------------------------
    def filter_provenance(self, skill: Skill) -> list[dict]:
        """Per-viewer provenance: only spans from sources the caller can read."""
        out = []
        for ku_id in skill.source_ku_ids_jsonb or []:
            prov = self.db.scalars(
                select(KUProvenance).where(KUProvenance.knowledge_unit_id == ku_id)
            ).first()
            if not prov:
                continue
            art = self.db.get(Artifact, prov.artifact_id)
            if not art or not can_access_source(self.db, self.org_id, self.principal.id, self._groups, art.source_id):
                continue  # redacted
            src = self.db.get(Source, art.source_id)
            when = art.occurred_at.date().isoformat() if art and art.occurred_at else ""
            label = f"{src.kind}/{(art.raw_jsonb.get('channel') or art.raw_jsonb.get('title') or src.name)}" if src else "?"
            out.append({"ku": ku_id[:8], "source": f"{label} {when}".strip(),
                        "span": (prov.quote_span or "")[:60]})
        return out

    # -- display ------------------------------------------------------------
    def audience_requirements(self, skill: Skill) -> list[dict]:
        from apps.api.access.acl import source_allow_groups

        reqs = []
        for sid in skill_sources(self.db, skill):
            src = self.db.get(Source, sid)
            groups = sorted(source_allow_groups(self.db, self.org_id, sid))
            reqs.append({"source": src.name if src else sid, "kind": src.kind if src else "?",
                         "allow_groups": groups})
        return reqs
