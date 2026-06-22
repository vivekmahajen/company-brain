"""M8 — Governance: policy enforcement + confidence gating at execution time.

Approval expressions are tiny, safe comparisons ("amount > 500") evaluated
against the agent's input — never `eval`. `policy` rows are checked at execution
time (not just documented); a violation is blocked and logged with the rule.
"""
from __future__ import annotations

import operator
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.tables import Policy

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}
_EXPR = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def eval_expression(expr: str | None, inputs: dict) -> bool:
    """Evaluate a single 'field op number' guard. Returns False on unparsable/missing."""
    if not expr or expr.strip().lower() == "never":
        return False
    m = _EXPR.match(expr)
    if not m:
        return False
    field, op, num = m.group(1), m.group(2), float(m.group(3))
    val = inputs.get(field)
    if val is None:
        return False
    try:
        return _OPS[op](float(val), num)
    except (TypeError, ValueError):
        return False


def seed_default_policies(db: Session, org_id: str) -> None:
    """Idempotently seed the canonical refund policy (refund > $500 => human approval)."""
    existing = db.scalar(select(Policy).where(Policy.org_id == org_id, Policy.name == "refund_high_value"))
    if existing:
        return
    db.add(
        Policy(
            org_id=org_id,
            name="refund_high_value",
            rule_jsonb={"tool": "stripe_refund", "when": "amount > 500", "require": "human_approval"},
            enforcement="block",
        )
    )
    db.commit()


def check_policies(db: Session, org_id: str, tool_name: str, inputs: dict) -> dict:
    """Return {'allowed': bool, 'rule': name|None, 'reason': str} for a tool call."""
    policies = db.scalars(select(Policy).where(Policy.org_id == org_id)).all()
    for p in policies:
        rule = p.rule_jsonb or {}
        if rule.get("tool") != tool_name:
            continue
        if eval_expression(rule.get("when"), inputs):
            if p.enforcement in ("block",):
                return {
                    "allowed": False,
                    "rule": p.name,
                    "reason": f"policy '{p.name}' requires {rule.get('require')} when {rule.get('when')}",
                }
    return {"allowed": True, "rule": None, "reason": "no blocking policy matched"}
