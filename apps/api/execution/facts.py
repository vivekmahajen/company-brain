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


def mirror_db_facts(db: Session, org_id: str) -> int:
    """Populate the read-only Order fact store from the Postgres reader (INV-2).

    The `order_record` table is the server-side fact store the refund gate reads;
    in production it is mirrored from the orders DB via the read-only Postgres
    connector. Here we mirror its `orders` table so gate facts are DB-backed, not
    agent-supplied. Idempotent upsert."""
    from apps.api.connectors.registry import get_connector
    from apps.api.models.tables import Source

    n = 0
    for src in db.scalars(select(Source).where(Source.org_id == org_id, Source.kind == "postgres")).all():
        conn = get_connector("postgres", src.config_jsonb)
        records = conn._records()  # fixture or live (read-only)
        for row in records.get("tables", {}).get("orders", {}).get("rows", []):
            existing = db.scalar(select(Order).where(Order.org_id == org_id, Order.order_id == str(row["id"])))
            if not existing:
                existing = Order(org_id=org_id, order_id=str(row["id"]))
                db.add(existing)
            existing.original_charge = float(row["amount"])
            existing.age_days = int(row.get("age_days", 0))
            n += 1
    db.commit()
    return n


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
                # required for a live provider refund; None in the demo dataset
                "provider_charge_id": order.provider_charge_id,
            }
        )
        return facts

    # Non-refund tools: pass args through as facts for now.
    facts.update({k: v for k, v in args.items()})
    return facts
