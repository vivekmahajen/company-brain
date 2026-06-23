"""M5 — RESOLVER (routing layer).

Maintains one resolver entry per skill (intents + keywords + priority +
embedding), generates the canonical RESOLVER.md, and routes a natural-language
task to the right skill via a hybrid score (keyword/intent match + embedding
similarity, LLM tie-break seam). Enforces the no-dark-capability rule: every
skill must be routable or `lint_resolver` fails (wired into CI).
"""
from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.config import get_settings
from apps.api.llm.embeddings import cosine, embed
from apps.api.models.tables import ResolverEntry, Skill

_SLUG_TO_TMPL = {t["slug"]: t for t in SKILL_TEMPLATES.values()}


def _latest_skills(db: Session, org_id: str) -> list[Skill]:
    rows = db.scalars(select(Skill).where(Skill.org_id == org_id).order_by(Skill.version.desc())).all()
    seen, out = set(), []
    for s in rows:
        if s.slug in seen or s.status == "deprecated":
            continue
        seen.add(s.slug)
        out.append(s)
    return out


def upsert_entry(db: Session, skill: Skill) -> ResolverEntry:
    tmpl = _SLUG_TO_TMPL.get(skill.slug, {})
    intents = tmpl.get("intents", [skill.title])
    keywords = tmpl.get("keywords", skill.slug.split("-"))
    entry = db.scalar(
        select(ResolverEntry).where(ResolverEntry.org_id == skill.org_id, ResolverEntry.slug == skill.slug)
    )
    text_for_embed = " ".join([skill.title, skill.summary, *intents, *keywords])
    if entry:
        entry.skill_id = skill.id
        entry.intents_jsonb = intents
        entry.keywords_jsonb = keywords
        entry.embedding = embed(text_for_embed)
    else:
        entry = ResolverEntry(
            org_id=skill.org_id,
            skill_id=skill.id,
            slug=skill.slug,
            intents_jsonb=intents,
            keywords_jsonb=keywords,
            priority=100,
            embedding=embed(text_for_embed),
        )
        db.add(entry)
    db.flush()
    return entry


def sync_resolver(db: Session, org_id: str) -> dict:
    """Ensure every skill is routable, then (re)write RESOLVER.md."""
    skills = _latest_skills(db, org_id)
    for s in skills:
        upsert_entry(db, s)
    db.commit()
    write_resolver_md(db, org_id)
    return {"entries": len(skills)}


def lint_resolver(db: Session, org_id: str) -> list[str]:
    """Return slugs of skills with no resolver entry. Non-empty => CI failure."""
    skills = _latest_skills(db, org_id)
    entries = {e.slug for e in db.scalars(select(ResolverEntry).where(ResolverEntry.org_id == org_id)).all()}
    return [s.slug for s in skills if s.slug not in entries]


def resolve(db: Session, org_id: str, task: str, top_k: int = 3) -> list[dict]:
    task_low = task.lower()
    qvec = embed(task)
    entries = db.scalars(select(ResolverEntry).where(ResolverEntry.org_id == org_id)).all()
    ranked = []
    for e in entries:
        kw_hits = [k for k in e.keywords_jsonb if k.lower() in task_low]
        intent_hits = [i for i in e.intents_jsonb if any(w in task_low for w in i.lower().split() if len(w) > 3)]
        kw_score = min(1.0, 0.34 * len(kw_hits))
        intent_score = min(1.0, 0.2 * len(intent_hits))
        sem_score = max(0.0, cosine(qvec, e.embedding or []))
        # weighted hybrid; small priority nudge
        score = 0.5 * kw_score + 0.2 * intent_score + 0.3 * sem_score + (100 - e.priority) * 0.0001
        reason_bits = []
        if kw_hits:
            reason_bits.append(f"matched keywords {kw_hits}")
        if intent_hits:
            reason_bits.append(f"matched intent “{intent_hits[0]}”")
        reason_bits.append(f"semantic similarity {sem_score:.2f}")
        skill = db.get(Skill, e.skill_id)
        ranked.append(
            {
                "slug": e.slug,
                "skill_id": e.skill_id,
                "title": skill.title if skill else e.slug,
                "score": round(score, 3),
                "confidence": round(min(1.0, score), 3),
                "reason": "; ".join(reason_bits),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def write_resolver_md(db: Session, org_id: str) -> str:
    entries = db.scalars(
        select(ResolverEntry).where(ResolverEntry.org_id == org_id).order_by(ResolverEntry.priority)
    ).all()
    lines = [
        "# RESOLVER",
        "",
        "> Generated canonical routing index (M5). Every skill MUST appear here.",
        "> A compile that leaves a skill unroutable fails CI.",
        "",
        "| Skill | Intents | Keywords | Priority |",
        "|---|---|---|---|",
    ]
    for e in entries:
        skill = db.get(Skill, e.skill_id)
        title = skill.title if skill else e.slug
        lines.append(
            f"| `{e.slug}` — {title} | {'; '.join(e.intents_jsonb)} | "
            f"{', '.join(e.keywords_jsonb)} | {e.priority} |"
        )
    content = "\n".join(lines) + "\n"
    path = get_settings().resolver_path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
