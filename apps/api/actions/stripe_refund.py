"""Stripe refund adapter (§7). Sandbox simulates deterministically; live would
pass the idempotency_key to Stripe's native idempotency so even a retry past our
own check cannot double-charge."""
from __future__ import annotations

import hashlib

from apps.api.actions.base import Action


class StripeRefundAction(Action):
    name = "stripe_refund"
    side_effecting = True

    def execute(self, args: dict, resolved_facts: dict, idempotency_key: str) -> dict:
        amount = args.get("amount", resolved_facts.get("original_charge"))
        order_id = args.get("order_id")
        if self.mode == "live":  # pragma: no cover - requires real keys + approval
            raise RuntimeError("live Stripe mode requires explicit operator approval")
        # Deterministic fake provider id keyed by idempotency_key.
        refund_id = "re_sandbox_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
        return {
            "provider": "stripe",
            "refund_id": refund_id,
            "order_id": order_id,
            "amount": amount,
            "status": "succeeded",
            "mode": "sandbox",
        }
