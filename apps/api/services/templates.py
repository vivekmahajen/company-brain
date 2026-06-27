"""Customer-authored capability templates (Phase 3).

A tenant defines a new skill *shape* (inputs, tools, routing intents/keywords);
the compiler then fills it from that tenant's knowledge, exactly like a built-in.
Tenant-scoped; built-in topics/slugs are reserved.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.registry import BUILTIN_TOPICS, get_templates
from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.models.tables import SkillTemplate

_BUILTIN_SLUGS = {t["slug"] for t in SKILL_TEMPLATES.values()}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "skill"


def list_templates(db: Session, org_id: str) -> list[dict]:
    out = []
    for topic, t in get_templates(db, org_id).items():
        out.append({"topic": topic, "slug": t["slug"], "title": t["title"],
                    "description": t.get("description", ""), "inputs": t.get("inputs", []),
                    "tools": [tool.get("name") for tool in t.get("tools", [])],
                    "intents": t.get("intents", []), "keywords": t.get("keywords", []),
                    "custom": t.get("custom", False)})
    return out


def create_template(db: Session, org_id: str, *, topic: str, title: str, description: str = "",
                    inputs: list | None = None, tools: list | None = None,
                    intents: list | None = None, keywords: list | None = None,
                    slug: str | None = None) -> dict:
    topic = (topic or "").strip().lower()
    if not topic or not title.strip():
        return {"error": "topic and title are required"}
    if topic in BUILTIN_TOPICS:
        return {"error": f"'{topic}' is a built-in topic — choose a different name"}
    if db.scalar(select(SkillTemplate).where(SkillTemplate.org_id == org_id, SkillTemplate.topic == topic)):
        return {"error": f"template '{topic}' already exists"}
    slug = _slugify(slug or topic)
    existing_slugs = {t["slug"] for t in get_templates(db, org_id).values()} | _BUILTIN_SLUGS
    if slug in existing_slugs:
        return {"error": f"slug '{slug}' is taken"}

    row = SkillTemplate(
        org_id=org_id, topic=topic, slug=slug, title=title.strip(), description=description or "",
        inputs_jsonb=inputs or [], tools_jsonb=tools or [],
        intents_jsonb=intents or [title.strip()],
        keywords_jsonb=[k.lower() for k in (keywords or [topic])],
    )
    db.add(row)
    db.commit()
    return {"topic": topic, "slug": slug, "title": row.title, "custom": True,
            "next": "add knowledge for this topic, then it compiles into a skill"}


def delete_template(db: Session, org_id: str, topic: str) -> dict:
    row = db.scalar(select(SkillTemplate).where(
        SkillTemplate.org_id == org_id, SkillTemplate.topic == topic.lower()))
    if not row:
        return {"error": "not found"}  # built-ins aren't deletable (not in this table)
    db.delete(row)
    db.commit()
    return {"deleted": topic}
