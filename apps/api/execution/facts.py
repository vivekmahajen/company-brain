"""Server-side fact resolution (INV-2, §6 step 4).

The gate decision must use ground truth the server looks up — never the agent's
claimed args. For refund tools we resolve the order's true original charge and
age; for other tools we currently fall back to the supplied args (extend per
capability as real connectors land).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.serving import Order

_REFUND_TOOLS = {"stripe_refund", "update_support_ticket"}


def resolve_facts(db: Session, org_id: str, tool_name: str, args: dict) -> dict:
    """Return the fact context used by guardrails + the approval gate."""
    facts: dict = {"tool": tool_name, "requested_args": dict(args)}

    if tool_name in _REFUND_TOOLS:
        order_id = str(args.get("order_id", ""))
        order = db.scalar(
            select(Order).where(Order.org_id == org_id, Order.order_id == order_id)
        )
        if order is None:
            facts.update({"order_found": False, "order_id": order_id})
            # Unknown order: expose requested amount so guardrails can still act.
            facts["amount"] = args.get("amount")
            facts["requested_amount"] = args.get("amount")
            return facts
        facts.update(
            {
                "order_found": True,
                "order_id": order.order_id,
                # INV-2: the GATE reads the server-known charge, not the agent's.
                "amount": order.original_charge,
                "original_charge": order.original_charge,
                "requested_amount": args.get("amount"),
                "order_age_days": order.age_days,
                "order_status": order.status,
            }
        )
        return facts

    # Non-refund tools: pass args through as facts for now.
    facts.update({k: v for k, v in args.items()})
    return facts
