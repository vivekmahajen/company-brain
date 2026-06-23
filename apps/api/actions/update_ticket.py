"""Support-ticket update adapter (§7)."""
from __future__ import annotations

import hashlib

from apps.api.actions.base import Action


class UpdateTicketAction(Action):
    name = "update_support_ticket"
    side_effecting = True

    def execute(self, args: dict, resolved_facts: dict, idempotency_key: str) -> dict:
        ticket_id = "tkt_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]
        return {
            "provider": "support_desk",
            "ticket_id": ticket_id,
            "order_id": args.get("order_id"),
            "note": args.get("note", ""),
            "status": "updated",
            "mode": "sandbox",
        }
