-- Permissions-aware access (§3): groups, memberships, ACLs, visibility cache,
-- audit log. The app also creates these tables (create_all) and adds the
-- principal.external_subject column additively on startup.

ALTER TABLE principal ADD COLUMN IF NOT EXISTS external_subject varchar;

CREATE TABLE IF NOT EXISTS group_ (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  name text NOT NULL,
  kind text DEFAULT 'mirrored'
);

CREATE TABLE IF NOT EXISTS membership (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  principal_id uuid NOT NULL,
  group_id uuid NOT NULL,
  source_of_truth text DEFAULT 'brain'
);
CREATE INDEX IF NOT EXISTS ix_membership_principal ON membership(org_id, principal_id);

CREATE TABLE IF NOT EXISTS role_grant (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  principal_id uuid NOT NULL,
  role text NOT NULL
);

CREATE TABLE IF NOT EXISTS source_acl (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  source_id uuid NOT NULL,
  subject_id uuid NOT NULL,
  subject_kind text DEFAULT 'group',
  access text DEFAULT 'allow',
  origin text DEFAULT 'mirror'
);
CREATE INDEX IF NOT EXISTS ix_source_acl ON source_acl(org_id, source_id);

CREATE TABLE IF NOT EXISTS skill_acl (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  skill_id uuid NOT NULL,
  subject_id uuid NOT NULL,
  subject_kind text DEFAULT 'group',
  access text DEFAULT 'allow'
);

CREATE TABLE IF NOT EXISTS visibility_label (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  target_type text NOT NULL,
  target_id uuid NOT NULL,
  requirements_jsonb jsonb DEFAULT '[]',
  lineage_hash text DEFAULT '',
  computed_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS access_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  principal_id uuid,
  action text DEFAULT '',
  target_type text DEFAULT '',
  target_id text DEFAULT '',
  decision text DEFAULT '',
  reason text DEFAULT '',
  occurred_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_access_log ON access_log(org_id, occurred_at);
