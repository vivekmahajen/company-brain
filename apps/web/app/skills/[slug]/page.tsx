import { api } from "../../lib/api";
import ReviewButtons from "./review-buttons";

export const dynamic = "force-dynamic";

export default async function SkillDetail({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let skill: any = null;
  let versions: any[] = [];
  try {
    skill = await api.skill(slug);
    versions = await api.skillVersions(slug);
  } catch {
    return <div className="text-amber-300">API unreachable.</div>;
  }
  if (!skill) return <div>Not found.</div>;

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{skill.title}</h1>
          <div className="text-sm text-neutral-400">
            {skill.slug} · v{skill.version} · <span className="text-amber-300">{skill.status}</span>
          </div>
        </div>
        <ReviewButtons slug={skill.slug} />
      </div>

      <section>
        <h2 className="mb-2 text-lg font-medium">Tool bindings</h2>
        <div className="space-y-2">
          {skill.tools.map((t: any) => (
            <div key={t.name} className="rounded border border-neutral-800 p-3 text-sm">
              <span className="font-mono">{t.name}</span>
              {t.side_effecting && <span className="ml-2 rounded bg-red-900/50 px-2 text-xs text-red-300">side-effecting</span>}
              {t.approval_required && (
                <span className="ml-2 rounded bg-amber-900/50 px-2 text-xs text-amber-300">
                  approval when {t.approval_expression}
                </span>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Provenance</h2>
        <ul className="space-y-1 text-xs text-neutral-400">
          {skill.provenance.map((p: any, i: number) => (
            <li key={i}>
              <span className="text-neutral-300">{p.source}</span> — “{p.span}” <span className="text-neutral-600">[{p.ku}]</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Compiled SKILL.md</h2>
        <pre className="max-h-96 overflow-auto rounded bg-neutral-900 p-4 text-xs">{skill.body_md}</pre>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-medium">Version history</h2>
        <div className="text-sm text-neutral-400">
          {versions.map((v) => (
            <span key={v.version} className="mr-3">
              v{v.version} ({v.status})
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
