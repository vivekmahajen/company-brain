"""CBE eval orchestrator (§9, §11).

    python -m apps.api.evals.run                # dev iterate (test split, N runs)
    python -m apps.api.evals.run --ci           # CI gate mode (nonzero exit on fail)
    python -m apps.api.evals.run --split dev

Runs every stage N times against the real engine, aggregates mean±95% CI,
validates the judge (κ), checks contamination, emits the scorecard, and (in CI
mode) enforces the gates: GAR must be 100% and determinism 1.0 (hard), the rest
against thresholds.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

from apps.api.config import get_settings
from apps.api.evals import scorecard as sc_mod
from apps.api.evals import scoring
from apps.api.evals.judge.validate_judge import cohens_kappa
from apps.api.evals.loader import DATASET_VERSION, contamination_check, counts
from apps.api.evals.runners import (
    compilation, e2e, execution, extraction, guardrail, permission, routing, synthesis,
)
from apps.api.evals.runners.harness import EVAL_ORG, setup_brain
from apps.api.models.db import SessionLocal, init_db

MODEL_SNAPSHOT = "2026-01"
SEED = 0

# Pass thresholds (§7). GAR + determinism are hard (must equal 1.0).
THRESHOLDS = {
    "SEC": 0.90, "routing_top1": 0.90, "routing_abstention": 0.95,
    "extraction_f1": 0.85, "noise_rejection": 0.95, "provenance_accuracy": 0.95,
    "synthesis_correctness": 0.90, "compilation_fidelity": 0.95,
}


def _commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _one_run(db, split, run_tag):
    results = []
    for mod in (guardrail, execution, permission, routing, extraction, compilation):
        results += mod.run(db, split)
    results += synthesis.run(db, split, run_tag=run_tag)
    results += e2e.run(db, split, run_tag=run_tag)
    return results


def _latency(db, split) -> dict:
    from apps.api.evals.runners.routing import _route

    times = []
    for c in [c for c in __import__("apps.api.evals.loader", fromlist=["load_cases"]).load_cases("routing", split)][:10]:
        t0 = time.perf_counter()
        _route(db, c["task"])
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p50 = times[len(times) // 2] if times else 0
    return {"resolve_ms_p50": round(p50, 1), "extraction_tokens": 0}


def run_suite(split: str = "test", n: int = 5):
    init_db()
    db = SessionLocal()
    setup_brain(db)

    per_run_metrics = []
    all_results = []
    for i in range(n):
        results = _one_run(db, split, run_tag=f"r{i}")
        all_results = results  # keep last run's per-case detail for persistence
        per_run_metrics.append(scoring.single_run_metrics(results))

    metrics = scoring.aggregate(per_run_metrics)
    judge = cohens_kappa()
    contam = contamination_check()
    cost = _latency(db, split)

    # --- gates ---
    gates = {}
    hard_fail = False
    gar = metrics.get("GAR", {}).get("mean", 0)
    det = metrics.get("determinism", {}).get("mean", 0)
    per = metrics.get("PER", {}).get("mean", 1.0)
    gates["GAR"] = "100% required — PASS" if gar >= 1.0 else "100% required — FAIL ❌"
    gates["PER"] = "100% required — PASS" if per >= 1.0 else "100% required — FAIL ❌"
    gates["determinism"] = "1.0 required — PASS" if det >= 1.0 else "1.0 required — FAIL ❌"
    if gar < 1.0 or det < 1.0 or per < 1.0:
        hard_fail = True
    regressions = []
    for k, thr in THRESHOLDS.items():
        mean = metrics.get(k, {}).get("mean", 0)
        ok = mean >= thr
        gates[k] = f"≥{thr} — {'PASS' if ok else 'FAIL ❌'}"
        if not ok:
            regressions.append(k)
    any_error = any(r["error"] for r in all_results)
    gates["overall"] = "PASS" if (not hard_fail and not regressions and not any_error) else "FAIL"

    attribution = {
        "commit_sha": _commit_sha(), "dataset_version": DATASET_VERSION,
        "model_id": get_settings().model_extract if get_settings().llm_provider == "anthropic" else "fixture",
        "model_snapshot": MODEL_SNAPSHOT if get_settings().llm_provider == "anthropic" else "deterministic",
        "split": split, "n_runs": n, "seed": SEED,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": get_settings().llm_provider,
    }
    scorecard = sc_mod.build_scorecard(attribution=attribution, metrics=metrics, counts=counts(),
                                       judge=judge, contamination=contam, cost=cost, gates=gates)
    db.close()
    return scorecard, all_results


def persist(scorecard: dict, results: list[dict]) -> str:
    from apps.api.models.serving import EvalResult, EvalRun

    db = SessionLocal()
    try:
        a = scorecard["attribution"]
        run = EvalRun(org_id=EVAL_ORG, commit_sha=a["commit_sha"], dataset_version=a["dataset_version"],
                      model_id=a["model_id"], model_snapshot=a["model_snapshot"], split=a["split"],
                      n_runs=a["n_runs"], finished_at=datetime.now(timezone.utc), scorecard_jsonb=scorecard)
        db.add(run)
        db.flush()
        for r in results:
            db.add(EvalResult(eval_run_id=run.id, eval_stage=r["stage"], case_id=r["case_id"],
                              tier=r["tier"], split=r["split"], passed=r["passed"],
                              metric_jsonb=r.get("detail", {}), judge_used=r["judge_used"], error=r["error"]))
        db.commit()
        return run.id
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--ci", action="store_true", help="exit nonzero if any gate fails")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()

    scorecard, results = run_suite(args.split, args.n)
    paths = sc_mod.write(scorecard)
    if not args.no_persist:
        try:
            persist(scorecard, results)
        except Exception as e:  # noqa: BLE001
            print(f"(persist skipped: {e})")

    print(sc_mod.to_markdown(scorecard))
    print(f"\nWrote {paths['json']}, {paths['md']}, {paths['html']}")

    if args.ci and scorecard["gates"]["overall"] != "PASS":
        print("\nCBE GATE: FAIL", file=sys.stderr)
        sys.exit(1)
    print("\nCBE GATE:", scorecard["gates"]["overall"])


if __name__ == "__main__":
    main()
