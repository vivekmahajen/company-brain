"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Template = {
  topic: string;
  slug: string;
  title: string;
  description: string;
  intents: string[];
  keywords: string[];
  custom: boolean;
};
type Draft = {
  topic: string;
  title: string;
  description: string;
  intents: string[];
  keywords: string[];
  inputs?: string[];
  tools?: unknown[];
  drafted_by?: string;
};

export default function CapabilitiesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [desc, setDesc] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setTemplates(await api.templates());
      setErr("");
    } catch {
      setErr("API unreachable.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function makeDraft() {
    if (!desc.trim()) return;
    setBusy(true);
    setErr("");
    try {
      setDraft(await api.draftTemplate(desc));
    } catch {
      setErr("Draft failed.");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!draft) return;
    setBusy(true);
    setErr("");
    try {
      const body = {
        topic: draft.topic,
        title: draft.title,
        description: draft.description,
        inputs: draft.inputs || [],
        tools: draft.tools || [],
        intents: draft.intents,
        keywords: draft.keywords,
      };
      const res = await api.createTemplate(body);
      if (res.error || res.detail) setErr(res.error || res.detail);
      else {
        setDraft(null);
        setDesc("");
        await load();
      }
    } catch (e: any) {
      setErr(String(e?.message || "Create failed."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(topic: string) {
    if (!confirm(`Delete the "${topic}" capability?`)) return;
    await api.deleteTemplate(topic);
    await load();
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Capabilities</h1>
        <p className="mt-1 text-sm text-neutral-400">
          The skill <em>shapes</em> your brain can compile. Built-ins ship with the product; describe
          your own below and the brain drafts a new one — then fills it from your knowledge.
        </p>
      </div>

      {err && <div className="rounded bg-red-900/30 p-2 text-sm text-red-200">{err}</div>}

      {/* Author a new capability */}
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-medium">Describe a new capability</h2>
        <textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="e.g. Approve a vendor invoice over a threshold and notify finance"
          rows={2}
          className="mt-2 w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
        />
        <button
          onClick={makeDraft}
          disabled={busy || !desc.trim()}
          className="mt-2 rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? "Drafting…" : "Draft it"}
        </button>

        {draft && (
          <div className="mt-4 space-y-2 border-t border-neutral-800 pt-4">
            <div className="text-xs text-neutral-500">
              Draft ({draft.drafted_by}) — edit, then create:
            </div>
            <Field label="Topic (id)" value={draft.topic} onChange={(v) => setDraft({ ...draft, topic: v })} />
            <Field label="Title" value={draft.title} onChange={(v) => setDraft({ ...draft, title: v })} />
            <Field label="Description" value={draft.description} onChange={(v) => setDraft({ ...draft, description: v })} />
            <Field
              label="Keywords (comma-separated)"
              value={draft.keywords.join(", ")}
              onChange={(v) => setDraft({ ...draft, keywords: v.split(",").map((x) => x.trim()).filter(Boolean) })}
            />
            <Field
              label="Intents (comma-separated)"
              value={draft.intents.join(", ")}
              onChange={(v) => setDraft({ ...draft, intents: v.split(",").map((x) => x.trim()).filter(Boolean) })}
            />
            <button
              onClick={create}
              disabled={busy}
              className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create capability"}
            </button>
          </div>
        )}
      </section>

      {/* Existing capabilities */}
      <section>
        <h2 className="mb-2 text-lg font-medium">Your capabilities ({templates.length})</h2>
        <div className="space-y-2">
          {templates.map((t) => (
            <div key={t.topic} className="flex items-start justify-between rounded-lg border border-neutral-800 p-3">
              <div>
                <span className="font-medium">{t.title}</span>{" "}
                <span className={`ml-1 rounded px-1.5 py-0.5 text-xs ${t.custom ? "bg-emerald-900/40 text-emerald-300" : "bg-neutral-800 text-neutral-400"}`}>
                  {t.custom ? "custom" : "built-in"}
                </span>
                <div className="text-xs text-neutral-500">
                  <code>{t.slug}</code> · keywords: {t.keywords.slice(0, 6).join(", ")}
                </div>
              </div>
              {t.custom && (
                <button onClick={() => remove(t.topic)} className="rounded bg-neutral-700 px-2 py-1 text-xs hover:bg-red-700">
                  delete
                </button>
              )}
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          A new capability compiles into a skill once you add knowledge for it (Add knowledge / connected sources).
        </p>
      </section>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-400">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 p-2 text-sm"
      />
    </label>
  );
}
