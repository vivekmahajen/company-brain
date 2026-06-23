"""Transport-agnostic MCP application core.

Holds all serving logic so stdio, HTTP, and the in-process smoke test share one
implementation. Tool dispatch for any side effect goes through GovernedExecutor
(INV-1). Visibility is scoped to the caller's org + approved skills (INV-7).
"""
from __future__ import annotations

from sqlalchemy import select

from apps.api.access.visibility import VisibilityFilter
from apps.api.auth.principals import resolve_principal
from apps.api.execution.executor import GovernedExecutor
from apps.api.mcp.wrappers import build_skill_tools, visible_approved_skills
from apps.api.models.db import SessionLocal
from apps.api.models.tables import Skill, SkillBinding
from apps.api.services.execution import resolve_task
from apps.api.services.serving import get_approval

# Core tools (always present). Read/routing only, except invoke_skill_tool.
CORE_TOOLS = [
    {
        "name": "resolve",
        "description": "Route a natural-language task to the correct company skill(s).",
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
    {
        "name": "get_skill",
        "description": "Return a compiled SKILL.md, its bindings, inputs, and provenance.",
        "input_schema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "list_skills",
        "description": "List approved skills visible to the caller.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_approval",
        "description": "Poll the status/result of a held (approval-gated) action.",
        "input_schema": {
            "type": "object",
            "properties": {"approval_id": {"type": "string"}},
            "required": ["approval_id"],
        },
    },
    {
        "name": "invoke_skill_tool",
        "description": "The single governed entry point to execute a skill-bound tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_slug": {"type": "string"},
                "tool_name": {"type": "string"},
                "args": {"type": "object"},
                "idempotency_key": {"type": "string"},
                "approval_id": {"type": "string"},
            },
            "required": ["skill_slug", "tool_name", "args", "idempotency_key"],
        },
    },
]


class AuthError(Exception):
    pass


class MCPBrain:
    def __init__(self, token: str | None, transport: str = "http") -> None:
        self.token = token
        self.transport = transport

    # -- discovery ----------------------------------------------------------
    def list_tools(self) -> list[dict]:
        with SessionLocal() as db:
            principal = resolve_principal(db, self.token)
            if not principal:
                raise AuthError("no valid principal for credential")
            vf = VisibilityFilter(db, principal)
            visible = vf.filter_skills(visible_approved_skills(db, principal.org_id))
            tools = [dict(t) for t in CORE_TOOLS]
            tools += build_skill_tools(db, principal.org_id, visible)
            return tools

    # -- dispatch -----------------------------------------------------------
    def call_tool(self, name: str, arguments: dict) -> dict:
        with SessionLocal() as db:
            principal = resolve_principal(db, self.token)
            if not principal:
                raise AuthError("no valid principal for credential")
            org = principal.org_id
            arguments = arguments or {}
            vf = VisibilityFilter(db, principal)

            if name == "resolve":
                slugs = {s.slug for s in vf.filter_skills(visible_approved_skills(db, org))}
                routes = [r for r in resolve_task(db, arguments["task"], org) if r["slug"] in slugs]
                return {"routes": routes}

            if name == "list_skills":
                return {
                    "skills": [
                        {"slug": s.slug, "title": s.title, "version": s.version, "status": s.status}
                        for s in vf.filter_skills(visible_approved_skills(db, org))
                    ]
                }

            if name == "get_skill":
                return self._get_skill(db, vf, arguments["slug"])

            if name == "get_approval":
                return get_approval(db, org, arguments["approval_id"]) or {"error": "not found"}

            if name == "invoke_skill_tool":
                return GovernedExecutor(db).invoke(
                    principal=principal,
                    skill_slug=arguments["skill_slug"],
                    tool_name=arguments["tool_name"],
                    args=arguments.get("args", {}),
                    idempotency_key=arguments["idempotency_key"],
                    approval_id=arguments.get("approval_id"),
                    transport=self.transport,
                )

            # Per-skill wrapper: "<slug>__<tool>" -> invoke_skill_tool (INV-1).
            if "__" in name:
                slug, _, tool = name.partition("__")
                args = dict(arguments)
                idem = args.pop("idempotency_key", None)
                approval_id = args.pop("approval_id", None)
                if not idem:
                    return {"status": "error", "detail": "idempotency_key is required"}
                return GovernedExecutor(db).invoke(
                    principal=principal,
                    skill_slug=slug,
                    tool_name=tool,
                    args=args,
                    idempotency_key=idem,
                    approval_id=approval_id,
                    transport=self.transport,
                )

            return {"error": f"unknown tool '{name}'"}

    def _get_skill(self, db, vf: VisibilityFilter, slug: str) -> dict:
        # VIS-5: hidden and nonexistent are indistinguishable.
        skill = vf.visible_slug(slug, action="get_skill")
        if not skill:
            return {"error": "not found"}
        bindings = db.scalars(select(SkillBinding).where(SkillBinding.skill_id == skill.id)).all()
        return {
            "slug": skill.slug,
            "title": skill.title,
            "version": skill.version,
            "skill_md": skill.body_md,
            "inputs": skill.frontmatter_jsonb.get("inputs", []),
            "provenance": vf.filter_provenance(skill),  # VIS-6 per-viewer
            "bindings": [
                {
                    "tool_name": b.tool_name,
                    "side_effecting": b.side_effecting,
                    "approval_required_when": b.approval_expression if b.approval_required else "never",
                    "schema": b.tool_schema_jsonb,
                }
                for b in bindings
            ],
        }
