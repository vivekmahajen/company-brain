"""Multi-capability: pricing + incident compile, route, and gate correctly."""
from apps.api.services.execution import execute_tool, get_skill, resolve_task


def test_three_skills_compiled(seeded, db, org_id):
    from apps.api.services.execution import list_skills

    slugs = {s["slug"] for s in list_skills(db, org_id)}
    assert {"handle-refund", "handle-pricing-exception", "respond-to-incident"} <= slugs


def test_routing_across_capabilities(seeded, db, org_id):
    cases = [
        ("the customer is asking for a 30% discount", "handle-pricing-exception"),
        ("production is down, looks like a sev1 outage", "respond-to-incident"),
        ("angry customer wants their money back", "handle-refund"),
    ]
    for task, expected in cases:
        assert resolve_task(db, task, org_id)[0]["slug"] == expected, task


def test_pricing_approval_gate(seeded, db, org_id):
    # discount_percent > 20 must gate on the manager-approval threshold.
    skill = get_skill(db, "handle-pricing-exception", org_id)
    apply = next(t for t in skill["tools"] if t["name"] == "apply_discount")
    assert apply["approval_required"] is True
    assert "discount_percent > 20" in (apply["approval_expression"] or "")

    big = execute_tool(db, "handle-pricing-exception", "apply_discount", {"account_id": "a", "discount_percent": 30}, org_id=org_id)
    small = execute_tool(db, "handle-pricing-exception", "apply_discount", {"account_id": "a", "discount_percent": 10}, org_id=org_id)
    assert big["outcome"] == "approval_required"
    assert small["outcome"] == "executed"


def test_incident_skill_is_executable(seeded, db, org_id):
    skill = get_skill(db, "respond-to-incident", org_id)
    body = skill["body_md"].lower()
    assert "procedure" in body
    # has a guardrail extracted from the runbook
    assert any("post-mortem" in g.lower() for g in skill["frontmatter"]["guardrails"])
