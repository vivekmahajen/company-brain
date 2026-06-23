import Link from "next/link";
import { api } from "../lib/api";
import Approvals from "./approvals";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  let skills: any[] = [];
  let staleness: any[] = [];
  let drift: any[] = [];
  let knowledge: any[] = [];
  try {
    [skills, staleness, drift, knowledge] = await Promise.all([
      api.skills(),
      api.staleness(),
      api.drift(),
      api.knowledge(),
    ]);
  } catch {
    return <div className="text-amber-300">API unreachable.</div>;
  }
  const needsReview = skills.filter((s) => s.status === "needs_review");
  const lowConf = knowledge.filter((k) => k.status === "needs_review");

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Review queue</h1>

      <Approvals />

      <Section title={`Skills needing review (${needsReview.length})`}>
        {needsReview.map((s) => (
          <Link key={s.slug} href={`/skills/${s.slug}`} className="block rounded border border-neutral-800 p-3 text-sm hover:border-neutral-600">
            {s.title} — v{s.version}
          </Link>
        ))}
      </Section>

      <Section title={`Low-confidence knowledge (${lowConf.length})`}>
        {lowConf.map((k) => (
          <div key={k.id} className="rounded border border-neutral-800 p-3 text-sm">
            <span className="text-neutral-500">[{k.type}] conf {(k.confidence * 100).toFixed(0)}%</span> {k.statement}
          </div>
        ))}
      </Section>

      <Section title={`Staleness signals (${staleness.length})`}>
        {staleness.map((s) => (
          <div key={s.id} className="rounded border border-neutral-800 p-3 text-sm text-amber-200">{s.reason}</div>
        ))}
      </Section>

      <Section title={`Drift alerts (${drift.length})`}>
        {drift.map((d) => (
          <div key={d.log_id} className="rounded border border-red-900 bg-red-900/20 p-3 text-sm text-red-200">
            expected <b>{d.expected?.decision}</b> but observed <b>{d.actual}</b> — {JSON.stringify(d.input)}
          </div>
        ))}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-lg font-medium">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
