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


_DRAFT_RUBRIC = (
    "You design a capability template for a company-operations 'skill'. Given a one-line "
    "description of a workflow, return JSON with these fields:\n"
    '{"topic": "<snake_case identifier>", "title": "<short imperative title>", '
    '"description": "<one sentence>", "inputs": ["name (type, required|optional)", ...], '
    '"tools": [{"name": "<verb_noun>", "side_effecting": true, "approval_for_action": '
    '"manager_approval"|null, "approval_field": "<input field>"|null, "threshold_kind": '
    '"amount"|"percent"|"days"|null}], "intents": ["<natural phrasing>", ...], '
    '"keywords": ["<routing keyword>", ...]}\n'
    "Keep it minimal and realistic. JSON only."
)

_STOP = {"the", "a", "an", "to", "of", "for", "and", "or", "when", "with", "that", "this",
         "request", "requests", "handle", "process", "manage", "our", "their", "any", "is", "are"}


def _heuristic_draft(desc: str) -> dict:
    words = [w.strip(".,;:!?").lower() for w in desc.split()]
    sig = [w for w in words if len(w) > 3 and w not in _STOP and w.isalpha()]
    topic = (sig[0] if sig else "capability")
    title = desc.strip().rstrip(".")[:60] or f"Handle {topic}"
    return {
        "topic": re.sub(r"[^a-z0-9]+", "_", topic),
        "title": title[0].upper() + title[1:] if title else title,
        "description": desc.strip(),
        "inputs": [],
        "tools": [],
        "intents": [desc.strip()],
        "keywords": sig[:6] or [topic],
        "drafted_by": "heuristic",
    }


def _normalize_draft(d: dict, desc: str) -> dict:
    base = _heuristic_draft(desc)
    return {
        "topic": re.sub(r"[^a-z0-9]+", "_", str(d.get("topic") or base["topic"]).lower()).strip("_"),
        "title": str(d.get("title") or base["title"]),
        "description": str(d.get("description") or desc.strip()),
        "inputs": d.get("inputs") if isinstance(d.get("inputs"), list) else [],
        "tools": d.get("tools") if isinstance(d.get("tools"), list) else [],
        "intents": d.get("intents") if isinstance(d.get("intents"), list) else [desc.strip()],
        "keywords": [str(k).lower() for k in (d.get("keywords") or base["keywords"]) if k],
        "drafted_by": "model",
    }


def draft_template(description: str) -> dict:
    """Draft a capability template from a one-line description. Uses the real model
    when LLM_PROVIDER=anthropic; otherwise a deterministic heuristic (offline). The
    draft is NOT saved — the caller reviews and POSTs it to create."""
    from apps.api.config import get_settings

    desc = (description or "").strip()
    if not desc:
        return {"error": "description is required"}
    draft = _heuristic_draft(desc)
    if get_settings().llm_provider.lower() == "anthropic":
        try:
            from apps.api.llm.base import get_llm

            r = get_llm().complete_json(system=_DRAFT_RUBRIC, prompt=desc,
                                        model=get_settings().model_extract)
            if isinstance(r.data, dict) and r.data.get("topic") and r.data.get("title"):
                draft = _normalize_draft(r.data, desc)
        except Exception:  # noqa: BLE001 - fall back to the heuristic draft
            pass
    if draft["topic"] in BUILTIN_TOPICS:
        draft["topic"] = f"{draft['topic']}_custom"
    return draft


def delete_template(db: Session, org_id: str, topic: str) -> dict:
    row = db.scalar(select(SkillTemplate).where(
        SkillTemplate.org_id == org_id, SkillTemplate.topic == topic.lower()))
    if not row:
        return {"error": "not found"}  # built-ins aren't deletable (not in this table)
    db.delete(row)
    db.commit()
    return {"deleted": topic}
