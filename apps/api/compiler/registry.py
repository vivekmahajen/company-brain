"""Template registry — built-in (code) + per-tenant (DB) capability templates.

Built-in templates (compiler/templates.py) are shared by every tenant. A customer
can add their own capability *shapes* (Phase 3) as SkillTemplate rows; this module
merges them so the compiler, pipeline, scheduler, resolver, and extractor see one
unified set per org. Custom templates win on topic collision (a tenant can override
a built-in for itself, never for others).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.templates import BUILTIN_TOPIC_KEYWORDS, SKILL_TEMPLATES
from apps.api.models.tables import SkillTemplate

BUILTIN_TOPICS = set(SKILL_TEMPLATES)


def _row_to_template(t: SkillTemplate) -> dict:
    return {
        "slug": t.slug,
        "title": t.title,
        "description": t.description,
        "inputs": t.inputs_jsonb or [],
        "tools": t.tools_jsonb or [],
        "intents": t.intents_jsonb or [],
        "keywords": t.keywords_jsonb or [],
        "custom": True,
    }


def get_templates(db: Session, org_id: str) -> dict[str, dict]:
    """All capability templates visible to this org: built-ins + its own."""
    merged: dict[str, dict] = {k: {**v, "custom": False} for k, v in SKILL_TEMPLATES.items()}
    for t in db.scalars(select(SkillTemplate).where(SkillTemplate.org_id == org_id)).all():
        merged[t.topic] = _row_to_template(t)
    return merged


def slug_to_template(db: Session, org_id: str) -> dict[str, dict]:
    return {tpl["slug"]: tpl for tpl in get_templates(db, org_id).values()}


def topic_keywords(db: Session, org_id: str) -> dict[str, tuple[str, ...]]:
    """Document-level topic detection map: built-in keywords + each custom template's
    keywords, so extraction attaches custom-topic artifacts to the right capability."""
    out: dict[str, tuple[str, ...]] = dict(BUILTIN_TOPIC_KEYWORDS)
    for t in db.scalars(select(SkillTemplate).where(SkillTemplate.org_id == org_id)).all():
        kws = tuple(k.lower() for k in (t.keywords_jsonb or []) if k)
        if kws:
            out[t.topic] = kws
    return out
