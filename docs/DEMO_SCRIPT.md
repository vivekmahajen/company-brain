# Company Brain — 5-minute demo script

A tight click-path through the product for a prospect. Console = your Vercel URL,
API = `https://company-brain-production-e41b.up.railway.app`.

**The one-liner:** *"Company Brain turns your scattered company knowledge into governed,
executable skills your AI agents can safely act on — and we publish a quality scorecard
on **your** data, not a public benchmark."*

---

## Before the call (2 min, once)
- Confirm health: open `…/api/health/db` (→ `postgres`) and `…/api/health/llm` (→ `anthropic`).
- Reseed a clean demo brain: `POST …/api/admin/reseed-serving`.
- Have a GitHub issue ready in a repo with a policy line (e.g. "refunds above $500 require manager sign-off").

---

## The flow (≈5 min)

**1. The problem (15s).** "Your policies live in Slack, Notion, GitHub, tickets. Agents
can't act on them safely. We fix that."

**2. Connect a source — live (60s).** Console → **Connect sources** → **Connect with OAuth**
on GitHub → approve. "One OAuth app, their workspace. Credentials are encrypted in a vault,
never stored in plaintext." → click **sync**.
> Talking point: every other source (Slack/Notion/Gmail/Linear/Zendesk) works the same way.

**3. Real knowledge, real provenance (60s).** Console → **Knowledge**. "Their GitHub issue
became a typed policy rule — `refunds above $500 require manager sign-off` — and synthesis
**merged it with the other sources and resolved a conflict** ($500 beat the old $300). Every
rule cites its source line." Show the **Skills** page → the compiled `handle-refund` skill.

**4. Governed execution — the moat (45s).** Console → resolve a task ("customer wants their
money back") → it routes to the refund skill with calibrated confidence. "A $200 refund
executes; a $620 one returns **approval_required** — gated on server-resolved facts, not the
agent's word. That's why you can let an agent touch money."

**5. They author their own (45s).** Console → **Capabilities** → type *"Approve a vendor
invoice over a threshold and notify finance"* → **Draft it** (Claude drafts it) → **Create**.
Or **Install pack** (SaaS Support / E-commerce / IT). "No code. Their workflow, their skill."

**6. The closing scorecard (30s).** Console → **Brain scorecard**. "Most memory products
quote recall on a public benchmark. Here's a governance + completeness score on **your**
brain — readiness, provenance coverage, guardrails, freshness." (Demo org: **100/100**.)

**7. It's a business (20s).** Console → **Billing** (plans, metered usage, upgrade) and
**Security** (audit log, one-click data export, GDPR erasure). "Metered, plan-gated,
auditable, exportable — enterprise-ready."

---

## The closing argument
"It's not enterprise search or a RAG chatbot. It's a **governed, executable knowledge layer**:
their real data → typed knowledge with provenance → compiled skills → executed behind approval
gates → measured per-tenant. Multi-tenant, OAuth-connected, billed, and audited — today, on
production."

## Honest credibility line (use it — it lands)
"Our published extraction number is **F1 74.8% ± 2.7**, judge-validated at κ=1.0 — *below* 100%
on purpose. 100% recall (we miss no rule), lower precision (we over-extract, a human prunes).
We publish the real number with its confidence interval, not a marketing one."

## If something's offline
- Live OAuth flaky? Use **Connect with token** or the pre-seeded fixtures (the brain is already
  populated after reseed).
- Don't run `reseed`/`pipeline` repeatedly on a paid key mid-demo — each costs money.
