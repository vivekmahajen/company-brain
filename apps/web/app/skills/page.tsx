import Link from "next/link";
import { api } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function SkillsPage() {
  let skills: any[] = [];
  try {
    skills = await api.skills();
  } catch {
    return <div className="text-amber-300">API unreachable.</div>;
  }
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">Skills</h1>
      {skills.map((s) => (
        <Link
          key={s.slug}
          href={`/skills/${s.slug}`}
          className="block rounded-lg border border-neutral-800 p-4 hover:border-neutral-600"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium">{s.title}</span>
            <span className="text-xs text-neutral-400">v{s.version} · {s.status}</span>
          </div>
          <div className="text-sm text-neutral-500">{s.slug}</div>
        </Link>
      ))}
    </div>
  );
}
