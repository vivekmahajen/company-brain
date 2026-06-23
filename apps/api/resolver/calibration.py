"""Resolver confidence calibration (Part B).

Learns a monotonic Platt map g(score) → P(top-1 correct) so `confidence` means
something. Ranking is unchanged (the resolver still argmaxes the RAW score), so
top-1 accuracy is invariant (INT-8). Fit on a held-out `calib` split, evaluated
on `test` (INT-2). Pure-Python logistic regression — no sklearn dependency.
"""
from __future__ import annotations

import json
import math
import os

from apps.api.evals.loader import DATASET_VERSION

_PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")
_cache: dict | None = None


def _sigmoid(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def fit_platt(scores: list[float], labels: list[int], iters: int = 5000, lr: float = 0.5) -> tuple[float, float]:
    """Fit P(correct) = sigmoid(A*score + B) by gradient descent on log-loss."""
    A, B = 1.0, 0.0
    n = len(scores)
    if n == 0:
        return A, B
    for _ in range(iters):
        gA = gB = 0.0
        for s, y in zip(scores, labels):
            p = _sigmoid(A * s + B)
            err = p - y
            gA += err * s
            gB += err
        A -= lr * gA / n
        B -= lr * gB / n
    return A, B


def apply(score: float) -> float:
    """Calibrated confidence for a raw resolver score. Identity if not yet fit."""
    global _cache
    if _cache is None:
        _cache = _load()
    if not _cache:
        return max(0.0, min(1.0, score))
    return _sigmoid(_cache["A"] * score + _cache["B"])


def _load() -> dict:
    if not os.path.exists(_PARAMS_PATH):
        return {}
    with open(_PARAMS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(A: float, B: float, *, fit_split: str, n: int) -> None:
    global _cache
    params = {"A": round(A, 6), "B": round(B, 6), "method": "platt",
              "dataset_version": DATASET_VERSION, "fit_split": fit_split, "n": n}
    with open(_PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2)
    _cache = params


def is_monotonic() -> bool:
    """A>0 ⇒ confidence increases with score (a sane calibrator)."""
    p = _cache or _load()
    return (not p) or p.get("A", 1.0) > 0


def reload() -> None:
    global _cache
    _cache = None


# --- fitting CLI: build the (score, correct) calib set + fit + persist --------
def fit_from_calib(split: str = "calib") -> dict:
    from apps.api.evals.runners.harness import EVAL_ORG, setup_brain
    from apps.api.evals.runners.routing import collect_calibration_points
    from apps.api.models.db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        setup_brain(db)
        pts = collect_calibration_points(db, EVAL_ORG, split)
    finally:
        db.close()
    if not pts:
        raise RuntimeError(f"no calibration points on split '{split}'")
    scores = [s for s, _ in pts]
    labels = [int(y) for _, y in pts]
    A, B = fit_platt(scores, labels)
    save(A, B, fit_split=split, n=len(pts))
    return {"A": A, "B": B, "n": len(pts), "positives": sum(labels)}


if __name__ == "__main__":
    print(fit_from_calib())
