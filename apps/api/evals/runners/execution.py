"""E5 — Skill-Execution Correctness (SEC). HEADLINE.

Drives the real GovernedExecutor against each scenario's server facts and checks
the brain reaches the exactly-correct governed decision (+ no leaked side effect).
Deterministic decision-match (no LLM judge).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.evals.loader import load_cases
from apps.api.evals.runners.harness import AGENT, EVAL_ORG, invoke_refund, new_key, upsert_order
from apps.api.models.tables import ExecutionLog


def _side_effect_fired(db: Session, key: str) -> bool:
    return db.scalar(
        select(ExecutionLog).where(
            ExecutionLog.org_id == EVAL_ORG,
            ExecutionLog.idempotency_key == key,
            ExecutionLog.outcome == "executed",
        )
    ) is not None


def _decision(res: dict) -> str:
    if res["status"] == "executed":
        return "execute"
    if res["status"] == "denied":
        return res.get("reason", "denied")
    if res["status"] == "approval_required":
        reason = (res.get("gate_reason") or "").lower()
        return "escalate" if "90" in reason or "age" in reason else "approval_required"
    return res["status"]


def run(db: Session, split: str | None = "test") -> list[dict]:
    results = []
    for case in load_cases("execution", split):
        try:
            upsert_order(db, case.get("order"))
            key = new_key()
            res = invoke_refund(db, token=AGENT, request=case["request"], idempotency_key=key)
            exp = case["expected"]
            actual = _decision(res)
            ok = actual == exp["decision"]
            if "side_effect_fired" in exp:
                ok = ok and (_side_effect_fired(db, key) == exp["side_effect_fired"])
            if exp.get("gate_reason_contains"):
                ok = ok and exp["gate_reason_contains"] in (res.get("gate_reason") or "")
            results.append({
                "stage": "execution", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": bool(ok), "judge_used": False, "error": None,
                "detail": {"expected": exp["decision"], "actual": actual, "status": res["status"]},
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "execution", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
