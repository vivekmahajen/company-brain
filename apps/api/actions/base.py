"""Action adapter ABC (§7).

The executor never calls a vendor SDK directly — it dispatches to an adapter
only AFTER every gate has cleared. Adapters never make gate decisions. Sandbox
mode simulates success deterministically so the full path is testable without
real provider keys; the code path is identical to live.
"""
from __future__ import annotations

import abc

from apps.api.config import get_settings


class Action(abc.ABC):
    name: str = "base"
    side_effecting: bool = True

    @abc.abstractmethod
    def execute(self, args: dict, resolved_facts: dict, idempotency_key: str) -> dict:
        """Perform the side effect. Must be idempotent on idempotency_key."""

    @property
    def mode(self) -> str:
        return get_settings().actions_mode
