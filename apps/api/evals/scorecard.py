"""Emit the CBE Scorecard: JSON + human-readable Markdown/HTML (§8)."""
from __future__ import annotations

import json
import os

REPORT_DIR = "evals_out"


def build_scorecard(*, attribution: dict, metrics: dict, counts: dict, judge: dict,
                    contamination: dict, cost: dict, gates: dict) -> dict:
    return {
        "name": "Company Brain Eval (CBE)",
        "version": "0.1",
        "attribution": attribution,
        "headline": {"GAR": metrics.get("GAR"), "SEC": metrics.get("SEC"), "PER": metrics.get("PER")},
        "metrics": metrics,
        "dataset_counts": counts,
        "judge": judge,
        "contamination": contamination,
        "cost_latency": cost,
        "gates": gates,
    }


def _fmt(metric: dict | None) -> str:
    if not metric:
        return "—"
    pct = metric["mean"] * 100
    ci = metric["ci95"] * 100
    return f"{pct:.1f}%" + (f" ±{ci:.1f}" if metric["n"] >= 2 and ci > 0 else "")


def to_markdown(sc: dict) -> str:
    a = sc["attribution"]
    m = sc["metrics"]
    ns = sc.get("metric_n", {})
    L = []
    L.append(f"# {sc['name']} — v{sc['version']}\n")
    L.append(f"> **{sc.get('mode','fixture')}** · commit `{a['commit_sha']}` · dataset {a['dataset_version']} · "
             f"{a['model_id']} ({a['model_snapshot']}) · {a['n_runs']} runs · **{a['split']}** split · seed {a['seed']}\n")
    L.append("## Headline — deterministic governance (exact, with n)\n")
    L.append("| Metric | Value | n | Gate |")
    L.append("|---|---|---|---|")
    gar = m.get("GAR", {})
    L.append(f"| **Guardrail Adherence Rate (GAR)** | **{_fmt(gar)}** | {ns.get('GAR','?')} | {sc['gates'].get('GAR','')} |")
    L.append(f"| **Permission Enforcement Rate (PER)** | **{_fmt(m.get('PER'))}** | {ns.get('PER','?')} | {sc['gates'].get('PER','')} |")
    L.append(f"| **Skill-Execution Correctness (SEC)** | **{_fmt(m.get('SEC'))}** | {ns.get('SEC','?')} | {sc['gates'].get('SEC','')} |")
    L.append("\n_These drive the real GovernedExecutor / VisibilityFilter with programmatic pass/fail — "
             "they are exact rates, independent of the extraction model._")
    L.append("\n## Supporting\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    rows = [
        ("Routing top-1", "routing_top1"), ("Routing abstention", "routing_abstention"),
        ("Extraction F1", "extraction_f1"), ("Noise rejection", "noise_rejection"),
        ("Provenance accuracy", "provenance_accuracy"), ("Synthesis correctness", "synthesis_correctness"),
        ("Compilation fidelity", "compilation_fidelity"), ("Determinism", "determinism"),
        ("End-to-end", "e2e"), ("Calibration (ECE)", "calibration_ece"),
    ]
    for label, key in rows:
        if key not in m:
            continue
        if key == "calibration_ece":
            L.append(f"| {label} | {m[key]['mean']:.3f} |")
        else:
            L.append(f"| {label} | {_fmt(m[key])} |")
    j = sc["judge"]
    L.append(f"| Judge agreement (κ vs human, n={j.get('n','?')}) | {j['kappa']}{' ⚠ low-trust' if j['low_trust'] else ''} |")

    cal = sc.get("calibration")
    if cal:
        L.append("\n## Calibration (resolver confidence)\n")
        ci = cal.get("ci95", [0, 0])
        L.append(f"ECE = **{cal.get('ece')}** · 95% CI [{ci[0]}, {ci[1]}] · n={cal.get('n')} committed · {cal.get('bins')} bins (bootstrap)\n")
        L.append("Reliability diagram (confidence → empirical accuracy; ideal = equal):\n")
        L.append("```")
        L.append(f"{'bin':>10} {'n':>4} {'conf':>6} {'acc':>6}")
        for b in cal.get("reliability", []):
            bar = "█" * round(b["accuracy"] * 20)
            L.append(f"{b['lo']:.1f}-{b['hi']:.1f} {b['n']:>4} {b['avg_conf']:>6.3f} {b['accuracy']:>6.3f}  {bar}")
        L.append("```")
    if sc.get("extraction_by_kind"):
        L.append("\n## Extraction F1 by source kind\n")
        L.append("| Source kind | F1 | Noise rejection | Cases |")
        L.append("|---|---|---|---|")
        for kind, v in sc["extraction_by_kind"].items():
            nr = "—" if v["noise_rejection"] is None else f"{v['noise_rejection']*100:.0f}%"
            f1 = "—" if v["f1"] is None else f"{v['f1']:.2f}"
            L.append(f"| {kind} | {f1} | {nr} | {v['cases']} |")
    L.append("\n## Dataset\n")
    for stage, c in sc["dataset_counts"].items():
        L.append(f"- {stage}: {c['total']} cases ({c['test']} test / {c['dev']} dev)")
    L.append(f"\nContamination check: {'clean ✅' if sc['contamination']['clean'] else 'LEAK ❌ ' + str(sc['contamination']['leaks'])}")
    co = sc["cost_latency"]
    L.append(f"\nCost/latency: resolve {co.get('resolve_ms_p50','?')}ms p50 · "
             f"extraction {co.get('extraction_tokens','?')} tok/artifact (fixture=0)")
    return "\n".join(L) + "\n"


def to_html(sc: dict) -> str:
    md = to_markdown(sc)
    body = md.replace("&", "&amp;").replace("<", "&lt;")
    return ("<!doctype html><meta charset='utf-8'><title>CBE Scorecard</title>"
            "<style>body{font:14px ui-monospace,monospace;max-width:900px;margin:40px auto;"
            "background:#0a0a0a;color:#eee;padding:0 20px}h1{color:#7dd3fc}table{border-collapse:collapse}"
            "</style><pre>" + body + "</pre>")


def write(sc: dict, out_dir: str = REPORT_DIR) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = {
        "json": os.path.join(out_dir, "cbe_scorecard.json"),
        "md": os.path.join(out_dir, "cbe_scorecard.md"),
        "html": os.path.join(out_dir, "cbe_scorecard.html"),
    }
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(sc, f, indent=2)
    with open(paths["md"], "w", encoding="utf-8") as f:
        f.write(to_markdown(sc))
    with open(paths["html"], "w", encoding="utf-8") as f:
        f.write(to_html(sc))
    return paths
