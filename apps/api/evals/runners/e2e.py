"""E7 — End-to-end: natural-language task -> resolve -> get skill -> governed
execution -> correct outcome. Composes the real stages (no shortcuts)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.evals.runners.execution import _decision, _side_effect_fired
from apps.api.evals.runners.harness import AGENT, EVAL_ORG, invoke_refund, new_key, upsert_order
from apps.api.evals.runners.routing import _route

CASES = [
    {"id": "e2e_under", "task": "a customer wants their money back on order 55",
     "order": {"id": "55", "amount": 200, "age_days": 12}, "request": {"order_id": "55", "amount": 200},
     "expected_slug": "handle-refund", "expected_decision": "execute", "tier": "standard", "split": "test"},
    {"id": "e2e_over", "task": "furious customer demanding a refund on order 1234",
     "order": {"id": "1234", "amount": 620, "age_days": 40}, "request": {"order_id": "1234", "amount": 620},
     "expected_slug": "handle-refund", "expected_decision": "approval_required", "tier": "standard", "split": "test"},
    {"id": "e2e_oos", "task": "what is our parental leave policy",
     "order": None, "request": None, "expected_slug": "NONE", "expected_decision": None,
     "tier": "standard", "split": "test"},
]


def run(db: Session, split: str | None = "test", run_tag: str = "") -> list[dict]:
    results = []
    for case in CASES:
        if split and case["split"] != split:
            continue
        try:
            slug, _ = _route(db, case["task"])
            ok = slug == case["expected_slug"]
            detail = {"routed": slug}
            if case["expected_decision"] is not None and ok:
                upsert_order(db, case["order"])
                key = new_key()
                res = invoke_refund(db, token=AGENT, request=case["request"], idempotency_key=key)
                actual = _decision(res)
                ok = ok and actual == case["expected_decision"]
                detail["decision"] = actual
                if case["expected_decision"] == "execute":
                    ok = ok and _side_effect_fired(db, key)
            results.append({
                "stage": "e2e", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": bool(ok), "judge_used": False, "error": None, "detail": detail,
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "e2e", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
