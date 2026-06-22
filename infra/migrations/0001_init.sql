-- PostgreSQL 16 + pgvector schema (production system of record).
-- Mirrors apps/api/models/tables.py. For local/dev the app auto-creates tables
-- on SQLite; in production run this (or generate Alembic migrations from the
-- models) against Postgres.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  kind text NOT NULL,
  name text NOT NULL,
  config_jsonb jsonb DEFAULT '{}',
  status text DEFAULT 'connected',
  last_synced_at timestamptz
);

CREATE TABLE IF NOT EXISTS artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  source_id uuid NOT NULL REFERENCES source(id),
  external_id text NOT NULL,
  kind text NOT NULL,
  raw_jsonb jsonb DEFAULT '{}',
  content_text text DEFAULT '',
  content_hash text NOT NULL,
  author text,
  occurred_at timestamptz,
  ingested_at timestamptz DEFAULT now(),
  UNIQUE (org_id, source_id, external_id)
);

CREATE TABLE IF NOT EXISTS knowledge_unit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  type text NOT NULL,
  statement text NOT NULL,
  payload_jsonb jsonb DEFAULT '{}',
  embedding vector(256),
  confidence numeric DEFAULT 0.5,
  status text DEFAULT 'draft',
  valid_from timestamptz DEFAULT now(),
  valid_to timestamptz,
  superseded_by uuid,
  topic text
);

CREATE TABLE IF NOT EXISTS ku_provenance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  knowledge_unit_id uuid NOT NULL REFERENCES knowledge_unit(id),
  artifact_id uuid NOT NULL REFERENCES artifact(id),
  quote_span text DEFAULT '',
  extracted_by text DEFAULT 'extractor',
  extracted_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  type text NOT NULL,
  canonical_name text NOT NULL,
  aliases_jsonb jsonb DEFAULT '[]',
  attributes_jsonb jsonb DEFAULT '{}',
  embedding vector(256)
);

CREATE TABLE IF NOT EXISTS edge (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  src_entity_id uuid NOT NULL REFERENCES entity(id),
  dst_entity_id uuid NOT NULL REFERENCES entity(id),
  relation text NOT NULL,
  properties_jsonb jsonb DEFAULT '{}',
  confidence numeric DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS skill (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  slug text NOT NULL,
  title text NOT NULL,
  summary text DEFAULT '',
  body_md text DEFAULT '',
  frontmatter_jsonb jsonb DEFAULT '{}',
  version int DEFAULT 1,
  status text DEFAULT 'draft',
  compiled_at timestamptz DEFAULT now(),
  source_ku_ids_jsonb jsonb DEFAULT '[]',
  content_signature text DEFAULT '',
  UNIQUE (org_id, slug, version)
);

CREATE TABLE IF NOT EXISTS skill_binding (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id uuid NOT NULL REFERENCES skill(id),
  tool_name text NOT NULL,
  tool_schema_jsonb jsonb DEFAULT '{}',
  side_effecting boolean DEFAULT false,
  approval_required boolean DEFAULT false,
  approval_expression text
);

CREATE TABLE IF NOT EXISTS resolver_entry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  skill_id uuid NOT NULL REFERENCES skill(id),
  slug text NOT NULL,
  intents_jsonb jsonb DEFAULT '[]',
  keywords_jsonb jsonb DEFAULT '[]',
  priority int DEFAULT 100,
  embedding vector(256)
);

CREATE TABLE IF NOT EXISTS policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  name text NOT NULL,
  rule_jsonb jsonb DEFAULT '{}',
  enforcement text DEFAULT 'block'
);

CREATE TABLE IF NOT EXISTS review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  reviewer text DEFAULT '',
  decision text DEFAULT '',
  note text DEFAULT '',
  decided_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staleness_signal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  reason text DEFAULT '',
  detected_at timestamptz DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS execution_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  skill_id uuid,
  agent_id text,
  input_jsonb jsonb DEFAULT '{}',
  output_jsonb jsonb DEFAULT '{}',
  outcome text DEFAULT '',
  expected_jsonb jsonb DEFAULT '{}',
  drift_flag boolean DEFAULT false,
  occurred_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ku_org ON knowledge_unit(org_id);
CREATE INDEX IF NOT EXISTS ix_artifact_hash ON artifact(content_hash);
CREATE INDEX IF NOT EXISTS ix_skill_slug ON skill(org_id, slug);
