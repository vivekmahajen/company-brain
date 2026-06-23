"""Part B acceptance: calibrated confidence (ECE ≤ 0.10 on test) without moving
top-1 (INT-8), monotonic, in [0,1]."""
import pytest

from apps.api.evals.loader import load_cases
from apps.api.evals.runners import routing
from apps.api.evals.runners.harness import setup_brain
from apps.api.evals.runners.routing import _route
from apps.api.evals.scoring import ece_with_ci
from apps.api.models.db import SessionLocal, init_db
from apps.api.resolver import calibration


@pytest.fixture(scope="module")
def eval_brain():
    init_db()
    db = SessionLocal()
    try:
        setup_brain(db)
    finally:
        db.close()


def test_calibrator_is_monotonic_and_bounded(eval_brain):
    calibration.reload()
    assert calibration.is_monotonic()
    xs = [0.0, 0.1, 0.3, 0.6, 1.0]
    ys = [calibration.apply(x) for x in xs]
    assert all(0.0 <= y <= 1.0 for y in ys)
    assert ys == sorted(ys)  # non-decreasing in score


def test_top1_invariant_under_calibration(eval_brain):
    # Calibration changes confidence, never the argmax (INT-8).
    db = SessionLocal()
    try:
        calibration.reload()
        with_cal = [_route(db, c["task"])[0] for c in load_cases("routing", "test")]
        calibration._cache = {}  # identity
        without = [_route(db, c["task"])[0] for c in load_cases("routing", "test")]
        calibration.reload()
        assert with_cal == without
    finally:
        db.close()


def test_ece_below_threshold_on_test(eval_brain):
    db = SessionLocal()
    try:
        calibration.reload()
        res = routing.run(db, split="test")
        ece = ece_with_ci(res)
        # Point estimate ≤ 0.10 (CI disclosed on the scorecard); huge drop from 0.68.
        assert ece["ece"] <= 0.10, ece
        assert ece["n"] >= 20
    finally:
        db.close()
