# Company Brain — SaaS Roadmap

**From a single deployment to every company in the world.**

> North star: any company signs up, connects their tools, and within minutes has
> governed, executable skills their agents can safely act on — with a published quality
> number per tenant. Zero code written per customer.

**The core bet that makes this scalable:** *capability templates are shared; knowledge is
per-tenant.* We ship the shapes (refund, pricing, incident, …); each company's own data
fills them. That is why one codebase can serve millions.

---

## Phase 0 — What already exists (do not rebuild)

- Fully `org_id`-scoped data model + queries; org-isolated tokens; org-scoped `VisibilityFilter`.
- One governed executor choke point (approvals, idempotency, guardrails) — the safety moat.
- Runtime knowledge/policy extension (no redeploy).
- A deterministic governance benchmark **+ a real measured extraction F1 (74.8% ± 2.7, κ=1.0)**.
- Postgres+pgvector seam, fixture/live LLM seam, fixture/live connector seam.

This is the **design-partner-ready** state. Everything below turns it into **world-ready**.

---

## Phase 1 — True multi-tenancy *(Foundation — do first)*

**Goal:** two companies on one deployment, provably isolated.

- Replace `_org()` in `routers/brain.py` with per-request tenant resolution (API key /
  principal / subdomain → `org_id`). The plumbing beneath already respects `org_id`.
- `POST /api/orgs` to create a tenant + provision its seed (reuse `run_full_pipeline(org_id)`).
- Tenant-context middleware; reject any request with no resolved org (fail closed).
- **Isolation test suite:** org A can never read org B's skills/knowledge/approvals — a hard
  CI gate, like GAR/PER.

**Unblocks:** everything else. **Effort:** S–M. **Proof:** live demo — two orgs, one URL,
zero cross-visibility, enforced in CI.

---

## Phase 2 — Self-serve onboarding + real connector auth *(the biggest lift)*

**Goal:** a company connects *their* Slack/Notion/GitHub with *their* credentials, unattended.

- Per-connector **OAuth flows** (Slack/Google/GitHub/Atlassian) → tokens in an **encrypted
  secrets vault**, not `config_jsonb` plaintext.
- Promote connectors from fixture-first to live-mode: token refresh, pagination, incremental
  sync, per-tenant ACL mirroring (`pull_acls()` exists).
- Onboarding wizard: connect sources → first sync → first skills compiled → review queue.
- Background **sync/job system** (Celery/Arq/Temporal) — ingestion can't be request-synchronous.

**Unblocks:** real customers without touching their config. **Effort:** L (the quarter-long one).
**Proof:** a stranger signs up, connects real Slack, sees real skills compile — unattended.

---

## Phase 3 — Customer-authored capabilities *(no-code skill authoring)*

**Goal:** customers add new capability *shapes*, not just knowledge.

- Template-authoring UI writing to a **DB-backed template store** (move `SKILL_TEMPLATES`
  from code → per-org DB rows).
- LLM-assisted template synthesis: "Describe the workflow" → draft template → human confirms.
- A **tool/action SDK + registry** so customers bind their own tools (webhooks first; the
  executor + `actions/registry.py` already abstract this).

**Unblocks:** breadth across verticals without eng. **Effort:** L. **Proof:** a customer
creates a brand-new skill (e.g., "approve vendor invoice") entirely in-product.

---

## Phase 4 — Scale infrastructure

**Goal:** thousands of tenants, millions of artifacts.

- SQLite → **Postgres + pgvector** (seam exists).
- Tenant isolation strategy: start row-level `org_id` + RLS; escalate to schema-per-tenant
  for large accounts.
- Connection pooling, caching, async embeddings, per-tenant sync scheduling + backpressure,
  object storage for raw artifacts.

**Effort:** M–L. **Proof:** load test — 1k tenants, p95 resolve < 200ms, isolated.

---

## Phase 5 — Security & compliance *(gates enterprise revenue)*

**Goal:** pass a security review; sellable to regulated buyers.

- SSO/SAML/OIDC + SCIM; encryption at rest (vault/KMS) + in transit.
- Full **audit log** (executions/access already logged — extend + export).
- Data residency + deletion (GDPR/DPA); secrets rotation; pen-test.
- **SOC 2 Type II**, then ISO 27001.

**Effort:** L + ongoing. SOC 2 is months of *calendar* time — start the clock early.
**Proof:** SOC 2 Type II report + a clean enterprise security questionnaire.

---

## Phase 6 — Billing, packaging & plans

**Goal:** money in, self-serve.

- Stripe billing; **usage metering** (real `cost.usd`/tokens already tracked — meter per tenant).
- Plan tiers (Free/Team/Business/Enterprise) gating sources, skills, seats, run volume.
- Quotas + overage; in-app upgrade.

**Effort:** M. **Proof:** a customer self-upgrades and is billed correctly on usage.

---

## Phase 7 — Reliability & observability

**Goal:** production SLAs.

- Per-tenant metrics/tracing/error tracking; health checks.
- Rate limiting + abuse protection; graceful LLM-provider failover (`get_llm()` seam helps).
- Incident runbooks; status page; backups + DR.

**Effort:** M. **Proof:** a 99.9% uptime month + a clean game-day failover.

---

## Phase 8 — Go-to-market packaging *(distribution moat)*

**Goal:** every company finds a fast path to value.

- **Vertical capability packs** (SaaS support, e-commerce ops, fintech, dev/on-call).
- A **template marketplace** (community/partner skills).
- Guided trial with sample data → connect real data; self-serve docs.
- **Per-tenant published quality scorecard** — extend the CBE harness so each customer sees
  *their* GAR/PER/extraction number. "We measure our own quality, per tenant" is differentiated.

**Effort:** M, continuous. **Proof:** trial → connected → first governed execution, no human
touch from us.

---

## Cross-cutting: keep the quality loop per-tenant

The eval harness is a strategic asset competitors lack. Run the deterministic governance gates
(GAR/PER) and the measured extraction number **per tenant** on their data, surfaced in their
console. "Governed, and we publish our accuracy on *your* data" is a closing argument.

---

## Suggested sequencing (dependency-true)

- **Next 30 days:** Phase 1 (multi-tenancy + isolation CI). Non-negotiable foundation.
- **30–90 days:** Phase 2 (onboarding + OAuth + jobs) ∥ **start** SOC 2 (Phase 5, long pole).
  Stand up Postgres (Phase 4) early — Phase 2 volume forces it.
- **90–180 days:** Phase 3 (customer authoring) + Phase 6 (billing) → self-serve revenue.
- **180+ days:** Phases 7–8 harden + scale distribution; finish SOC 2 Type II.

---

## The honest risks (name them now)

1. **Phase 2 is the real moat and the real cost** — per-provider OAuth + secure credential
   handling is where most "connect your tools" startups burn a year.
2. **Compliance is calendar, not code** — SOC 2 Type II gates the biggest deals and takes
   months of observation. Start in month 2, not month 12.
3. **Per-tenant model cost** — at ~$10/eval run and live extraction, unit economics matter.
   Meter from day one; use cheaper models for the classify/extract gate.
4. **Support burden of self-serve** — "every company" demands great errors, retries, and
   per-tenant observability, or support drowns.
5. **Don't let breadth outrun the safety story** — the governed-executor + published-eval
   differentiation is the reason to buy. Keep it true per tenant, or it becomes just another
   RAG bot.
