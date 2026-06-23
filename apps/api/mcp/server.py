"""Low-level MCP Server (§3, §11).

The tool list is DYNAMIC — computed per-caller from approved skills in Postgres —
and every call dispatches through the one GovernedExecutor via MCPBrain. We use
the low-level `Server` (not FastMCP) precisely because of these two needs.
"""
from __future__ import annotations

import json

import mcp.types as types
from mcp.server.lowlevel import Server

from apps.api.mcp.brain import AuthError, MCPBrain
from apps.api.mcp.context import current_credential


def build_server() -> Server:
    server = Server("company-brain")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        brain = MCPBrain(current_credential.get(), transport="mcp")
        try:
            descriptors = brain.list_tools()
        except AuthError:
            return []
        return [
            types.Tool(name=d["name"], description=d["description"], inputSchema=d["input_schema"])
            for d in descriptors
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        brain = MCPBrain(current_credential.get(), transport="mcp")
        try:
            result = brain.call_tool(name, arguments or {})
        except AuthError as e:
            result = {"status": "denied", "reason": "unauthorized", "detail": str(e)}
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    # Expose each approved skill as a resource at skill://<slug>.
    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        brain = MCPBrain(current_credential.get(), transport="mcp")
        try:
            skills = brain.call_tool("list_skills", {}).get("skills", [])
        except AuthError:
            return []
        return [
            types.Resource(uri=f"skill://{s['slug']}", name=s["title"], mimeType="text/markdown")
            for s in skills
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        slug = str(uri).replace("skill://", "")
        brain = MCPBrain(current_credential.get(), transport="mcp")
        skill = brain.call_tool("get_skill", {"slug": slug})
        return skill.get("skill_md", json.dumps(skill))

    return server
