"""M7 — MCP server: how AI agents consume and execute skills.

Exposes:
  - resolve(task)        -> ranked skills + why
  - list_skills()        -> available skills
  - get_skill(slug)      -> the compiled SKILL.md + bound tools + provenance
  - execute(slug, tool, inputs) -> runs a bound tool with inline governance;
                           side-effecting tools return APPROVAL_REQUIRED instead
                           of acting when an approval gate / policy matches.

Run:  python -m apps.api.mcp.server   (stdio transport)
The same logic is mirrored over REST in routers/brain.py.
"""
from __future__ import annotations

import json

from apps.api.config import get_settings
from apps.api.models.db import SessionLocal, init_db
from apps.api.services.execution import execute_tool, get_skill, list_skills, resolve_task

try:
    from mcp.server.fastmcp import FastMCP

    _HAVE_MCP = True
except Exception:  # pragma: no cover - mcp optional at import time
    _HAVE_MCP = False


def _org() -> str:
    return get_settings().default_org_id


def build_server():
    if not _HAVE_MCP:
        raise RuntimeError("The `mcp` package is not installed. `pip install mcp`. ")
    mcp = FastMCP("company-brain")

    @mcp.tool()
    def resolve(task: str) -> str:
        """Route a natural-language task to the correct company skill(s)."""
        with SessionLocal() as db:
            return json.dumps(resolve_task(db, task, _org()), default=str)

    @mcp.tool()
    def brain_list_skills() -> str:
        """List the skills the company brain can execute."""
        with SessionLocal() as db:
            return json.dumps(list_skills(db, _org()), default=str)

    @mcp.tool()
    def get_skill_md(slug: str) -> str:
        """Return the compiled SKILL.md, bound tools, and provenance for a slug."""
        with SessionLocal() as db:
            return json.dumps(get_skill(db, slug, _org()), default=str)

    @mcp.tool()
    def execute(slug: str, tool: str, inputs: dict, agent_id: str = "mcp-agent") -> str:
        """Execute a bound tool of a skill. Side-effecting tools honor approval gates."""
        with SessionLocal() as db:
            return json.dumps(
                execute_tool(db, slug, tool, inputs, agent_id=agent_id, org_id=_org()), default=str
            )

    return mcp


def main() -> None:
    init_db()
    server = build_server()
    server.run()  # stdio by default


if __name__ == "__main__":
    main()
