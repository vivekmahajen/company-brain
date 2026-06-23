"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function AccessPage() {
  const [principals, setPrincipals] = useState<any[]>([]);
  const [token, setToken] = useState("agent-sales-token");
  const [task, setTask] = useState("a customer wants their money back");
  const [view, setView] = useState<any>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.accessPrincipals().then(setPrincipals).catch(() => setErr("API unreachable."));
    api.accessSources().then(setSources).catch(() => {});
    api.accessAudit().then(setAudit).catch(() => {});
  }, []);

  async function run() {
    const r = await api.viewAs(token, task);
    setView(r);
    api.accessAudit().then(setAudit).catch(() => {});
  }

  if (err) return <div className="text-amber-300">{err}</div>;

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Access — permissions-aware view</h1>
        <p className="mt-1 text-sm text-neutral-400">
          A skill's visibility is the most-restrictive intersection of every source it draws on.
          "View as" any principal to see exactly what their agent would get — no more, no less.
        </p>
      </div>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 text-lg font-medium">View as</h2>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
          >
            {principals.map((p) => (
              <option key={p.token} value={p.token}>
                {p.label}
              </option>
            ))}
          </select>
          <input
            value={task}
            onChange={(e) => setTask(e.target.value)}
            className="flex-1 rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
          />
          <button onClick={run} className="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500">
            View
          </button>
        </div>

        {view && (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <span className="text-neutral-400">Visible skills:</span>{" "}
              {view.visible_skills?.length ? (
                view.visible_skills.map((s: any) => (
                  <span key={s.slug} className="mr-2 rounded bg-emerald-900/40 px-2 py-0.5 text-emerald-200">
                    {s.slug}
                  </span>
                ))
              ) : (
                <span className="text-neutral-500">none</span>
              )}
            </div>
            <div>
              <span className="text-neutral-400">resolve(&quot;{task}&quot;):</span>{" "}
              {view.routes?.length ? (
                view.routes.map((r: any) => (
                  <span key={r.slug} className="mr-2 rounded bg-neutral-800 px-2 py-0.5">
                    {r.slug}
                  </span>
                ))
              ) : (
                <span className="text-amber-300">abstained / nothing visible</span>
              )}
            </div>
            <div className="text-xs text-neutral-500">
              MCP tools exposed: {view.tools?.filter((t: string) => t.includes("__")).join(", ") || "—"}
            </div>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Source ACLs (mirrored from sources)</h2>
        <div className="space-y-2">
          {sources.map((s) => (
            <div key={s.source} className="rounded border border-neutral-800 p-3 text-sm">
              <span className="font-medium">{s.source}</span>{" "}
              <span className="text-neutral-500">({s.kind})</span> →{" "}
              {s.acls.length ? (
                s.acls.map((a: any, i: number) => (
                  <span key={i} className="mr-2 rounded bg-neutral-800 px-2 py-0.5 text-xs">
                    {a.access} {a.group} <span className="text-neutral-500">[{a.origin}]</span>
                  </span>
                ))
              ) : (
                <span className="text-amber-300 text-xs">no ACL — default-deny</span>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Access audit log</h2>
        <div className="space-y-1 text-xs font-mono">
          {audit.slice(0, 30).map((a, i) => (
            <div key={i} className={a.decision === "deny" ? "text-red-300" : "text-neutral-400"}>
              {a.decision.toUpperCase()} {a.action} {a.target_type}:{a.target_id?.slice(0, 8)} — {a.reason}
            </div>
          ))}
          {audit.length === 0 && <div className="text-neutral-500">No decisions logged yet.</div>}
        </div>
      </section>
    </div>
  );
}
