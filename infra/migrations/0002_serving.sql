-- MCP serving layer (§4): principals, approval requests, order facts,
-- execution_log enrichment. The app also applies these additively on startup
-- (create_all for new tables + ALTER for new columns), so this file is for
-- explicit/audited Postgres provisioning.

CREATE TABLE IF NOT EXISTS principal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  kind text DEFAULT 'agent',
  display_name text DEFAULT '',
  role text DEFAULT 'agent',
  scopes_jsonb jsonb DEFAULT '[]',
  token_hash text NOT NULL,
  status text DEFAULT 'active',
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_principal_token ON principal(token_hash);

CREATE TABLE IF NOT EXISTS approval_request (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  skill_id uuid,
  binding_id uuid,
  tool_name text NOT NULL,
  requested_by_principal uuid NOT NULL,
  input_jsonb jsonb DEFAULT '{}',
  resolved_facts_jsonb jsonb DEFAULT '{}',
  gate_reason text DEFAULT '',
  status text DEFAULT 'pending',
  idempotency_key text NOT NULL,
  decided_by_principal uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  result_jsonb jsonb DEFAULT '{}',
  expires_at timestamptz,
  created_at timestamptz DEFAULT now(),
  UNIQUE (org_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_approval_status ON approval_request(org_id, status);

CREATE TABLE IF NOT EXISTS order_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  order_id text NOT NULL,
  original_charge double precision DEFAULT 0,
  age_days int DEFAULT 0,
  status text DEFAULT 'paid'
);
CREATE INDEX IF NOT EXISTS ix_order_lookup ON order_record(org_id, order_id);

ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS principal_id varchar;
ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS idempotency_key varchar;
ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS gate_decision varchar;
ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS approval_request_id varchar;
ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS transport varchar;
ALTER TABLE execution_log ADD COLUMN IF NOT EXISTS trace_id varchar;
CREATE INDEX IF NOT EXISTS ix_exec_idem ON execution_log(idempotency_key);
