"""Measure PRODUCTION extraction quality on the real model (the published NLP number).

This is the model-graded counterpart to the deterministic governance scorecard. It
runs the *real* extraction path (`LLM_PROVIDER=anthropic`) over the goldens and scores
each extracted KU against a canonical `statement` by **semantic equivalence via the LLM
judge** — never substring overlap (INT-2). It reports micro precision / recall / F1
(INT-3), per-source-kind F1, noise rejection, and provenance, each as **mean ± 95% CI
over N≥5 runs** with the model snapshot attached (INT-6).

    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... \
        python -m apps.api.evals.extraction_live --n 5 --split test

Integrity:
  * Validates the judge against human labels FIRST (Cohen's κ). κ<0.7 ⇒ the whole
    measurement is stamped low-trust, because a number graded by an untrusted judge
    is not publishable.
  * Costs real money and needs the network, so it is **cost-guarded** and is NOT part
    of the CI gate (`make eval-ci`). The deterministic suite stays the gate (INT-7).
  * Refuses to invent a number: without a real provider it exits non-zero (unless
    `--allow-fixture`, which produces an explicitly NON-PUBLISHED wiring smoke test).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

from apps.api.config import get_settings
from apps.api.evals.judge.validate_judge import cohens_kappa
from apps.api.evals.loader import DATASET_VERSION
from apps.api.evals.runners import extraction
from apps.api.evals.scoring import extraction_by_kind, extraction_micro
from apps.api.models.db import SessionLocal, init_db

MODEL_SNAPSHOT = "2026-06"  # stamp the run; bump when the served model rev changes.
PUBLISHED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "published")
PUBLISHED_JSON = os.path.join(PUBLISHED_DIR, "extraction_live.json")
PUBLISHED_MD = os.path.join(PUBLISHED_DIR, "extraction_live.md")

# Keys we aggregate across runs.
_AGG_KEYS = ["precision", "recall", "f1", "noise_rejection", "provenance_accuracy"]


def _commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _mean_ci(vals: list[float]) -> dict:
    n = len(vals)
    mean = sum(vals) / n if n else 0.0
    if n >= 2:
        var = sum((v - mean) ** 2 for v in vals) / (n - 1)
        ci = 1.96 * math.sqrt(var) / math.sqrt(n)
    else:
        ci = 0.0
    return {"mean": round(mean, 4), "ci95": round(ci, 4), "n": n,
            "min": round(min(vals), 4) if vals else 0.0,
            "max": round(max(vals), 4) if vals else 0.0}


def measure(split: str = "test", n: int = 5) -> dict:
    settings = get_settings()
    live = settings.llm_provider.lower() == "anthropic"

    # 1) Trust the judge before trusting any judge-graded number.
    judge = cohens_kappa()

    # 2) N runs of the real extraction path, judge-graded.
    init_db()
    db = SessionLocal()
    try:
        from apps.api.evals.runners.harness import setup_brain

        setup_brain(db)
        per_run, by_kind_last = [], {}
        for _ in range(n):
            results = extraction.run(db, split, live=True)
            per_run.append(extraction_micro(results))
            by_kind_last = extraction_by_kind(results)
    finally:
        db.close()

    agg = {k: _mean_ci([r[k] for r in per_run]) for k in _AGG_KEYS}
    counts = {
        "knowledge_cases": per_run[0]["knowledge_cases"] if per_run else 0,
        "noise_cases": per_run[0]["noise_n"] if per_run else 0,
        "tp_last": per_run[-1]["tp"] if per_run else 0,
        "fp_last": per_run[-1]["fp"] if per_run else 0,
        "fn_last": per_run[-1]["fn"] if per_run else 0,
    }

    cost = {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
    if live:
        from apps.api.llm.anthropic_client import AnthropicClient

        t = AnthropicClient.TOTAL
        cost = {"usd": round(t.cost_usd, 4), "calls": t.calls,
                "input_tokens": t.input_tokens, "output_tokens": t.output_tokens}

    return {
        "kind": "extraction_live",
        "published": live and not judge["low_trust"],
        "provider": settings.llm_provider,
        "model": settings.model_extract if live else "fixture",
        "model_snapshot": MODEL_SNAPSHOT if live else "deterministic (NOT PUBLISHED)",
        "commit_sha": _commit_sha(),
        "dataset_version": DATASET_VERSION,
        "split": split,
        "n_runs": n,
        "judge": judge,
        "metrics": agg,
        "by_kind": by_kind_last,
        "counts": counts,
        "cost": cost,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": ("Model-graded extraction quality, judge-matched (semantic equivalence). "
                 "Honest production number — expected below the fixture gate's 100%.")
        if live else
        ("WIRING SMOKE TEST ONLY — fixture provider, NOT a published measurement. "
         "Run with LLM_PROVIDER=anthropic for the real number."),
    }


def to_markdown(r: dict) -> str:
    m = r["metrics"]

    def cell(x):
        v = m.get(x, {})
        s = f"{v.get('mean', 0) * 100:.1f}%"
        return s + (f" ±{v.get('ci95', 0) * 100:.1f}" if v.get("n", 0) >= 2 and v.get("ci95", 0) > 0 else "")

    L = [
        "# Extraction quality — measured (model-graded)\n",
        f"> {'**PUBLISHED**' if r['published'] else '**NOT PUBLISHED** (wiring smoke / low-trust judge)'} · "
        f"{r['model']} ({r['model_snapshot']}) · commit `{r['commit_sha']}` · dataset {r['dataset_version']} · "
        f"**{r['split']}** split · {r['n_runs']} runs · judge κ={r['judge']['kappa']}"
        f"{' ⚠ LOW-TRUST' if r['judge']['low_trust'] else ''}\n",
        "| Metric | Value (mean ± 95% CI) |",
        "|---|---|",
        f"| Precision | {cell('precision')} |",
        f"| Recall | {cell('recall')} |",
        f"| **F1** | **{cell('f1')}** |",
        f"| Noise rejection | {cell('noise_rejection')} |",
        f"| Provenance accuracy | {cell('provenance_accuracy')} |",
        "",
        f"Judge-graded against canonical statements (semantic equivalence, not substring). "
        f"Cohen's κ vs human labels = **{r['judge']['kappa']}** (n={r['judge']['n']}, "
        f"observed agreement {r['judge']['observed_agreement']}).",
        f"Cost: ${r['cost']['usd']} · {r['cost']['calls']} model calls "
        f"({r['cost']['input_tokens']}/{r['cost']['output_tokens']} in/out tokens).",
        "",
        "## Per source kind (F1, last run)",
        "| Kind | F1 | Noise rej. | Cases |",
        "|---|---|---|---|",
    ]
    for k, v in sorted(r["by_kind"].items()):
        f1 = "—" if v["f1"] is None else f"{v['f1']:.3f}"
        nr = "—" if v["noise_rejection"] is None else f"{v['noise_rejection']:.3f}"
        L.append(f"| {k} | {f1} | {nr} | {v['cases']} |")
    L.append("\n_" + r["note"] + "_")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--allow-fixture", action="store_true",
                    help="run on the fixture provider as a NON-PUBLISHED wiring smoke test")
    args = ap.parse_args()

    settings = get_settings()
    live = settings.llm_provider.lower() == "anthropic"
    if not live and not args.allow_fixture:
        print(
            "extraction_live measures the REAL model and would otherwise fabricate a number.\n"
            "Set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY, then re-run:\n\n"
            "    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... \\\n"
            "        python -m apps.api.evals.extraction_live --n 5\n\n"
            "Or pass --allow-fixture for an offline wiring smoke test (NOT published).",
            file=sys.stderr,
        )
        sys.exit(2)

    if live:
        from apps.api.llm.anthropic_client import AnthropicClient

        AnthropicClient.reset_usage()

    result = measure(args.split, args.n)
    md = to_markdown(result)

    if result["published"]:
        os.makedirs(PUBLISHED_DIR, exist_ok=True)
        with open(PUBLISHED_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        with open(PUBLISHED_MD, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(md)
        print(f"\nWrote published measurement → {PUBLISHED_JSON}")
        print("Commit it next to BENCHMARK.md so the number is attributable.")
    else:
        print(md)
        reason = "low-trust judge (κ<0.7)" if live else "fixture provider"
        print(f"\nNOT written to published/ — {reason}. Nothing to publish.", file=sys.stderr)
        if live and result["judge"]["low_trust"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
