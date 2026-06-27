"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Connector = {
  kind: string;
  auth: string;
  secret_fields: string[];
  oauth_configured?: boolean;
  authorize_path?: string;
};
type Source = {
  id: string;
  kind: string;
  name: string;
  status: string;
  last_synced_at: string | null;
  artifact_count?: number;
  acl_groups?: string[];
};
type Step = { key: string; label: string; done: boolean };

const CONFIG_HINT: Record<string, string> = {
  github: "repos (comma-separated, e.g. owner/repo)",
  slack: "channels (comma-separated, e.g. support,refunds)",
  zendesk: "subdomain",
};

export default function OnboardingPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [persistent, setPersistent] = useState<boolean | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState<{ name: string; secrets: Record<string, string>; settings: string }>({
    name: "",
    secrets: {},
    settings: "",
  });
  const [msg, setMsg] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [c, s, ob, db] = await Promise.all([
        api.connectors(),
        api.sources(),
        api.onboarding(),
        api.dbHealth().catch(() => null),
      ]);
      setConnectors(c);
      setSources(s);
      setSteps(ob.steps || []);
      setPersistent(db ? db.persistent : null);
      setErr("");
    } catch {
      setErr("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  function settingsToConfig(kind: string, text: string): Record<string, unknown> {
    const t = text.trim();
    if (!t) return {};
    if (kind === "github") return { repos: t.split(",").map((x) => x.trim()).filter(Boolean) };
    if (kind === "slack") return { channels: t.split(",").map((x) => x.trim()).filter(Boolean) };
    if (kind === "zendesk") return { subdomain: t };
    return {};
  }

  async function oauthConnect(kind: string) {
    setErr("");
    try {
      const res = await api.connectAuthorize(kind);
      if (res.configured && res.authorize_url) window.location.href = res.authorize_url;
      else setErr(`${kind}: OAuth app not configured (${(res.needed_env || []).join(", ")})`);
    } catch {
      setErr("Failed to start OAuth.");
    }
  }

  async function tokenConnect(c: Connector, e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const secrets = Object.fromEntries(
        Object.entries(form.secrets).filter(([, v]) => v).map(([k, v]) => [k, v])
      );
      const config = settingsToConfig(c.kind, form.settings);
      const res = await api.connectSource({
        kind: c.kind,
        name: form.name || `${c.kind} source`,
        config,
        secrets: Object.keys(secrets).length ? secrets : undefined,
      });
      if (res.error) setErr(res.error);
      else {
        setOpen(null);
        setForm({ name: "", secrets: {}, settings: "" });
        await load();
      }
    } finally {
      setBusy(false);
    }
  }

  async function sync(id: string) {
    setMsg({ ...msg, [id]: "syncing…" });
    try {
      const r = await api.syncSource(id);
      setMsg({ ...msg, [id]: r.error ? r.error : `inserted ${r.inserted ?? 0}, skipped ${r.skipped ?? 0}` });
    } catch {
      setMsg({ ...msg, [id]: "sync failed" });
    }
    await load();
  }

  async function configure(s: Source) {
    const text = prompt(`Set ${CONFIG_HINT[s.kind] || "config"} for ${s.name}:`);
    if (text == null) return;
    await api.configureSource(s.id, settingsToConfig(s.kind, text));
    setMsg({ ...msg, [s.id]: "configured — sync to apply" });
    await load();
  }

  async function remove(id: string) {
    if (!confirm("Remove this source and its data?")) return;
    await api.deleteSource(id);
    await load();
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Connect your tools</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Connect a source, sync it, and the brain compiles your knowledge into governed skills.
          One OAuth app per provider; each company authorizes it into their own workspace.
        </p>
      </div>

      {persistent === false && (
        <div className="rounded border border-amber-800 bg-amber-900/30 p-3 text-sm text-amber-200">
          ⚠ Running on ephemeral SQLite — connected sources won&apos;t survive a redeploy. Set{" "}
          <code>DATABASE_URL</code> to Postgres to persist.
        </div>
      )}
      {err && <div className="rounded bg-red-900/30 p-2 text-sm text-red-200">{err}</div>}

      {/* Onboarding progress */}
      <div className="flex flex-wrap gap-2">
        {steps.map((st) => (
          <div
            key={st.key}
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
              st.done ? "border-emerald-800 bg-emerald-900/20 text-emerald-300" : "border-neutral-700 text-neutral-400"
            }`}
          >
            <span>{st.done ? "✓" : "○"}</span>
            {st.label}
          </div>
        ))}
      </div>

      {/* Connector catalog */}
      <section>
        <h2 className="mb-2 text-lg font-medium">Add a source</h2>
        <div className="grid grid-cols-2 gap-3">
          {connectors.map((c) => (
            <div key={c.kind} className="rounded-lg border border-neutral-800 p-4">
              <div className="flex items-center justify-between">
                <div className="font-medium capitalize">{c.kind}</div>
                <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">{c.auth}</span>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {c.auth === "oauth" && (
                  <button
                    onClick={() => oauthConnect(c.kind)}
                    disabled={!c.oauth_configured}
                    title={c.oauth_configured ? "" : "OAuth app not configured on the server"}
                    className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500 disabled:opacity-40"
                  >
                    Connect with OAuth
                  </button>
                )}
                {(c.secret_fields.length > 0 || c.auth === "oauth") && (
                  <button
                    onClick={() => {
                      setOpen(open === c.kind ? null : c.kind);
                      setForm({ name: "", secrets: {}, settings: "" });
                    }}
                    className="rounded border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800"
                  >
                    {open === c.kind ? "Cancel" : "Connect with token"}
                  </button>
                )}
                {c.auth === "none" && (
                  <span className="text-xs text-neutral-500">fixture / push only</span>
                )}
              </div>

              {open === c.kind && (
                <form onSubmit={(e) => tokenConnect(c, e)} className="mt-3 space-y-2 border-t border-neutral-800 pt-3">
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="display name"
                    className="w-full rounded border border-neutral-700 bg-neutral-900 p-1.5 text-sm"
                  />
                  {(c.secret_fields.length ? c.secret_fields : ["access_token"]).map((sf) => (
                    <input
                      key={sf}
                      type="password"
                      value={form.secrets[sf] || ""}
                      onChange={(e) => setForm({ ...form, secrets: { ...form.secrets, [sf]: e.target.value } })}
                      placeholder={sf}
                      className="w-full rounded border border-neutral-700 bg-neutral-900 p-1.5 text-sm"
                    />
                  ))}
                  {CONFIG_HINT[c.kind] && (
                    <input
                      value={form.settings}
                      onChange={(e) => setForm({ ...form, settings: e.target.value })}
                      placeholder={CONFIG_HINT[c.kind]}
                      className="w-full rounded border border-neutral-700 bg-neutral-900 p-1.5 text-sm"
                    />
                  )}
                  <button
                    disabled={busy}
                    className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {busy ? "Connecting…" : "Connect"}
                  </button>
                </form>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Connected sources */}
      <section>
        <h2 className="mb-2 text-lg font-medium">Connected sources ({sources.length})</h2>
        <div className="space-y-2">
          {sources.map((s) => (
            <div key={s.id} className="rounded-lg border border-neutral-800 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{s.name}</span>{" "}
                  <span className="text-xs text-neutral-500">
                    {s.kind} · {s.artifact_count ?? 0} artifacts · last sync {s.last_synced_at?.slice(0, 19).replace("T", " ") || "—"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => sync(s.id)} className="rounded bg-neutral-700 px-2 py-1 text-xs hover:bg-emerald-700">
                    sync
                  </button>
                  <button onClick={() => configure(s)} className="rounded bg-neutral-700 px-2 py-1 text-xs hover:bg-neutral-600">
                    configure
                  </button>
                  <button onClick={() => remove(s.id)} className="rounded bg-neutral-700 px-2 py-1 text-xs hover:bg-red-700">
                    remove
                  </button>
                </div>
              </div>
              {msg[s.id] && <div className="mt-1 text-xs text-emerald-400">{msg[s.id]}</div>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
