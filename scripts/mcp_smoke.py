"""MCP smoke test (§11). Asserts the §1 definition-of-done outcomes in sandbox.

Runs the transport-agnostic MCPBrain core in-process (the same code stdio/HTTP
dispatch through), against a fresh seeded DB. Runnable in CI:

    python scripts/mcp_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# Isolated DB so the smoke run never touches a real database.
_TMP = tempfile.mkdtemp(prefix="mcp-smoke-")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP}/smoke.db")
os.environ.setdefault("LLM_PROVIDER", "fixture")
os.environ.setdefault("ACTIONS_MODE", "sandbox")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.api.auth.principals import resolve_principal  # noqa: E402
from apps.api.config import get_settings  # noqa: E402
from apps.api.mcp.brain import MCPBrain  # noqa: E402
from apps.api.models.db import SessionLocal, init_db  # noqa: E402
from apps.api.services.serving import approve_demo_skills, decide_approval  # noqa: E402
from apps.api.services.pipeline import run_full_pipeline  # noqa: E402

AGENT, LIMITED, HUMAN = "agent-token", "agent-readonly-token", "human-token"


def setup() -> str:
    init_db()
    org = get_settings().default_org_id
    db = SessionLocal()
    try:
        run_full_pipeline(db, org)
        approve_demo_skills(db, org)
    finally:
        db.close()
    return org


def check(label: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(f"smoke failed: {label}")


def main() -> None:
    org = setup()
    agent = MCPBrain(AGENT)

    print("MCP smoke test (sandbox)")

    tools = {t["name"] for t in agent.list_tools()}
    check("tools/list has core + wrappers", {"resolve", "invoke_skill_tool"} <= tools
          and "handle-refund__stripe_refund" in tools)

    routes = agent.call_tool("resolve", {"task": "angry customer wants their money back"})["routes"]
    check("resolve -> handle-refund first", routes and routes[0]["slug"] == "handle-refund")

    skill = agent.call_tool("get_skill", {"slug": "handle-refund"})
    check("get_skill returns bindings + provenance",
          any(b["tool_name"] == "stripe_refund" for b in skill["bindings"]) and bool(skill["provenance"]))

    under = agent.call_tool("handle-refund__stripe_refund",
                            {"order_id": "55", "amount": 200, "idempotency_key": "s-a1"})
    check("$200/#55 executes", under["status"] == "executed")

    over = agent.call_tool("handle-refund__stripe_refund",
                           {"order_id": "1234", "amount": 620, "idempotency_key": "s-b1"})
    check("$620/#1234 -> approval_required, no side effect", over["status"] == "approval_required")
    approval_id = over["approval_id"]

    inv2 = agent.call_tool("handle-refund__stripe_refund",
                           {"order_id": "1234", "amount": 200, "idempotency_key": "s-inv2"})
    check("gate uses server facts not agent claim (INV-2)", inv2["status"] == "approval_required")

    limited = MCPBrain(LIMITED).call_tool("handle-refund__stripe_refund",
                                          {"order_id": "55", "amount": 50, "idempotency_key": "s-lim"})
    check("limited agent denied_permission", limited.get("reason") == "denied_permission")

    db = SessionLocal()
    try:
        agent_p = resolve_principal(db, AGENT)
        human_p = resolve_principal(db, HUMAN)
        self_approve = decide_approval(db, org, approval_id, decision="approve", approver=agent_p)
        check("requester cannot self-approve (INV-4)", "error" in self_approve)
        approved = decide_approval(db, org, approval_id, decision="approve", approver=human_p)
        check("human approval executes held action", approved["execution"]["status"] == "executed")
    finally:
        db.close()

    final = agent.call_tool("get_approval", {"approval_id": approval_id})
    check("get_approval -> executed + result", final["status"] == "executed" and final["result"])

    replay = agent.call_tool("handle-refund__stripe_refund",
                             {"order_id": "1234", "amount": 620, "idempotency_key": "s-b1"})
    check("idempotent replay (INV-5)", replay["status"] == "idempotent_replay")

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
