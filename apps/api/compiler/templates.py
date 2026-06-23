"""Per-capability compile templates: required inputs + tool bindings + routing.

Adding a capability is data, not code: add a template here, optionally provide
fixtures/knowledge, and the compiler + resolver pick it up. Thresholds are NOT
hard-coded — they are filled from the canonical KUs at compile time.

Tool approval gates are generic:
  - approval_for_action: the policy action that triggers a gate (e.g.
    "manager_approval").
  - approval_field:      the agent-input field used in the gate expression.
  - threshold_kind:      which extracted threshold to read (amount|percent|days).
The compiler emits `approval_required_when: "<field> > <threshold>"`.
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
                    "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}},
                    "required": ["order_id", "amount"],
                },
                "approval_for_action": "manager_approval",
                "approval_field": "amount",
                "threshold_kind": "amount",
            },
            {
                "name": "update_support_ticket",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}, "note": {"type": "string"}},
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
        "keywords": ["refund", "money back", "chargeback", "reimburse", "return payment",
                     "reverse the charge", "reverse", "overcharged", "double charged",
                     "wrong charge", "charged", "return", "cancelled order"],
    },
    "pricing": {
        "slug": "handle-pricing-exception",
        "title": "Handle a pricing exception",
        "description": (
            "Decide and apply pricing exceptions and discounts, including approval "
            "thresholds and deal-desk escalation. Use when a customer asks for a "
            "discount or special pricing."
        ),
        "inputs": [
            "account_id (string, required)",
            "discount_percent (number, required)",
            "reason (string, optional)",
        ],
        "tools": [
            {
                "name": "apply_discount",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string"},
                        "discount_percent": {"type": "number"},
                    },
                    "required": ["account_id", "discount_percent"],
                },
                "approval_for_action": "manager_approval",
                "approval_field": "discount_percent",
                "threshold_kind": "percent",
            },
            {
                "name": "update_crm",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}, "note": {"type": "string"}},
                    "required": ["account_id"],
                },
                "approval_for_action": None,
            },
        ],
        "intents": [
            "approve a discount",
            "customer wants a lower price",
            "grant a pricing exception",
            "special pricing request",
        ],
        "keywords": ["discount", "pricing", "price exception", "deal desk", "markdown", "special pricing",
                     "lower price", "custom price", "price", "percent off", "% off", "exception"],
    },
    "incident": {
        "slug": "respond-to-incident",
        "title": "Respond to a production incident",
        "description": (
            "Triage and respond to production incidents: classify severity, page "
            "on-call, open an incident channel, and post status updates. Use when a "
            "service is down or degraded."
        ),
        "inputs": [
            "service (string, required)",
            "severity (string, required)",
            "summary (string, optional)",
        ],
        "tools": [
            {
                "name": "page_oncall",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}, "severity": {"type": "string"}},
                    "required": ["service", "severity"],
                },
                "approval_for_action": None,
            },
            {
                "name": "open_incident_channel",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
                "approval_for_action": None,
            },
            {
                "name": "post_status_update",
                "side_effecting": True,
                "schema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}, "message": {"type": "string"}},
                    "required": ["service", "message"],
                },
                "approval_for_action": None,
            },
        ],
        "intents": [
            "respond to an incident",
            "production is down",
            "service outage",
            "page the on-call engineer",
        ],
        "keywords": ["incident", "outage", "down", "sev1", "pager", "on-call", "post-mortem",
                     "degraded", "service is", "unreachable", "500s", "errors", "failing",
                     "broken", "impacted", "latency", "outages"],
    },
}
