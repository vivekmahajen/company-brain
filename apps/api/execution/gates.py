"""Gate evaluation (§6 steps 5–6, INV-2).

`safe_eval` evaluates `approval_required_when` expressions against the resolved
facts using a restricted AST walk — literals, names bound to the context,
comparisons, and boolean ops only. Never `eval()`.

Guardrails are server-enforced structured checks keyed by tool: a hard deny
(e.g. refund amount exceeds the original charge) blocks the side effect; a soft
guardrail (e.g. order older than 90 days) forces approval/escalation.
"""
from __future__ import annotations

import ast
import operator

_BIN_OPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class UnsafeExpression(ValueError):
    pass


def safe_eval(expr: str, context: dict) -> bool:
    """Evaluate a boolean guard expression against `context`. Safe by construction."""
    if not expr or expr.strip().lower() == "never":
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpression(f"cannot parse: {expr!r}") from e
    return bool(_ev(tree.body, context))


def _ev(node, ctx):
    if isinstance(node, ast.BoolOp):
        vals = [_ev(v, ctx) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _ev(node.operand, ctx)
    if isinstance(node, ast.Compare):
        left = _ev(node.left, ctx)
        for op, right_node in zip(node.ops, node.comparators):
            right = _ev(right_node, ctx)
            fn = _BIN_OPS.get(type(op))
            if fn is None:
                raise UnsafeExpression(f"operator not allowed: {op}")
            if left is None or right is None:
                return False
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        return ctx.get(node.id)
    if isinstance(node, ast.Constant):
        return node.value
    raise UnsafeExpression(f"disallowed expression node: {type(node).__name__}")


# --- Guardrails (server-enforced, structured) -----------------------------
# Each returns (tripped, kind, reason). kind ∈ {hard, soft}.
def _refund_guardrails(facts: dict):
    out = []
    req = facts.get("requested_amount")
    charge = facts.get("original_charge")
    if req is not None and charge is not None and req > charge:
        out.append((True, "hard", f"refund {req} exceeds original charge {charge}"))
    age = facts.get("order_age_days")
    if age is not None and age > 90:
        out.append((True, "soft", f"order age {age}d exceeds 90 days"))
    return out


_GUARDRAILS = {
    "stripe_refund": _refund_guardrails,
}


def evaluate_guardrails(tool_name: str, facts: dict):
    """Return (hard_deny_reason | None, soft_escalate_reason | None)."""
    checks = _GUARDRAILS.get(tool_name)
    if not checks:
        return None, None
    hard, soft = None, None
    for tripped, kind, reason in checks(facts):
        if not tripped:
            continue
        if kind == "hard" and hard is None:
            hard = reason
        elif kind == "soft" and soft is None:
            soft = reason
    return hard, soft
