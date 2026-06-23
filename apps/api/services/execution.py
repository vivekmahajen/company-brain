"""Execution surface for agents (used by both MCP and REST).

resolve / get_skill / list_skills + per-skill tool execution with inline
governance: approval gates (binding expression) and policy checks (M8) are
enforced *before* a side-effecting tool runs. Every invocation writes an
execution_log with the policy-expected decision for closed-loop drift (M9).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.governance.policy import check_policies, eval_expression
from apps.api.models.tables import ExecutionLog, Skill, SkillBinding
from apps.api.resolver.resolver import resolve as _resolve


def resolve_task(db: Session, task: str, org_id: str | None = None) -> list[dict]:
    org_id = org_id or get_settings().default_org_id
    return _resolve(db, org_id, task)


def _latest_skill(db: Session, org_id: str, slug: str) -> Skill | None:
    return db.scalars(
        select(Skill).where(Skill.org_id == org_id, Skill.slug == slug).order_by(Skill.version.desc())
    ).first()


def list_skills(db: Session, org_id: str | None = None) -> list[dict]:
    org_id = org_id or get_settings().default_org_id
    rows = db.scalars(select(Skill).where(Skill.org_id == org_id).order_by(Skill.version.desc())).all()
    seen, out = set(), []
    for s in rows:
        if s.slug in seen:
            continue
        seen.add(s.slug)
        out.append({"slug": s.slug, "title": s.title, "version": s.version, "status": s.status})
    return out


def get_skill(db: Session, slug: str, org_id: str | None = None) -> dict | None:
    org_id = org_id or get_settings().default_org_id
    s = _latest_skill(db, org_id, slug)
    if not s:
        return None
    bindings = db.scalars(select(SkillBinding).where(SkillBinding.skill_id == s.id)).all()
    return {
        "slug": s.slug,
        "title": s.title,
        "version": s.version,
        "status": s.status,
        "frontmatter": s.frontmatter_jsonb,
        "body_md": s.body_md,
        "provenance": s.frontmatter_jsonb.get("provenance", []),
        "tools": [
            {
                "name": b.tool_name,
                "schema": b.tool_schema_jsonb,
                "side_effecting": b.side_effecting,
                "approval_required": b.approval_required,
                "approval_expression": b.approval_expression,
            }
            for b in bindings
        ],
    }


def _simulate_tool(tool_name: str, inputs: dict) -> dict:
    if tool_name == "stripe_refund":
        return {"refunded": True, "order_id": inputs.get("order_id"), "amount": inputs.get("amount")}
    if tool_name == "update_support_ticket":
        return {"ticket_updated": True, "order_id": inputs.get("order_id")}
    return {"ok": True}


def execute_tool(
    db: Session,
    slug: str,
    tool_name: str,
    inputs: dict,
    *,
    agent_id: str = "agent",
    org_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """REST/console execution. Routes through the ONE GovernedExecutor (INV-1)
    using the seeded default agent principal."""
    import uuid

    from apps.api.auth.principals import resolve_principal
    from apps.api.execution.executor import GovernedExecutor

    org_id = org_id or get_settings().default_org_id
    args = dict(inputs)
    key = idempotency_key or args.pop("idempotency_key", None) or f"rest-{uuid.uuid4()}"

    principal = resolve_principal(db, "agent-token")
    if not principal or principal.org_id != org_id:
        return {"status": "error", "detail": "no agent principal seeded for this org"}

    return GovernedExecutor(db).invoke(
        principal=principal,
        skill_slug=slug,
        tool_name=tool_name,
        args=args,
        idempotency_key=key,
        transport="rest",
    )
