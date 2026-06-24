"""Integrity tests for the model-graded extraction measurement (Part 2).

These run offline (fixture provider) and lock in the *contract* of the live harness —
that it grades by the judge, reports precision AND recall, refuses to fabricate a number,
validates the judge first, and stays OUT of the CI gate. The actual published number
requires a real key (`make eval-extraction-live`); these guard the machinery around it.
"""
from __future__ import annotations

import pytest

from apps.api.evals import extraction_live
from apps.api.evals.judge.judge import _JUDGE_RUBRIC, equivalent
from apps.api.evals.loader import load_cases
from apps.api.evals.runners.extraction import _matches, _matches_live
from apps.api.evals.scoring import extraction_micro


def test_every_golden_unit_has_canonical_statement():
    """The judge matches against `statement`; every expected knowledge unit must have one."""
    for case in load_cases("extraction"):
        for u in case.get("expected_units", []):
            assert u.get("statement"), f"{case['id']} expected_unit missing canonical statement"


def test_matches_live_requires_type_and_semantic_equivalence():
    expected = {"type": "policy_rule", "terms": ["$500"], "statement": "Refunds above $500 require manager sign-off."}
    same = {"type": "policy_rule", "statement": "A refund over $500 needs a manager to approve."}
    wrong_type = {"type": "procedure_step", "statement": "A refund over $500 needs a manager to approve."}
    # fixture judge (token overlap) still gates on type and on overlap.
    assert _matches_live(same, expected) is True
    assert _matches_live(wrong_type, expected) is False


def test_judge_rubric_is_numeric_sensitive():
    """The strict rubric must call out the silent-meaning-change failure modes."""
    for cue in ("threshold", "comparator", "negation", "equivalent=false"):
        assert cue in _JUDGE_RUBRIC


def test_judge_returns_model_stamp():
    v = equivalent("refunds within 30 days are auto-approved",
                   "any refund inside 30 days is auto-approved")
    assert "model" in v and "judge" in v  # fixture stamps too, so the field always exists


def test_extraction_micro_reports_precision_and_recall():
    """INT-3: F1 alone is not enough — precision and recall must both be present."""
    results = [
        {"stage": "extraction", "passed": True,
         "detail": {"noise": False, "tp": 3, "fp": 1, "fn": 2, "prov_ok": 4, "prov_total": 4}},
        {"stage": "extraction", "passed": True,
         "detail": {"noise": True, "tp": 0, "fp": 0, "fn": 0, "prov_ok": 0, "prov_total": 0}},
    ]
    m = extraction_micro(results)
    assert m["precision"] == pytest.approx(3 / 4)
    assert m["recall"] == pytest.approx(3 / 5)
    assert 0 < m["f1"] < 1
    assert m["noise_rejection"] == 1.0


def test_live_measure_on_fixture_is_not_published():
    """No real model ⇒ no published number. The harness must self-mark NOT published."""
    r = extraction_live.measure(split="test", n=2)
    assert r["published"] is False
    assert r["provider"] == "fixture"
    assert "NOT PUBLISHED" in r["model_snapshot"]
    # carries the full integrity payload regardless of provider
    assert set(r["metrics"]) >= {"precision", "recall", "f1"}
    assert "kappa" in r["judge"]


def test_extraction_live_not_in_ci_gate():
    """INT-7: the deterministic suite is the gate; the live measurement is never in eval-ci."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(root, "Makefile"), encoding="utf-8") as f:
        mk = f.read()
    eval_ci = mk.split("eval-ci:")[1].split("\n\n")[0]
    assert "extraction_live" not in eval_ci
    assert "eval-extraction-live" in mk  # but the target exists


def test_fixture_gate_matcher_is_substring_not_judge():
    """Part 1's gate must stay substring-based (deterministic), distinct from the judge."""
    unit = {"type": "policy_rule", "statement": "Refunds above $500 require manager sign-off."}
    assert _matches(unit, {"type": "policy_rule", "terms": ["$500", "manager"]}) is True
    assert _matches(unit, {"type": "policy_rule", "terms": ["$999"]}) is False
