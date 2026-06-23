"""E4 — Routing. top-1 correctness + abstention + calibration data.

Abstention is decided on the RAW score (calibration changes only confidence, not
the argmax). The calibrated confidence feeds ECE (Part B).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.evals.loader import load_cases
from apps.api.evals.runners.harness import EVAL_ORG
from apps.api.resolver.resolver import resolve

ABSTAIN_THRESHOLD = 0.12  # raw best-match score below this ⇒ "no skill applies"


def _route(db: Session, task: str):
    """Return (slug, raw_score, calibrated_confidence, committed)."""
    ranked = resolve(db, EVAL_ORG, task, top_k=3)
    if not ranked:
        return "NONE", 0.0, 0.0, False
    top = ranked[0]
    raw = top.get("raw_score", top["score"])
    if raw < ABSTAIN_THRESHOLD:
        return "NONE", raw, top["confidence"], False
    return top["slug"], raw, top["confidence"], True


def collect_calibration_points(db: Session, org_id: str, split: str) -> list[tuple[float, int]]:
    """(raw_score, was_top1_correct) over COMMITTED routing decisions on `split`.
    Used to fit the calibrator — never on the `test` split (INT-2)."""
    pts = []
    for case in load_cases("routing", split):
        ranked = resolve(db, org_id, case["task"], top_k=1)
        if not ranked:
            continue
        top = ranked[0]
        raw = top.get("raw_score", top["score"])
        if raw < ABSTAIN_THRESHOLD:
            continue  # abstention is a separate decision, not skill-confidence
        pts.append((raw, 1 if top["slug"] == case["expected"] else 0))
    return pts


def run(db: Session, split: str | None = "test") -> list[dict]:
    results = []
    for case in load_cases("routing", split):
        try:
            slug, raw, conf, committed = _route(db, case["task"])
            ok = slug == case["expected"]
            results.append({
                "stage": "routing", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": bool(ok), "judge_used": False, "error": None,
                "detail": {"expected": case["expected"], "actual": slug, "raw_score": round(raw, 3),
                           "confidence": round(conf, 3), "committed": committed,
                           "abstention_case": case["expected"] == "NONE"},
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "routing", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
