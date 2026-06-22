import { api } from "../lib/api";

export const dynamic = "force-dynamic";

const BADGE: Record<string, string> = {
  approved: "bg-emerald-900/50 text-emerald-300",
  needs_review: "bg-amber-900/50 text-amber-300",
  superseded: "bg-neutral-800 text-neutral-400 line-through",
  draft: "bg-neutral-800 text-neutral-300",
};

export default async function KnowledgePage() {
  let kus: any[] = [];
  try {
    kus = await api.knowledge();
  } catch {
    return <div className="text-amber-300">API unreachable.</div>;
  }
  return (
    <div className="max-w-4xl space-y-4">
      <h1 className="text-2xl font-semibold">Knowledge units</h1>
      <p className="text-sm text-neutral-400">
        Typed, provenance-linked facts. Superseded units are retired bitemporally, never deleted.
      </p>
      {kus.map((k) => (
        <div key={k.id} className="rounded-lg border border-neutral-800 p-4">
          <div className="flex items-center gap-2 text-xs">
            <span className="rounded bg-neutral-800 px-2 py-0.5 text-neutral-300">{k.type}</span>
            <span className={`rounded px-2 py-0.5 ${BADGE[k.status] || ""}`}>{k.status}</span>
            <span className="text-neutral-500">conf {(k.confidence * 100).toFixed(0)}%</span>
            {k.topic && <span className="text-neutral-500">· {k.topic}</span>}
            {k.superseded_by && <span className="text-neutral-500">· superseded</span>}
          </div>
          <div className="mt-2 text-sm">{k.statement}</div>
          {k.provenance?.length > 0 && (
            <div className="mt-2 text-xs text-neutral-500">
              ↳ provenance: {k.provenance.map((p: any) => `"${p.span?.slice(0, 50)}"`).join("  ·  ")}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
