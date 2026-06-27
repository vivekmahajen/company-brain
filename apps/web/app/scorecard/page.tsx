"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Sc = {
  org_id: string;
  readiness: number;
  skills: { total: number; approved: number; needs_review: number };
  knowledge: { total: number; approved: number; needs_review: number; superseded: number; provenance_coverage: number };
  capabilities: { total: number; compiled: number };
  governance: { guardrails: number; policies: number };
  sources: { total: number; synced: number };
  health: { unroutable_skills: string[]; staleness_signals: number };
  subscores: Record<string, number>;
};

export default function ScorecardPage() {
  const [sc, setSc] = useState<Sc | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.scorecard().then(setSc).catch(() => setErr("API unreachable."));
  }, []);

  if (err) return <div className="rounded bg-red-900/30 p-3 text-sm text-red-200">{err}</div>;
  if (!sc) return <div className="text-neutral-400">Loading…</div>;

  const good = sc.readiness >= 75;
  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Brain scorecard</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Your brain&apos;s health and governance posture — on your data. (Most products report recall on a
          public benchmark; we report yours.)
        </p>
      </div>

      <div className={`rounded-lg border p-5 ${good ? "border-emerald-800 bg-emerald-900/10" : "border-amber-800 bg-amber-900/10"}`}>
        <div className="text-sm text-neutral-400">Readiness</div>
        <div className="mt-1 text-5xl font-semibold">{sc.readiness}<span className="text-2xl text-neutral-500">/100</span></div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {Object.entries(sc.subscores).map(([k, v]) => (
            <span key={k} className="rounded-full border border-neutral-700 px-2 py-0.5 text-neutral-300">
              {k} {(v * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Tile label="Skills" value={`${sc.skills.approved}/${sc.skills.total}`} sub={`${sc.skills.needs_review} need review`} />
        <Tile label="Knowledge units" value={`${sc.knowledge.approved}`} sub={`${sc.knowledge.needs_review} review · ${sc.knowledge.superseded} superseded`} />
        <Tile label="Provenance coverage" value={`${(sc.knowledge.provenance_coverage * 100).toFixed(0)}%`} sub="approved units with a source" />
        <Tile label="Capabilities" value={`${sc.capabilities.compiled}/${sc.capabilities.total}`} sub="compiled into skills" />
        <Tile label="Governance" value={`${sc.governance.guardrails} guardrails`} sub={`${sc.governance.policies} policies`} />
        <Tile label="Sources" value={`${sc.sources.synced}/${sc.sources.total}`} sub="synced" />
      </div>

      {(sc.health.unroutable_skills.length > 0 || sc.health.staleness_signals > 0) && (
        <div className="rounded-lg border border-amber-800 bg-amber-900/10 p-4 text-sm text-amber-200">
          {sc.health.unroutable_skills.length > 0 && <div>⚠ {sc.health.unroutable_skills.length} unroutable skill(s)</div>}
          {sc.health.staleness_signals > 0 && <div>⚠ {sc.health.staleness_signals} staleness signal(s) — knowledge may be out of date</div>}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="text-sm text-neutral-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-neutral-500">{sub}</div>
    </div>
  );
}
