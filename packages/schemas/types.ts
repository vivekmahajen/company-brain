// Shared contract types between the API and the web console.
// Phase 2: auto-generate from Pydantic models (datamodel-code-generator).

export type KUType =
  | "entity"
  | "relationship"
  | "fact"
  | "policy_rule"
  | "procedure_step"
  | "metric_definition"
  | "glossary_term";

export type SkillStatus = "draft" | "needs_review" | "approved" | "deprecated";

export interface KnowledgeUnit {
  id: string;
  type: KUType;
  statement: string;
  payload: Record<string, unknown>;
  confidence: number;
  status: "draft" | "needs_review" | "approved" | "superseded";
  topic?: string | null;
  valid_to?: string | null;
  superseded_by?: string | null;
  provenance: { artifact_id: string; span: string }[];
}

export interface ToolBinding {
  name: string;
  schema: Record<string, unknown>;
  side_effecting: boolean;
  approval_required: boolean;
  approval_expression?: string | null;
}

export interface Skill {
  slug: string;
  title: string;
  version: number;
  status: SkillStatus;
  frontmatter: Record<string, unknown>;
  body_md: string;
  provenance: { ku: string; source: string; span: string }[];
  tools: ToolBinding[];
}

export interface ResolverRoute {
  slug: string;
  title: string;
  score: number;
  confidence: number;
  reason: string;
}

export interface ExecutionResult {
  outcome: "executed" | "approval_required" | "error";
  tool?: string;
  reason?: string;
  policy_rule?: string | null;
  result?: Record<string, unknown>;
}
