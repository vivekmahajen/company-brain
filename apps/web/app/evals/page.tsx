import { api } from "../lib/api";

export const dynamic = "force-dynamic";

function pct(m: any) {
  if (!m) return "—";
  const v = (m.mean * 100).toFixed(1) + "%";
  return m.n >= 2 && m.ci95 > 0 ? `${v} ±${(m.ci95 * 100).toFixed(1)}` : v;
}

export default async function EvalsPage() {
  let sc: any = null;
  let runs: any[] = [];
  try {
    sc = await api.evalsLatest();
    runs = await api.evalsRuns();
  } catch {
    return <div className="text-amber-300">API unreachable.</div>;
  }
  if (!sc || sc.error) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold">Evals — CBE Scorecard</h1>
        <p className="mt-3 text-sm text-neutral-400">
          No runs yet. Run <code>make eval</code> (or <code>python -m apps.api.evals.run</code>) to
          generate the scorecard.
        </p>
      </div>
    );
  }

  const a = sc.attribution;
  const m = sc.metrics;
  const ns = sc.metric_n || {};
  const cal = sc.calibration;
  const supporting: [string, string][] = [
    ["Routing top-1", "routing_top1"],
    ["Routing abstention", "routing_abstention"],
    ["Extraction F1", "extraction_f1"],
    ["Noise rejection", "noise_rejection"],
    ["Provenance accuracy", "provenance_accuracy"],
    ["Synthesis correctness", "synthesis_correctness"],
    ["Compilation fidelity", "compilation_fidelity"],
    ["Determinism", "determinism"],
    ["End-to-end", "e2e"],
  ];

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Company Brain Eval (CBE)</h1>
        <p className="mt-1 text-xs text-neutral-500">
          <span className={`mr-2 rounded px-1.5 py-0.5 ${sc.mode?.startsWith("live") ? "bg-emerald-900/50 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>
            {sc.mode || "fixture"}
          </span>
          commit {a.commit_sha} · dataset {a.dataset_version} · {a.model_id} ({a.model_snapshot}) · {a.n_runs} runs ·{" "}
          <b>{a.split}</b> split · seed {a.seed}
        </p>
      </div>

      <div className="text-xs text-neutral-500">Deterministic governance — exact rates with n (model-independent):</div>
      <div className="grid grid-cols-3 gap-4">
        <Tile label="Guardrail Adherence (GAR)" value={pct(m.GAR)} good={m.GAR?.mean >= 1} sub={`deterministic · n=${ns.GAR ?? "?"} · 100% req`} />
        <Tile label="Permission Enforcement (PER)" value={pct(m.PER)} good={m.PER?.mean >= 1} sub={`deterministic · n=${ns.PER ?? "?"} · 100% req`} />
        <Tile label="Skill-Execution (SEC)" value={pct(m.SEC)} good={m.SEC?.mean >= 0.9} sub={`deterministic · n=${ns.SEC ?? "?"} · ≥90%`} />
      </div>

      {cal && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <h2 className="mb-1 text-lg font-medium">Calibration (resolver confidence)</h2>
          <p className="text-sm text-neutral-300">
            ECE <b>{cal.ece}</b> · 95% CI [{cal.ci95?.[0]}, {cal.ci95?.[1]}] · n={cal.n} committed · {cal.bins} bins
          </p>
          <div className="mt-2 space-y-1">
            {(cal.reliability || []).map((b: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs font-mono text-neutral-400">
                <span className="w-16">{b.lo}-{b.hi}</span>
                <span className="w-10">n={b.n}</span>
                <span className="w-16">conf {b.avg_conf}</span>
                <div className="h-3 flex-1 rounded bg-neutral-900">
                  <div className="h-3 rounded bg-emerald-600" style={{ width: `${b.accuracy * 100}%` }} />
                </div>
                <span className="w-12 text-right">acc {b.accuracy}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-lg font-medium">Supporting</h2>
        <table className="w-full text-sm">
          <tbody>
            {supporting.map(([label, key]) =>
              m[key] ? (
                <tr key={key} className="border-b border-neutral-800">
                  <td className="py-1.5 text-neutral-300">{label}</td>
                  <td className="py-1.5 text-right font-mono">{pct(m[key])}</td>
                </tr>
              ) : null
            )}
            <tr className="border-b border-neutral-800">
              <td className="py-1.5 text-neutral-300">Calibration (ECE)</td>
              <td className="py-1.5 text-right font-mono">{m.calibration_ece?.mean?.toFixed(3)}</td>
            </tr>
            <tr>
              <td className="py-1.5 text-neutral-300">Judge agreement (κ)</td>
              <td className="py-1.5 text-right font-mono">
                {sc.judge.kappa} {sc.judge.low_trust ? "⚠" : ""}
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="text-xs text-neutral-500">
        Contamination: {sc.contamination.clean ? "clean ✅" : "LEAK ❌"} · resolve{" "}
        {sc.cost_latency.resolve_ms_p50}ms p50 · gate <b className={sc.gates.overall === "PASS" ? "text-emerald-400" : "text-red-400"}>{sc.gates.overall}</b>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Trend ({runs.length} runs)</h2>
        <div className="space-y-1 text-xs font-mono">
          {runs.map((r) => (
            <div key={r.id} className="flex gap-4 text-neutral-400">
              <span>{r.commit_sha}</span>
              <span>GAR {((r.GAR ?? 0) * 100).toFixed(0)}%</span>
              <span>SEC {((r.SEC ?? 0) * 100).toFixed(0)}%</span>
              <span>{r.finished_at?.slice(0, 19).replace("T", " ")}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Tile({ label, value, good, sub }: { label: string; value: string; good: boolean; sub: string }) {
  return (
    <div className={`rounded-lg border p-4 ${good ? "border-emerald-800 bg-emerald-900/10" : "border-red-800 bg-red-900/10"}`}>
      <div className="text-sm text-neutral-400">{label}</div>
      <div className="mt-1 text-3xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-neutral-500">{sub}</div>
    </div>
  );
}
