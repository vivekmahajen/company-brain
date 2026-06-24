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


def extraction_micro(results: list[dict]) -> dict:
    """Micro precision / recall / F1 over the extraction results, plus noise
    rejection and provenance — the full quality picture for one run (INT-3).
    Shared by the deterministic gate and the live (model-graded) measurement."""
    ext = [r for r in results if r["stage"] == "extraction"]
    know = [r for r in ext if not r["detail"].get("noise")]
    noise = [r for r in ext if r["detail"].get("noise")]
    tp = sum(r["detail"].get("tp", 0) for r in know)
    fp = sum(r["detail"].get("fp", 0) for r in know)
    fn = sum(r["detail"].get("fn", 0) for r in know)
    prec = _f(tp, tp + fp)
    rec = _f(tp, tp + fn)
    prov_ok = sum(r["detail"].get("prov_ok", 0) for r in ext)
    prov_total = sum(r["detail"].get("prov_total", 0) for r in ext)
    return {
        "precision": prec, "recall": rec, "f1": _f(2 * prec * rec, prec + rec),
        "tp": tp, "fp": fp, "fn": fn,
        "noise_rejection": _f(sum(1 for r in noise if r["passed"]), len(noise)),
        "noise_n": len(noise),
        "provenance_accuracy": _f(prov_ok, prov_total),
        "knowledge_cases": len(know),
    }


def extraction_by_kind(results: list[dict]) -> dict:
    """Per-source-kind extraction F1 + noise rejection (so a regression in one
    source type is visible, not averaged away)."""
    ext = [r for r in results if r["stage"] == "extraction"]
    kinds = sorted({r["detail"].get("kind") for r in ext if r["detail"].get("kind")})
    out = {}
    for k in kinds:
        rows = [r for r in ext if r["detail"].get("kind") == k]
        know = [r for r in rows if not r["detail"].get("noise")]
        noise = [r for r in rows if r["detail"].get("noise")]
        tp = sum(r["detail"].get("tp", 0) for r in know)
        fp = sum(r["detail"].get("fp", 0) for r in know)
        fn = sum(r["detail"].get("fn", 0) for r in know)
        prec = _f(tp, tp + fp)
        rec = _f(tp, tp + fn)
        f1 = round(_f(2 * prec * rec, prec + rec), 3) if know else None
        out[k] = {
            "f1": f1,
            "noise_rejection": round(_f(sum(1 for r in noise if r["passed"]), len(noise)), 3) if noise else None,
            "cases": len(rows),
        }
    return out


def _calib_points(routing_results: list[dict]) -> list[tuple[float, int]]:
    """(calibrated_confidence, correct) over COMMITTED routing decisions only —
    confidence is meaningful only when the resolver commits to a skill."""
    return [(r["detail"].get("confidence", 0.0), 1 if r["passed"] else 0)
            for r in routing_results if r["detail"].get("committed")]


def _ece_from_points(pts: list[tuple[float, int]], bins: int = 10) -> float:
    if not pts:
        return 0.0
    total = len(pts)
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(c, ok) for c, ok in pts if (lo <= c < hi) or (b == bins - 1 and c >= hi)]
        if not bucket:
            continue
        avg_conf = sum(c for c, _ in bucket) / len(bucket)
        acc = sum(ok for _, ok in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(acc - avg_conf)
    return ece


def _ece(routing_results: list[dict], bins: int = 10) -> float:
    return round(_ece_from_points(_calib_points(routing_results), bins), 4)


def ece_with_ci(routing_results: list[dict], bins: int = 10, n_boot: int = 2000, seed: int = 0) -> dict:
    """Bootstrap 95% CI for ECE on the committed routing decisions (Part B/§7)."""
    import random

    pts = _calib_points(routing_results)
    n = len(pts)
    point = _ece_from_points(pts, bins)
    if n < 2:
        return {"ece": round(point, 4), "ci95": [round(point, 4), round(point, 4)], "n": n, "bins": bins}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [pts[rng.randrange(n)] for _ in range(n)]
        boots.append(_ece_from_points(sample, bins))
    boots.sort()
    lo = boots[int(0.025 * n_boot)]
    hi = boots[int(0.975 * n_boot)]
    return {"ece": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)], "n": n, "bins": bins}


def reliability_bins(routing_results: list[dict], bins: int = 10) -> list[dict]:
    pts = _calib_points(routing_results)
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(c, ok) for c, ok in pts if (lo <= c < hi) or (b == bins - 1 and c >= hi)]
        if not bucket:
            continue
        out.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": len(bucket),
                    "avg_conf": round(sum(c for c, _ in bucket) / len(bucket), 3),
                    "accuracy": round(sum(ok for _, ok in bucket) / len(bucket), 3)})
    return out


def metric_n(results: list[dict]) -> dict:
    """Per-headline-metric denominators (n) for honest reporting (§7)."""
    return {
        "GAR": _rate(results, "guardrail")[1],
        "SEC": _rate(results, "execution")[1],
        "PER": _rate(results, "permission")[1],
        "routing_top1": _rate(results, "routing", lambda r: not r["detail"].get("abstention_case"))[1],
        "routing_abstention": _rate(results, "routing", lambda r: r["detail"].get("abstention_case"))[1],
        "extraction": len([r for r in results if r["stage"] == "extraction" and not r["detail"].get("noise")]),
        "synthesis_correctness": _rate(results, "synthesis")[1],
        "compilation_fidelity": _rate(results, "compilation")[1],
    }


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
