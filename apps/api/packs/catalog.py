"""Vertical capability packs (Phase 8 / GTM).

A pack is a curated bundle of capability templates for an industry — installing one
gives a tenant a head start instead of authoring from scratch. Each template is the
same shape as POST /api/templates; installing creates them (quota-checked, dedup'd),
then the tenant adds their own knowledge to fill them.
"""
from __future__ import annotations

PACKS: dict[str, dict] = {
    "saas-support": {
        "label": "SaaS Support",
        "description": "Refunds, plan changes, and escalations for a SaaS support team.",
        "templates": [
            {"topic": "plan_change", "title": "Change a customer's plan",
             "keywords": ["upgrade", "downgrade", "plan change", "subscription"],
             "intents": ["change a customer plan", "upgrade a subscription"]},
            {"topic": "bug_escalation", "title": "Escalate a customer bug",
             "keywords": ["bug", "broken", "not working", "escalate"],
             "intents": ["escalate a bug", "report a defect"]},
        ],
    },
    "ecommerce-ops": {
        "label": "E-commerce Ops",
        "description": "Order, shipping, and returns workflows for an online store.",
        "templates": [
            {"topic": "order_issue", "title": "Resolve an order issue",
             "keywords": ["order", "shipping", "delivery", "lost package", "tracking"],
             "intents": ["resolve an order problem", "where is my order"]},
            {"topic": "return_request", "title": "Process a return",
             "keywords": ["return", "rma", "exchange", "send back"],
             "intents": ["process a return", "start an exchange"]},
        ],
    },
    "it-ops": {
        "label": "IT / DevOps",
        "description": "Access requests and change management for an IT/platform team.",
        "templates": [
            {"topic": "access_request", "title": "Grant an access request",
             "keywords": ["access", "permission", "grant", "provision", "role"],
             "intents": ["grant access", "provision a role"]},
            {"topic": "change_request", "title": "Approve a change request",
             "keywords": ["change request", "deploy", "rollout", "maintenance window"],
             "intents": ["approve a change", "schedule a deploy"]},
        ],
    },
}


def list_packs() -> list[dict]:
    return [{"id": pid, "label": p["label"], "description": p["description"],
             "capabilities": [t["title"] for t in p["templates"]]}
            for pid, p in PACKS.items()]


def install_pack(db, org_id: str, pack_id: str) -> dict:
    from apps.api.services.templates import create_template

    pack = PACKS.get(pack_id)
    if not pack:
        return {"error": f"unknown pack '{pack_id}'", "known": sorted(PACKS)}
    created, skipped = [], []
    for t in pack["templates"]:
        res = create_template(db, org_id, topic=t["topic"], title=t["title"],
                              description=t.get("description", ""), keywords=t.get("keywords", []),
                              intents=t.get("intents", []), inputs=t.get("inputs", []),
                              tools=t.get("tools", []))
        if res.get("error"):
            skipped.append({"topic": t["topic"], "reason": res["error"], "quota": res.get("quota", False)})
        else:
            created.append(t["topic"])
    return {"pack": pack_id, "installed": created, "skipped": skipped}
