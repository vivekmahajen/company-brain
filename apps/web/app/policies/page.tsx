"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Policy = { id: string; name: string; rule: any; enforcement: string };

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    name: "",
    tool: "",
    when: "",
    require: "human_approval",
    enforcement: "block",
  });
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setPolicies(await api.policies());
      setErr("");
    } catch {
      setErr("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const res = await api.createPolicy(form);
      if (res.error) setErr(res.error);
      else {
        setForm({ ...form, name: "", tool: "", when: "" });
        await load();
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api.deletePolicy(id);
    await load();
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Governance policies</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Enforcement guardrails checked at execution time. When a tool call matches a policy
          condition, the agent gets <code>approval_required</code> instead of acting.
        </p>
      </div>

      {err && <div className="rounded bg-red-900/30 p-2 text-sm text-red-200">{err}</div>}

      <form onSubmit={add} className="space-y-3 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-medium">Add a policy</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="refund_ceiling" />
          <Field label="Tool" value={form.tool} onChange={(v) => setForm({ ...form, tool: v })} placeholder="stripe_refund" />
          <Field
            label="Condition (field op number)"
            value={form.when}
            onChange={(v) => setForm({ ...form, when: v })}
            placeholder="amount > 1000"
          />
          <Field label="Require" value={form.require} onChange={(v) => setForm({ ...form, require: v })} placeholder="human_approval" />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-neutral-400">Enforcement</label>
          <select
            value={form.enforcement}
            onChange={(e) => setForm({ ...form, enforcement: e.target.value })}
            className="rounded border border-neutral-700 bg-neutral-900 p-1 text-sm"
          >
            <option value="block">block</option>
            <option value="warn">warn</option>
            <option value="log">log</option>
          </select>
          <button
            disabled={busy}
            className="ml-auto rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Add policy"}
          </button>
        </div>
        <p className="text-xs text-neutral-500">
          Condition must be <code>&lt;field&gt; &lt;op&gt; &lt;number&gt;</code> (op ∈ &gt; &gt;= &lt; &lt;= ==),
          e.g. <code>discount_percent &gt; 20</code>. The field is read from the agent&apos;s tool inputs.
        </p>
      </form>

      <div className="space-y-2">
        {policies.map((p) => (
          <div key={p.id} className="flex items-center justify-between rounded-lg border border-neutral-800 p-3 text-sm">
            <div>
              <span className="font-medium">{p.name}</span>{" "}
              <span className="text-neutral-400">
                — when <code>{p.rule?.tool}</code> and <code>{p.rule?.when}</code> → {p.rule?.require}
              </span>
              <span className="ml-2 rounded bg-neutral-800 px-2 text-xs text-neutral-300">{p.enforcement}</span>
            </div>
            <button onClick={() => remove(p.id)} className="rounded bg-neutral-700 px-2 py-1 text-xs hover:bg-red-700">
              delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-400">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 p-2"
      />
    </label>
  );
}
