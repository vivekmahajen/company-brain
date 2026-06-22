"use client";

import { useState } from "react";
import { api, type Route } from "./lib/api";

export default function Dashboard() {
  const [task, setTask] = useState("a customer is angry and wants their money back");
  const [routes, setRoutes] = useState<Route[]>([]);
  const [skill, setSkill] = useState<any>(null);
  const [dryRun, setDryRun] = useState<any>(null);
  const [amount, setAmount] = useState(620);
  const [loading, setLoading] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState("");

  async function testBrain() {
    setLoading(true);
    setDryRun(null);
    try {
      const r = await api.resolve(task);
      setRoutes(r.routes);
      if (r.routes[0]) setSkill(await api.skill(r.routes[0].slug));
    } finally {
      setLoading(false);
    }
  }

  async function runPipeline() {
    setPipelineMsg("Running ingest → extract → synthesize → compile → resolve…");
    const r = await api.runPipeline();
    setPipelineMsg(
      `Compiled ${r.skill?.slug} v${r.skill?.version} (${r.skill?.status}). ` +
        `${r.extract.units_created} KUs, ${r.synthesis.merged_duplicates} merged, ` +
        `${r.synthesis.superseded_conflicts} superseded.`
    );
  }

  async function dryRunExecute() {
    if (!skill) return;
    const res = await api.execute(skill.slug, "stripe_refund", { order_id: "demo-1", amount });
    setDryRun(res);
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-neutral-400">
          The executable knowledge layer. Build the Brain, then test how an agent routes and acts.
        </p>
      </div>

      <section className="rounded-lg border border-neutral-800 p-4">
        <button onClick={runPipeline} className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500">
          Rebuild the Brain
        </button>
        {pipelineMsg && <p className="mt-3 text-sm text-neutral-300">{pipelineMsg}</p>}
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 text-lg font-medium">Test the Brain</h2>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={2}
          className="w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
        />
        <button
          onClick={testBrain}
          disabled={loading}
          className="mt-2 rounded bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? "Resolving…" : "Resolve"}
        </button>

        {routes.length > 0 && (
          <div className="mt-4 space-y-2">
            <h3 className="text-sm font-semibold text-neutral-300">Routing</h3>
            {routes.map((r) => (
              <div key={r.slug} className="rounded border border-neutral-800 p-2 text-sm">
                <span className="font-medium">{r.title}</span>{" "}
                <span className="text-neutral-400">({r.slug})</span> — confidence{" "}
                <span className="text-emerald-400">{(r.confidence * 100).toFixed(0)}%</span>
                <div className="text-xs text-neutral-500">{r.reason}</div>
              </div>
            ))}
          </div>
        )}

        {skill && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-neutral-300">Resolved skill: {skill.slug}</h3>
            <pre className="mt-2 max-h-80 overflow-auto rounded bg-neutral-900 p-3 text-xs text-neutral-300">
              {skill.body_md}
            </pre>

            <div className="mt-3 flex items-center gap-2">
              <span className="text-sm">Dry-run refund amount $</span>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="w-24 rounded border border-neutral-700 bg-neutral-900 p-1 text-sm"
              />
              <button onClick={dryRunExecute} className="rounded bg-neutral-700 px-3 py-1 text-sm hover:bg-neutral-600">
                Simulate agent action
              </button>
            </div>
            {dryRun && (
              <div
                className={`mt-2 rounded p-2 text-sm ${
                  dryRun.outcome === "approval_required" ? "bg-amber-900/40 text-amber-200" : "bg-emerald-900/40 text-emerald-200"
                }`}
              >
                <b>{dryRun.outcome}</b>
                {dryRun.reason ? ` — ${dryRun.reason}` : ""}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
