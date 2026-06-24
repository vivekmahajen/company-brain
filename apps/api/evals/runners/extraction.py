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
    """Deterministic (fixture) match: same type + every golden `term` is a substring
    of the extracted statement. This is the pipeline-correctness GATE (INT-5)."""
    if unit.get("type") != expected["type"]:
        return False
    stmt = (unit.get("statement") or "").lower()
    return all(t.lower() in stmt for t in expected["terms"])


def _matches_live(unit: dict, expected: dict) -> bool:
    """Model-graded match: same type + the LLM judge rules the extracted statement
    semantically equivalent to the golden `statement`. Used by extraction_live.py
    (INT-2: a real measurement, judge-in-the-loop, never substring-gamed)."""
    from apps.api.evals.judge.judge import equivalent

    if unit.get("type") != expected.get("type"):
        return False
    want = expected.get("statement")
    if not want:  # no canonical statement → fall back to the substring gate
        return _matches(unit, expected)
    return bool(equivalent(unit.get("statement") or "", want)["equivalent"])


def run(db: Session, split: str | None = "test", live: bool = False) -> list[dict]:
    """Score extraction against the goldens.

    live=False (default): substring match — the deterministic regression gate.
    live=True: judge-graded semantic match — the published NLP-quality measurement.
    Per-case `detail` carries tp/fp/fn so micro precision/recall/F1 aggregate honestly,
    including false positives the extractor invents (INT-3: precision AND recall)."""
    match = _matches_live if live else _matches
    results = []
    for case in load_cases("extraction", split):
        try:
            units = _extract(case["content"])
            expected = case.get("expected_units", [])
            if case.get("expected_absent"):
                ok = len(units) == 0
                results.append({
                    "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                    "passed": ok, "judge_used": live, "error": None,
                    "detail": {"kind": case.get("kind"), "noise": True, "extracted": len(units), "tp": 0, "fp": len(units), "fn": 0,
                               "prov_ok": 0, "prov_total": 0},
                })
                continue

            matched = [e for e in expected if any(match(u, e) for u in units)]
            tp = len(matched)
            fn = len(expected) - tp
            fp = sum(1 for u in units if not any(match(u, e) for e in expected))
            prov_total = len(units)
            prov_ok = sum(1 for u in units if (u.get("quote_span") or "") in case["content"])
            ok = (fn == 0)
            results.append({
                "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": ok, "judge_used": live, "error": None,
                "detail": {"kind": case.get("kind"), "noise": False, "tp": tp, "fp": fp, "fn": fn,
                           "prov_ok": prov_ok, "prov_total": prov_total},
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "extraction", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": live, "error": f"{type(e).__name__}: {e}",
                "detail": {"kind": case.get("kind"), "tp": 0, "fp": 0, "fn": 99, "prov_ok": 0, "prov_total": 0, "noise": False},
            })
    return results
