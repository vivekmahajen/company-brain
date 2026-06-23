"""Metric computation, calibration, and CIs across N runs (TRUST-4)."""
from __future__ import annotations

import math


def _rate(results, stage, predicate=lambda r: True) -> tuple[int, int]:
    sel = [r for r in results if r["stage"] == stage and predicate(r)]
    return sum(1 for r in sel if r["passed"]), len(sel)


def _f(n, d) -> float:
    return (n / d) if d else 0.0


def single_run_metrics(results: list[dict]) -> dict:
    m: dict[str, float] = {}

    # Headline
    p, t = _rate(results, "guardrail")
    m["GAR"] = _f(p, t)
    p, t = _rate(results, "execution")
    m["SEC"] = _f(p, t)
    p, t = _rate(results, "permission")
    if t:
        m["PER"] = _f(p, t)

    # Routing
    p, t = _rate(results, "routing", lambda r: not r["detail"].get("abstention_case"))
    m["routing_top1"] = _f(p, t)
    p, t = _rate(results, "routing", lambda r: r["detail"].get("abstention_case"))
    m["routing_abstention"] = _f(p, t)

    # Extraction micro-F1 + noise + provenance
    ext = [r for r in results if r["stage"] == "extraction"]
    tp = sum(r["detail"].get("tp", 0) for r in ext if not r["detail"].get("noise"))
    fp = sum(r["detail"].get("fp", 0) for r in ext if not r["detail"].get("noise"))
    fn = sum(r["detail"].get("fn", 0) for r in ext if not r["detail"].get("noise"))
    prec = _f(tp, tp + fp)
    rec = _f(tp, tp + fn)
    m["extraction_f1"] = _f(2 * prec * rec, prec + rec)
    noise = [r for r in ext if r["detail"].get("noise")]
    m["noise_rejection"] = _f(sum(1 for r in noise if r["passed"]), len(noise))
    prov_ok = sum(r["detail"].get("prov_ok", 0) for r in ext)
    prov_total = sum(r["detail"].get("prov_total", 0) for r in ext)
    m["provenance_accuracy"] = _f(prov_ok, prov_total)

    # Synthesis / compilation
    p, t = _rate(results, "synthesis")
    m["synthesis_correctness"] = _f(p, t)
    p, t = _rate(results, "compilation")
    m["compilation_fidelity"] = _f(p, t)
    comp = [r for r in results if r["stage"] == "compilation"]
    m["determinism"] = 1.0 if comp and all(r["detail"].get("determinism", True) for r in comp) else (
        0.0 if comp else 1.0)

    # E2E
    p, t = _rate(results, "e2e")
    if t:
        m["e2e"] = _f(p, t)

    m["calibration_ece"] = _ece([r for r in results if r["stage"] == "routing"])
    return m


def _ece(routing_results: list[dict], bins: int = 5) -> float:
    pts = [(r["detail"].get("confidence", 0.0), 1 if r["passed"] else 0) for r in routing_results]
    if not pts:
        return 0.0
    total = len(pts)
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(c, ok) for c, ok in pts if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if not bucket:
            continue
        avg_conf = sum(c for c, _ in bucket) / len(bucket)
        acc = sum(ok for _, ok in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(acc - avg_conf)
    return round(ece, 4)


def aggregate(run_metrics: list[dict]) -> dict:
    """mean ± 95% CI per metric across N runs (normal approx)."""
    keys = set().union(*[set(m) for m in run_metrics]) if run_metrics else set()
    out = {}
    for k in sorted(keys):
        vals = [m[k] for m in run_metrics if k in m]
        n = len(vals)
        mean = sum(vals) / n if n else 0.0
        if n >= 2:
            var = sum((v - mean) ** 2 for v in vals) / (n - 1)
            ci = 1.96 * math.sqrt(var) / math.sqrt(n)
        else:
            ci = 0.0
        out[k] = {"mean": round(mean, 4), "ci95": round(ci, 4), "n": n,
                  "min": round(min(vals), 4) if vals else 0.0, "max": round(max(vals), 4) if vals else 0.0}
    return out
