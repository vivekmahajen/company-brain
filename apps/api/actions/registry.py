"""Action adapter registry. Side-effecting tools map to real actions here; tools
without an adapter are treated as no-op/simulated side effects deterministically."""
from __future__ import annotations

import hashlib

from apps.api.actions.base import Action
from apps.api.actions.stripe_refund import StripeRefundAction
from apps.api.actions.update_ticket import UpdateTicketAction


class _GenericSandboxAction(Action):
    """Fallback for templated side-effecting tools without a dedicated adapter
    (apply_discount, page_oncall, …) so the governed path is uniform."""

    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, args: dict, resolved_facts: dict, idempotency_key: str) -> dict:
        if self.mode == "live":
            raise RuntimeError(
                f"no live adapter implemented for '{self.name}'; refusing to run a real side effect."
            )
        ref = self.name + "_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]
        return {"provider": "sandbox", "action": self.name, "ref": ref, "args": args, "mode": "sandbox"}


ACTIONS: dict[str, Action] = {
    "stripe_refund": StripeRefundAction(),
    "update_support_ticket": UpdateTicketAction(),
}


def get_action(tool_name: str) -> Action:
    return ACTIONS.get(tool_name) or _GenericSandboxAction(tool_name)
