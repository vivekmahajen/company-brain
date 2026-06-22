import { api } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  let sources: any[] = [];
  let artifacts: any[] = [];
  try {
    sources = await api.sources();
    artifacts = await api.artifacts();
  } catch {
    return <ApiDown />;
  }
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Sources</h1>
      <div className="grid grid-cols-2 gap-3">
        {sources.map((s) => (
          <div key={s.id} className="rounded-lg border border-neutral-800 p-4">
            <div className="font-medium">{s.name}</div>
            <div className="text-sm text-neutral-400">{s.kind} · {s.status}</div>
            <div className="text-xs text-neutral-500">last sync: {s.last_synced_at || "—"}</div>
          </div>
        ))}
      </div>
      <h2 className="text-lg font-medium">Ingested artifacts ({artifacts.length})</h2>
      <div className="space-y-2">
        {artifacts.map((a) => (
          <div key={a.id} className="rounded border border-neutral-800 p-3 text-sm">
            <span className="text-neutral-400">[{a.kind}] {a.author}</span>
            <div className="text-neutral-200">{a.content_text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ApiDown() {
  return (
    <div className="rounded border border-amber-800 bg-amber-900/30 p-4 text-sm text-amber-200">
      API unreachable. Start it: <code>uvicorn apps.api.main:app --reload</code> and set{" "}
      <code>NEXT_PUBLIC_API_URL</code>.
    </div>
  );
}
