"""§12 acceptance for the MCP serving layer, driven through the transport-
agnostic MCPBrain (the same core stdio/HTTP use). Sandbox actions."""
import asyncio

from apps.api.mcp.brain import AuthError, MCPBrain
from apps.api.mcp.context import broadcast_tools_changed
from apps.api.models.db import SessionLocal
from apps.api.services.serving import decide_approval, get_approval
from apps.api.auth.principals import resolve_principal

AGENT = "agent-token"
LIMITED = "agent-readonly-token"
HUMAN = "human-token"


def test_unauthenticated_sees_nothing(seeded):
    try:
        MCPBrain("bogus-token").list_tools()
        assert False, "unknown credential must not authenticate"
    except AuthError:
        pass


def test_list_tools_includes_core_and_wrappers(seeded):
    names = {t["name"] for t in MCPBrain(AGENT).list_tools()}
    assert {"resolve", "get_skill", "list_skills", "get_approval", "invoke_skill_tool"} <= names
    assert "handle-refund__stripe_refund" in names


def test_resolve_and_get_skill(seeded):
    brain = MCPBrain(AGENT)
    routes = brain.call_tool("resolve", {"task": "a customer is angry and wants their money back"})["routes"]
    assert routes and routes[0]["slug"] == "handle-refund"
    skill = brain.call_tool("get_skill", {"slug": "handle-refund"})
    assert any(b["tool_name"] == "stripe_refund" for b in skill["bindings"])
    assert skill["provenance"]


def test_under_threshold_executes(seeded):
    res = MCPBrain(AGENT).call_tool(
        "handle-refund__stripe_refund",
        {"order_id": "55", "amount": 200, "idempotency_key": "mcp-a1"},
    )
    assert res["status"] == "executed"
    assert res["result"]["refund_id"].startswith("re_sandbox_")


def test_over_threshold_holds_then_approves(seeded):
    brain = MCPBrain(AGENT)
    held = brain.call_tool(
        "handle-refund__stripe_refund",
        {"order_id": "1234", "amount": 620, "idempotency_key": "mcp-b1"},
    )
    assert held["status"] == "approval_required"
    approval_id = held["approval_id"]

    # No side effect happened yet: polling shows pending.
    assert MCPBrain(AGENT).call_tool("get_approval", {"approval_id": approval_id})["status"] == "pending"

    # Human approves (server executes the held action).
    db = SessionLocal()
    try:
        human = resolve_principal(db, HUMAN)
        out = decide_approval(db, db_org(db), approval_id, decision="approve", approver=human)
        assert out["execution"]["status"] == "executed"
    finally:
        db.close()

    assert MCPBrain(AGENT).call_tool("get_approval", {"approval_id": approval_id})["status"] == "executed"


def test_permission_denied_for_limited_agent(seeded):
    res = MCPBrain(LIMITED).call_tool(
        "handle-refund__stripe_refund",
        {"order_id": "55", "amount": 50, "idempotency_key": "mcp-lim"},
    )
    assert res["status"] == "denied" and res["reason"] == "denied_permission"


def test_idempotent_replay(seeded):
    brain = MCPBrain(AGENT)
    args = {"order_id": "55", "amount": 200, "idempotency_key": "mcp-idem"}
    first = brain.call_tool("handle-refund__stripe_refund", dict(args))
    second = brain.call_tool("handle-refund__stripe_refund", dict(args))
    assert first["status"] == "executed"
    assert second["status"] == "idempotent_replay"
    assert second["result"]["refund_id"] == first["result"]["refund_id"]


def test_gate_uses_server_facts_not_agent_claim(seeded):
    # Agent claims $200 but order #1234 is truly $620 -> gate still trips. (INV-2)
    res = MCPBrain(AGENT).call_tool(
        "handle-refund__stripe_refund",
        {"order_id": "1234", "amount": 200, "idempotency_key": "mcp-inv2"},
    )
    assert res["status"] == "approval_required"


def test_tools_list_changed_broadcast(seeded):
    # No connected sessions in-process -> 0 notified, but callable/safe.
    assert asyncio.get_event_loop().run_until_complete(broadcast_tools_changed()) == 0


def db_org(db):
    from apps.api.config import get_settings

    return get_settings().default_org_id
