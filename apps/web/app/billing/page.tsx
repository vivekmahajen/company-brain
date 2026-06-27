"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Usage = {
  plan: string;
  period: string;
  limits: { max_sources: number | null; max_custom_capabilities: number | null; monthly_extraction_usd: number | null };
  usage: { sources: number; custom_capabilities: number; extraction_usd: number };
  remaining: { sources: number | null; custom_capabilities: number | null; extraction_usd: number | null };
};
type Plan = {
  label: string;
  price_usd_month: number | null;
  max_sources: number | null;
  max_custom_capabilities: number | null;
  monthly_extraction_usd: number | null;
};

const cap = (n: number | null) => (n === null ? "∞" : String(n));

export default function BillingPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [plans, setPlans] = useState<Record<string, Plan>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      const [u, p] = await Promise.all([api.usage(), api.billingPlans()]);
      setUsage(u);
      setPlans(p);
      setErr("");
    } catch {
      setErr("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function pick(key: string) {
    setBusy(key);
    setErr("");
    try {
      const res = await api.checkout(key, typeof window !== "undefined" ? `${window.location.origin}/billing` : undefined);
      if (res.error || res.detail) {
        setErr(res.error || res.detail);
      } else if (res.mode === "stripe" || res.mode === "stub") {
        window.location.href = res.url; // → Stripe Checkout (or stub confirm)
        return;
      } else if (res.mode === "contact") {
        setErr("Enterprise is custom-priced — contact sales.");
      } else {
        await load(); // 'direct' (free downgrade) applied
      }
    } finally {
      setBusy("");
    }
  }

  if (err) return <div className="rounded bg-red-900/30 p-3 text-sm text-red-200">{err}</div>;
  if (!usage) return <div className="text-neutral-400">Loading…</div>;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Billing &amp; usage</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Plan <b className="capitalize">{usage.plan}</b> · billing period {usage.period}. Extraction
          spend is metered on real model cost.
        </p>
      </div>

      {/* Usage meters */}
      <section className="grid grid-cols-3 gap-4">
        <Meter label="Sources" used={usage.usage.sources} cap={usage.limits.max_sources} />
        <Meter label="Custom capabilities" used={usage.usage.custom_capabilities} cap={usage.limits.max_custom_capabilities} />
        <Meter
          label="Extraction spend"
          used={usage.usage.extraction_usd}
          cap={usage.limits.monthly_extraction_usd}
          fmt={(v) => `$${v.toFixed(2)}`}
        />
      </section>

      {/* Plans */}
      <section>
        <h2 className="mb-2 text-lg font-medium">Plans</h2>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(plans).map(([key, p]) => {
            const current = key === usage.plan;
            return (
              <div
                key={key}
                className={`rounded-lg border p-4 ${current ? "border-emerald-700 bg-emerald-900/10" : "border-neutral-800"}`}
              >
                <div className="font-medium">{p.label}</div>
                <div className="mt-1 text-2xl font-semibold">
                  {p.price_usd_month === null ? "Custom" : p.price_usd_month === 0 ? "Free" : `$${p.price_usd_month}`}
                  {p.price_usd_month ? <span className="text-sm text-neutral-500">/mo</span> : null}
                </div>
                <ul className="mt-3 space-y-1 text-xs text-neutral-400">
                  <li>{cap(p.max_sources)} sources</li>
                  <li>{cap(p.max_custom_capabilities)} capabilities</li>
                  <li>{p.monthly_extraction_usd === null ? "∞" : `$${p.monthly_extraction_usd}`}/mo extraction</li>
                </ul>
                <button
                  disabled={current || busy === key}
                  onClick={() => pick(key)}
                  className={`mt-4 w-full rounded px-3 py-1.5 text-sm font-medium ${
                    current
                      ? "cursor-default bg-neutral-800 text-neutral-400"
                      : "bg-emerald-600 hover:bg-emerald-500"
                  }`}
                >
                  {current ? "Current plan" : busy === key ? "Switching…" : "Switch"}
                </button>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          Switching is instant here (self-serve). Stripe checkout wraps this step once billing keys are
          configured.
        </p>
      </section>
    </div>
  );
}

function Meter({
  label,
  used,
  cap,
  fmt = (v: number) => String(v),
}: {
  label: string;
  used: number;
  cap: number | null;
  fmt?: (v: number) => string;
}) {
  const pct = cap ? Math.min(100, (used / cap) * 100) : 0;
  const over = cap !== null && used >= cap;
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="text-sm text-neutral-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold">
        {fmt(used)} <span className="text-sm text-neutral-500">/ {cap === null ? "∞" : fmt(cap)}</span>
      </div>
      <div className="mt-2 h-2 rounded bg-neutral-900">
        <div
          className={`h-2 rounded ${over ? "bg-red-500" : "bg-emerald-600"}`}
          style={{ width: `${cap === null ? 4 : pct}%` }}
        />
      </div>
      {over && <div className="mt-1 text-xs text-red-400">limit reached — upgrade to add more</div>}
    </div>
  );
}
