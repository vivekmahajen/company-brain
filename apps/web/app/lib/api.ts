const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  runPipeline: () => req("/pipeline/run", { method: "POST" }),
  sources: () => req("/sources"),
  artifacts: () => req("/artifacts"),
  knowledge: () => req("/knowledge"),
  skills: () => req("/skills"),
  skill: (slug: string) => req(`/skills/${slug}`),
  skillVersions: (slug: string) => req(`/skills/${slug}/versions`),
  reviewSkill: (slug: string, decision: string) =>
    req(`/skills/${slug}/review`, { method: "POST", body: JSON.stringify({ decision }) }),
  resolve: (task: string) =>
    req("/resolve", { method: "POST", body: JSON.stringify({ task }) }),
  execute: (slug: string, tool: string, inputs: Record<string, unknown>) =>
    req("/execute", { method: "POST", body: JSON.stringify({ slug, tool, inputs }) }),
  staleness: () => req("/staleness"),
  drift: () => req("/drift"),

  // Governance policies (M8)
  policies: () => req("/policies"),
  createPolicy: (body: {
    name: string;
    tool: string;
    when: string;
    require?: string;
    enforcement?: string;
  }) => req("/policies", { method: "POST", body: JSON.stringify(body) }),
  deletePolicy: (id: string) => req(`/policies/${id}`, { method: "DELETE" }),

  // Add knowledge (paste text -> extract -> recompile)
  addKnowledge: (text: string, source_name = "Manual entry") =>
    req("/knowledge/add", { method: "POST", body: JSON.stringify({ text, source_name }) }),

  // MCP serving: approvals (held side effects)
  approvals: () => req("/approvals"),
  decideApproval: (id: string, decision: "approve" | "reject") =>
    req(`/approvals/${id}/decide`, { method: "POST", body: JSON.stringify({ decision }) }),

  // Evals (CBE scorecard)
  evalsLatest: () => req("/evals/latest"),
  evalsRuns: () => req("/evals/runs"),
  evalsExtractionLive: () => req("/evals/extraction-live"),
  evalsFailures: (runId: string) => req(`/evals/runs/${runId}/failures`),

  // Access control (permissions)
  accessPrincipals: () => req("/access/principals"),
  viewAs: (token: string, task?: string) =>
    req("/access/view-as", { method: "POST", body: JSON.stringify({ token, task }) }),
  accessSources: () => req("/access/sources"),
  accessAudit: () => req("/access/audit"),
};

export type Route = { slug: string; title: string; score: number; confidence: number; reason: string };
