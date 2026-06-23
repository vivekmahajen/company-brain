"""Build per-skill native MCP tool schemas from approved bindings (§5).

Each wrapper (e.g. `handle-refund__stripe_refund`) is a thin native tool whose
only behavior is to call `invoke_skill_tool` with the matching skill/tool — so
there is no second execution path (INV-1).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.tables import Skill, SkillBinding


def visible_approved_skills(db: Session, org_id: str) -> list[Skill]:
    rows = db.scalars(
        select(Skill).where(Skill.org_id == org_id, Skill.status == "approved").order_by(Skill.version.desc())
    ).all()
    seen, out = set(), []
    for s in rows:
        if s.slug in seen:
            continue
        seen.add(s.slug)
        out.append(s)
    return out


def _wrapper_schema(binding: SkillBinding) -> dict:
    base = dict(binding.tool_schema_jsonb or {"type": "object", "properties": {}})
    props = dict(base.get("properties", {}))
    props["idempotency_key"] = {"type": "string", "description": "Dedup key; reuse to safely retry."}
    props["approval_id"] = {
        "type": "string",
        "description": "Optional: the approval id to resume a previously gated action.",
    }
    required = list(base.get("required", []))
    if "idempotency_key" not in required:
        required.append("idempotency_key")
    return {"type": "object", "properties": props, "required": required}


def build_skill_tools(db: Session, org_id: str, skills: list[Skill] | None = None) -> list[dict]:
    """Return wrapper tool descriptors for every binding of every visible skill."""
    tools = []
    for skill in (skills if skills is not None else visible_approved_skills(db, org_id)):
        bindings = db.scalars(select(SkillBinding).where(SkillBinding.skill_id == skill.id)).all()
        for b in bindings:
            gate = b.approval_expression if b.approval_required else "never"
            tools.append(
                {
                    "name": f"{skill.slug}__{b.tool_name}",
                    "description": (
                        f"{skill.title}: execute `{b.tool_name}`"
                        + (" (side-effecting" if b.side_effecting else " (read")
                        + f", approval when {gate}). Routes through the governed executor."
                    ),
                    "input_schema": _wrapper_schema(b),
                    "skill_slug": skill.slug,
                    "tool_name": b.tool_name,
                }
            )
    return tools
