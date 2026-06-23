"""E4 — Routing. top-1 correctness + abstention on out-of-scope tasks.

Abstention is modeled as: the top route's confidence is below a threshold (the
resolver returns ranked skills with confidence; a weak best match ⇒ abstain).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.evals.loader import load_cases
from apps.api.evals.runners.harness import EVAL_ORG
from apps.api.resolver.resolver import resolve

ABSTAIN_THRESHOLD = 0.12  # best-match confidence below this ⇒ "no skill applies"


def _route(db: Session, task: str) -> tuple[str, float]:
    ranked = resolve(db, EVAL_ORG, task, top_k=3)
    if not ranked:
        return "NONE", 0.0
    top = ranked[0]
    if top["confidence"] < ABSTAIN_THRESHOLD:
        return "NONE", top["confidence"]
    return top["slug"], top["confidence"]


def run(db: Session, split: str | None = "test") -> list[dict]:
    results = []
    for case in load_cases("routing", split):
        try:
            slug, conf = _route(db, case["task"])
            ok = slug == case["expected"]
            results.append({
                "stage": "routing", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": bool(ok), "judge_used": False, "error": None,
                "detail": {"expected": case["expected"], "actual": slug, "confidence": round(conf, 3),
                           "abstention_case": case["expected"] == "NONE"},
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "routing", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
