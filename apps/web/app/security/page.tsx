"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Audit = {
  id: string;
  actor: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  meta: Record<string, unknown>;
  at: string;
};

export default function SecurityPage() {
  const [rows, setRows] = useState<Audit[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      setRows(await api.audit(100));
      setErr("");
    } catch {
      setErr("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function exportData() {
    setMsg("");
    try {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `company-brain-export-${data.org_id?.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMsg("Export downloaded.");
    } catch {
      setErr("Export failed.");
    }
  }

  async function erase() {
    if (!confirm("Irreversibly delete ALL data for this tenant? This cannot be undone.")) return;
    const res = await api.deleteOrg();
    setMsg(res.detail || `Deleted: ${Object.keys(res.deleted || {}).length} tables`);
    await load();
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Security &amp; compliance</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Audit trail of security-relevant actions, plus GDPR data export and right-to-erasure.
        </p>
      </div>

      {err && <div className="rounded bg-red-900/30 p-2 text-sm text-red-200">{err}</div>}
      {msg && <div className="rounded bg-emerald-900/30 p-2 text-sm text-emerald-200">{msg}</div>}

      <section className="flex flex-wrap gap-3">
        <button onClick={exportData} className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500">
          Download data export (JSON)
        </button>
        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/audit?format=csv`}
          className="rounded border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800"
        >
          Download audit log (CSV)
        </a>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Audit log ({rows.length})</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-left text-xs text-neutral-500">
              <th className="py-1.5">When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Target</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-neutral-900">
                <td className="py-1.5 font-mono text-xs text-neutral-400">{r.at?.slice(0, 19).replace("T", " ")}</td>
                <td className="text-neutral-300">{r.actor}</td>
                <td className="font-mono text-xs text-emerald-300">{r.action}</td>
                <td className="text-xs text-neutral-400">
                  {r.target_type ? `${r.target_type} ${String(r.target_id || "").slice(0, 8)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="mt-2 text-sm text-neutral-500">No audited actions yet.</div>}
      </section>

      <section className="rounded-lg border border-red-900/60 p-4">
        <h2 className="text-lg font-medium text-red-300">Danger zone</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Permanently erase this tenant&apos;s data (GDPR right-to-erasure). The default demo org is protected.
        </p>
        <button onClick={erase} className="mt-3 rounded bg-red-700 px-4 py-2 text-sm font-medium hover:bg-red-600">
          Erase tenant data
        </button>
      </section>
    </div>
  );
}
