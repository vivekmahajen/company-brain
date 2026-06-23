"use client";

import { useState } from "react";
import { api } from "../lib/api";

type Status = "idle" | "running" | "done" | "fail";
type Step = {
  key: string;
  title: string;
  narrative: string;
  status: Status;
  detail?: string;
};

const STEP_DEFS: Omit<Step, "status" | "detail">[] = [
  {
    key: "build",
    title: "1 · Build the brain",
    narrative: "Pull from Slack, Notion, GitHub, Linear, Gmail, Postgres, transcripts & Zendesk → extract typed knowledge → compile executable skills.",
  },
  {
    key: "route",
    title: "2 · Route a natural-language task",
    narrative: "An agent asks in plain English; the RESOLVER sends it to the right skill with a reason.",
  },
  {
    key: "provenance",
    title: "3 · Multi-source provenance",
    narrative: "Skills compile from several real source types — every rule is cited back to where it came from.",
  },
  {
    key: "exec_small",
    title: "4 · Governed execution (in policy)",
    narrative: "A $200 refund on a 12-day-old order is within policy → executes (sandbox).",
  },
  {
    key: "exec_gate",
    title: "5 · The approval gate fires",
    narrative: "A $620 refund trips the >$500 gate → held server-side, NO side effect. The gate reads the real order amount, not the agent's claim.",
  },
  {
    key: "approve",
    title: "6 · Human approves → it executes",
    narrative: "A human with approver rights releases the held action. The requester can't approve their own request.",
  },
  {
    key: "perms",
    title: "7 · Permissions — each agent sees only its domain",
    narrative: "Source permissions propagate through derived knowledge: a skill built from a private channel is invisible to other teams. This is the moat.",
  },
];

const AUDIENCES: Record<string, { label: string; intro: string; highlight: string[] }> = {
  security: {
    label: "Security buyer",
    intro:
      "Every agent action is permission-checked, gated, and audited at a single server-side choke point. An agent can't see — let alone execute — a skill outside its role, and high-value side effects are held for human approval. Both properties are measured deterministically at 100% (GAR + PER). Watch steps 5–7.",
    highlight: ["exec_gate", "approve", "perms"],
  },
  ops: {
    label: "Ops buyer",
    intro:
      "Your refund, incident, and pricing know-how — scattered across Slack, GitHub, email, call transcripts, and your database — becomes skills an agent executes correctly and safely, with a human in the loop on the risky calls. Watch steps 1–6.",
    highlight: ["build", "route", "exec_small", "exec_gate", "approve"],
  },
  engineering: {
    label: "Engineering",
    intro:
      "Fragmented sources → typed knowledge units with provenance → a deduplicated graph → compiled SKILL.md with tool bindings → served over MCP through one GovernedExecutor. Permissions propagate through derived knowledge; deterministic eval gates (GAR / PER / SEC) keep it honest. Watch all steps.",
    highlight: STEP_DEFS.map((s) => s.key),
  },
};

export default function DemoPage() {
  const [steps, setSteps] = useState<Step[]>(STEP_DEFS.map((s) => ({ ...s, status: "idle" })));
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [audience, setAudience] = useState<keyof typeof AUDIENCES>("security");

  function reset() {
    setSteps(STEP_DEFS.map((s) => ({ ...s, status: "idle" })));
    setDone(false);
  }

  function update(key: string, status: Status, detail?: string) {
    setSteps((prev) => prev.map((s) => (s.key === key ? { ...s, status, detail } : s)));
  }

  async function runStep(key: string, fn: () => Promise<string>) {
    update(key, "running");
    try {
      const detail = await fn();
      update(key, "done", detail);
      return true;
    } catch (e: any) {
      update(key, "fail", String(e?.message || e));
      return false;
    }
  }

  async function run() {
    setRunning(true);
    setDone(false);
    setSteps(STEP_DEFS.map((s) => ({ ...s, status: "idle" })));
    let approvalId = "";

    await runStep("build", async () => {
      const r = await api.runPipeline();
      const arts = (r.ingest || []).reduce((n: number, s: any) => n + (s.inserted || 0) + (s.skipped || 0), 0);
      return `Ingested ${arts} artifacts from ${r.ingest?.length || 0} sources → compiled ${r.skills?.length || 0} skills (${(r.skills || []).map((s: any) => s.slug).join(", ")}).`;
    });

    await runStep("route", async () => {
      const r = await api.resolve("a customer is angry and wants their money back");
      const top = r.routes?.[0];
      return top ? `→ ${top.slug} @ ${(top.confidence * 100).toFixed(0)}% — ${top.reason}` : "no route";
    });

    await runStep("provenance", async () => {
      const sk = await api.skill("respond-to-incident");
      const kinds = Array.from(new Set((sk.provenance || []).map((p: any) => String(p.source).split("/")[0])));
      return `respond-to-incident is cited from: ${kinds.join(", ")}.`;
    });

    await runStep("exec_small", async () => {
      const r = await api.execute("handle-refund", "stripe_refund", { order_id: "55", amount: 200 });
      return `$200 on order #55 → ${r.status}${r.result?.refund_id ? ` (${r.result.refund_id})` : ""}.`;
    });

    await runStep("exec_gate", async () => {
      const r = await api.execute("handle-refund", "stripe_refund", { order_id: "1234", amount: 620 });
      approvalId = r.approval_id || "";
      return `$620 on order #1234 → ${r.status}. Gate: ${r.gate_reason || "—"}. No refund issued.`;
    });

    await runStep("approve", async () => {
      if (!approvalId) return "no approval to release";
      const r = await api.decideApproval(approvalId, "approve");
      return `Approved → held action executed: ${r.execution?.status || r.status}.`;
    });

    await runStep("perms", async () => {
      const roles = [
        ["agent-support-token", "Support agent"],
        ["agent-sales-token", "Sales agent"],
        ["agent-eng-token", "Eng agent"],
      ];
      const lines: string[] = [];
      for (const [token, label] of roles) {
        const r = await api.viewAs(token);
        const slugs = (r.visible_skills || []).map((s: any) => s.slug);
        lines.push(`${label}: ${slugs.length ? slugs.join(", ") : "—"}`);
      }
      return lines.join("   ·   ");
    });

    setRunning(false);
    setDone(true);
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">🧠 Company Brain — guided demo</h1>
        <p className="mt-1 text-sm text-neutral-400">
          One click runs the whole story: fragmented sources → executable, governed, permissions-aware
          skills an agent can act on.
        </p>
      </div>

      {/* Audience selector — tailors the framing + highlights the key steps. */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(AUDIENCES) as (keyof typeof AUDIENCES)[]).map((k) => (
          <button
            key={k}
            onClick={() => setAudience(k)}
            className={`rounded-full px-3 py-1 text-sm ${
              audience === k ? "bg-blue-600 text-white" : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
            }`}
          >
            {AUDIENCES[k].label}
          </button>
        ))}
      </div>
      <div className="rounded-lg border border-blue-900/50 bg-blue-900/10 p-3 text-sm text-neutral-200">
        {AUDIENCES[audience].intro}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={run}
          disabled={running}
          className="rounded-lg bg-emerald-600 px-6 py-3 text-base font-semibold hover:bg-emerald-500 disabled:opacity-50"
        >
          {running ? "Running…" : done ? "Run the demo again" : "▶ Run the demo"}
        </button>
        <button
          onClick={reset}
          disabled={running}
          className="rounded-lg border border-neutral-700 px-4 py-3 text-sm text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
        >
          Reset
        </button>
      </div>

      <div className="space-y-3">
        {steps.map((s) => {
          const keyForAudience = AUDIENCES[audience].highlight.includes(s.key);
          return (
          <div
            key={s.key}
            className={`rounded-lg border p-4 ${
              keyForAudience && audience !== "engineering" ? "ring-1 ring-blue-500/40 " : ""
            }${
              s.status === "done"
                ? "border-emerald-800 bg-emerald-900/10"
                : s.status === "running"
                ? "border-blue-700 bg-blue-900/10"
                : s.status === "fail"
                ? "border-red-800 bg-red-900/10"
                : keyForAudience && audience !== "engineering"
                ? "border-blue-900/60"
                : "border-neutral-800"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{s.title}</span>
              <span className="text-sm">
                {s.status === "done" ? "✅" : s.status === "running" ? "⏳" : s.status === "fail" ? "❌" : "•"}
              </span>
            </div>
            <p className="mt-1 text-xs text-neutral-400">{s.narrative}</p>
            {s.detail && (
              <pre className="mt-2 whitespace-pre-wrap rounded bg-neutral-900 p-2 text-xs text-neutral-200">
                {s.detail}
              </pre>
            )}
          </div>
          );
        })}
      </div>

      {done && (
        <div className="rounded-lg border border-emerald-800 bg-emerald-900/20 p-4 text-sm text-emerald-200">
          That's the whole loop: real sources → governed, executable skills → enforced at serve time, with
          every guardrail, approval gate, and permission boundary holding. Explore the{" "}
          <a className="underline" href="/access">Access</a>,{" "}
          <a className="underline" href="/skills">Skills</a>, and{" "}
          <a className="underline" href="/evals">Evals</a> pages for the details.
        </div>
      )}
    </div>
  );
}
