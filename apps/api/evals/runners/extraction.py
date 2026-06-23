"""E1 — Extraction. F1 of typed KUs vs golden + noise rejection + provenance.

Runs the production extraction path (cheap classify gate, then typed extraction).
Only units at/above the review-confidence floor count — i.e. the ones that would
actually reach a skill. Per-case `passed` = full recall (and empty on noise);
scoring aggregates micro-F1 from the per-case counts.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.evals.loader import load_cases
from apps.api.llm.base import get_llm
from apps.api.llm.prompts import EXTRACTION_SYSTEM


def _extract(content: str) -> list[dict]:
    llm = get_llm()
    if llm.classify(text=content, labels=["knowledge", "chatter"]) != "knowledge":
        return []
    resp = llm.complete_json(
        system=EXTRACTION_SYSTEM, prompt="extract", context={"task": "extract", "artifact_text": content}
    )
    floor = get_settings().confidence_review_threshold
    return [u for u in resp.data.get("units", []) if float(u.get("confidence", 0)) >= floor]


def _matches(unit: dict, expected: dict) -> bool:
    if unit.get("type") != expected["type"]:
        return False
    stmt = (unit.get("statement") or "").lower()
    return all(t.lower() in stmt for t in expected["terms"])


def run(db: Session, split: str | None = "test") -> list[dict]:
    results = []
    for case in load_cases("extraction", split):
        try:
            units = _extract(case["content"])
            expected = case.get("expected_units", [])
            if case.get("expected_absent"):
                ok = len(units) == 0
                results.append({
                    "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                    "passed": ok, "judge_used": False, "error": None,
                    "detail": {"kind": case.get("kind"), "noise": True, "extracted": len(units), "tp": 0, "fp": len(units), "fn": 0,
                               "prov_ok": 0, "prov_total": 0},
                })
                continue

            matched = [e for e in expected if any(_matches(u, e) for u in units)]
            tp = len(matched)
            fn = len(expected) - tp
            fp = sum(1 for u in units if not any(_matches(u, e) for e in expected))
            prov_total = len(units)
            prov_ok = sum(1 for u in units if (u.get("quote_span") or "") in case["content"])
            ok = (fn == 0)
            results.append({
                "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": ok, "judge_used": False, "error": None,
                "detail": {"kind": case.get("kind"), "noise": False, "tp": tp, "fp": fp, "fn": fn,
                           "prov_ok": prov_ok, "prov_total": prov_total},
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}",
                "detail": {"kind": case.get("kind"), "tp": 0, "fp": 0, "fn": 99, "prov_ok": 0, "prov_total": 0, "noise": False},
            })
    return results
