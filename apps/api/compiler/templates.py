"""Per-capability compile templates: required inputs + tool bindings.

These declare the *executable surface* (tools an agent may call, approval gates).
Thresholds are not hard-coded here — they are filled from the canonical KUs at
compile time. Keep templates minimal; the knowledge drives the rest.
"""
from __future__ import annotations

SKILL_TEMPLATES: dict[str, dict] = {
    "refund": {
        "slug": "handle-refund",
        "title": "Handle a customer refund",
        "description": (
            "Decide and execute customer refunds, including auto-approval thresholds, "
            "exception handling, and escalation. Use when a customer requests money back."
        ),
        "inputs": [
            "order_id (string, required)",
            "amount (number, required)",
            "reason (string, optional)",
        ],
        "tools": [
            {
                "name": "stripe_refund",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["order_id", "amount"],
                },
                # approval expression filled from the manager-approval threshold KU
                "approval_for_action": "manager_approval",
            },
            {
                "name": "update_support_ticket",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["order_id"],
                },
                "approval_for_action": None,
            },
        ],
        "intents": [
            "issue a refund",
            "customer wants their money back",
            "process a chargeback reversal",
            "refund an order",
        ],
        "keywords": ["refund", "money back", "chargeback", "reimburse", "return payment"],
    }
}
