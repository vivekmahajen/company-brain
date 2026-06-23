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


_DEFAULT_POLICIES = [
    ("refund_high_value", {"tool": "stripe_refund", "when": "amount > 500", "require": "human_approval"}),
    ("pricing_high_discount", {"tool": "apply_discount", "when": "discount_percent > 20", "require": "manager_approval"}),
]


def seed_default_policies(db: Session, org_id: str) -> None:
    """Idempotently seed the canonical enforcement policies."""
    for name, rule in _DEFAULT_POLICIES:
        if db.scalar(select(Policy).where(Policy.org_id == org_id, Policy.name == name)):
            continue
        db.add(Policy(org_id=org_id, name=name, rule_jsonb=rule, enforcement="block"))
    db.commit()


def list_policies(db: Session, org_id: str) -> list[dict]:
    rows = db.scalars(select(Policy).where(Policy.org_id == org_id)).all()
    return [
        {"id": p.id, "name": p.name, "rule": p.rule_jsonb, "enforcement": p.enforcement}
        for p in rows
    ]


def create_policy(
    db: Session,
    org_id: str,
    *,
    name: str,
    tool: str,
    when: str,
    require: str = "human_approval",
    enforcement: str = "block",
) -> dict:
    """Add a governance guardrail. Validates the `when` expression up front."""
    if enforcement not in ("block", "warn", "log"):
        return {"error": f"invalid enforcement '{enforcement}'"}
    if not _EXPR.match(when):
        return {"error": f"invalid condition '{when}'. Use '<field> <op> <number>', e.g. 'amount > 500'."}
    existing = db.scalar(select(Policy).where(Policy.org_id == org_id, Policy.name == name))
    rule = {"tool": tool, "when": when, "require": require}
    if existing:
        existing.rule_jsonb = rule
        existing.enforcement = enforcement
        p = existing
    else:
        p = Policy(org_id=org_id, name=name, rule_jsonb=rule, enforcement=enforcement)
        db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name, "rule": p.rule_jsonb, "enforcement": p.enforcement}


def delete_policy(db: Session, org_id: str, policy_id: str) -> dict:
    p = db.scalar(select(Policy).where(Policy.org_id == org_id, Policy.id == policy_id))
    if not p:
        return {"deleted": False, "error": "not found"}
    db.delete(p)
    db.commit()
    return {"deleted": True, "id": policy_id}


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
