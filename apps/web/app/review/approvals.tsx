"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Approval = {
  id: string;
  tool_name: string;
  requested_by: string;
  input: any;
  resolved_facts: any;
  gate_reason: string;
  created_at: string;
};

export default function Approvals() {
  const [items, setItems] = useState<Approval[]>([]);
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      setItems(await api.approvals());
    } catch {
      setMsg("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function decide(id: string, decision: "approve" | "reject") {
    const res = await api.decideApproval(id, decision);
    if (res.error) setMsg(res.error);
    else setMsg(`${decision}d ${id.slice(0, 8)}${res.execution ? ` → ${res.execution.status}` : ""}`);
    await load();
  }

  return (
    <section>
      <h2 className="mb-2 text-lg font-medium">Held actions — approvals ({items.length})</h2>
      <p className="mb-2 text-xs text-neutral-400">
        Side-effecting tool calls whose gate tripped. Approving executes the held action server-side
        (separation of duties + idempotency enforced by the executor).
      </p>
      {msg && <div className="mb-2 rounded bg-neutral-800 p-2 text-xs text-neutral-200">{msg}</div>}
      <div className="space-y-2">
        {items.map((a) => (
          <div key={a.id} className="rounded-lg border border-amber-900/60 bg-amber-900/10 p-3 text-sm">
            <div className="flex items-center justify-between">
              <div>
                <code className="text-amber-200">{a.tool_name}</code>{" "}
                <span className="text-neutral-400">requested by {a.requested_by}</span>
              </div>
              <div className="flex gap-2">
                <button onClick={() => decide(a.id, "approve")} className="rounded bg-emerald-600 px-3 py-1 text-xs hover:bg-emerald-500">
                  Approve
                </button>
                <button onClick={() => decide(a.id, "reject")} className="rounded bg-neutral-700 px-3 py-1 text-xs hover:bg-red-700">
                  Reject
                </button>
              </div>
            </div>
            <div className="mt-1 text-xs text-neutral-400">gate: {a.gate_reason}</div>
            <div className="mt-1 text-xs text-neutral-500">
              args {JSON.stringify(a.input)} · server facts {JSON.stringify(a.resolved_facts)}
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="text-sm text-neutral-500">No pending approvals.</div>}
      </div>
    </section>
  );
}
