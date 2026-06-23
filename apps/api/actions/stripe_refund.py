"""Stripe refund adapter (§7).

- sandbox: deterministic fake refund id; no network, no keys.
- live: a real Stripe refund. FAILS CLOSED — refuses to proceed unless a Stripe
  key is configured AND the order resolved to a provider charge id. The
  idempotency_key is passed to Stripe's native idempotency so even a retry past
  our own check cannot double-refund.

The executor only ever calls this AFTER all gates clear; the adapter never makes
the gate decision.
"""
from __future__ import annotations

import hashlib

from apps.api.actions.base import Action
from apps.api.config import get_settings


class StripeRefundAction(Action):
    name = "stripe_refund"
    side_effecting = True

    def execute(self, args: dict, resolved_facts: dict, idempotency_key: str) -> dict:
        amount = args.get("amount", resolved_facts.get("original_charge"))
        order_id = args.get("order_id")

        if self.mode != "live":
            refund_id = "re_sandbox_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
            return {
                "provider": "stripe",
                "refund_id": refund_id,
                "order_id": order_id,
                "amount": amount,
                "status": "succeeded",
                "mode": "sandbox",
            }

        # --- live: real money. Fail closed on any missing prerequisite. -----
        settings = get_settings()
        if not settings.stripe_api_key:
            raise RuntimeError(
                "ACTIONS_MODE=live but STRIPE_API_KEY is not set — refusing to issue a real refund."
            )
        charge_id = resolved_facts.get("provider_charge_id")
        if not charge_id:
            raise RuntimeError(
                f"no provider_charge_id resolved for order {order_id!r}; cannot issue a live refund."
            )
        if amount is None or float(amount) <= 0:
            raise RuntimeError("live refund requires a positive amount.")

        import stripe  # imported lazily so sandbox never needs the SDK

        stripe.api_key = settings.stripe_api_key
        refund = stripe.Refund.create(
            charge=charge_id,
            amount=int(round(float(amount) * 100)),  # Stripe expects minor units
            idempotency_key=idempotency_key,         # provider-level idempotency (INV-5)
        )
        return {
            "provider": "stripe",
            "refund_id": refund.id,
            "order_id": order_id,
            "amount": amount,
            "status": refund.status,
            "mode": "live",
        }
