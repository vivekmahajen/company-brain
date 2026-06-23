# Deploying Company Brain

Two services: the **API** (FastAPI) on Railway, the **console** (Next.js) on
Vercel. Deploy the API first so the console has something to call.

---

## 1. API → Railway

The repo ships a root `Dockerfile` and `railway.json` (Dockerfile builder), so
Railway builds the API directly.

### Steps

1. **New Project → Deploy from GitHub repo** → pick `company-brain`.
   - Set the deploy branch to the branch holding this code
     (`claude/happy-sagan-bbraug`) or merge it to `main` first.
   - Railway detects `railway.json` and builds the `Dockerfile`. No root
     directory change needed (the image build context is the repo root).

2. **Add a database.** Two options:
   - **Recommended:** add the **pgvector** Postgres template (gives native
     vector columns + indexing), then set `USE_PGVECTOR=true`.
   - **Any Postgres** works too: leave `USE_PGVECTOR` unset/`false`. Embeddings
     are stored as JSON and similarity is computed in Python — identical Phase-1
     results, no extension required. (You can flip to pgvector later.)

3. **Environment variables** on the API service:

   | Var | Value | Notes |
   |---|---|---|
   | `DATABASE_URL` | `postgresql+psycopg://...` | Use Railway's `DATABASE_URL`; ensure the `+psycopg` driver prefix. |
   | `LLM_PROVIDER` | `anthropic` | or leave `fixture` for the deterministic offline demo |
   | `ANTHROPIC_API_KEY` | `sk-ant-...` | required only when `LLM_PROVIDER=anthropic` |
   | `USE_PGVECTOR` | `true` | only if you used the pgvector template |
   | `SEED_ON_STARTUP` | `true` | seeds the refund demo on first boot so the console isn't empty |

   > If `DATABASE_URL` comes as `postgresql://...` (no driver), change it to
   > `postgresql+psycopg://...` so SQLAlchemy uses psycopg 3.

4. **Deploy.** Health check is `GET /health`. On first boot with
   `SEED_ON_STARTUP=true`, the API runs the full pipeline and compiles
   `handle-refund`.

5. **Verify:**
   ```bash
   curl https://<your-api>.up.railway.app/health
   curl -X POST https://<your-api>.up.railway.app/api/resolve \
        -H 'content-type: application/json' -d '{"task":"refund my money"}'
   ```

   If you didn't enable `SEED_ON_STARTUP`, seed once:
   ```bash
   curl -X POST https://<your-api>.up.railway.app/api/pipeline/run
   ```

### Troubleshooting

- **`Invalid value for '--port': '$PORT' is not a valid integer`** — a start
  command of `uvicorn … --port $PORT` was run without shell expansion. Don't set
  a Custom Start Command in Railway and don't put one in `railway.json`; the
  Dockerfile's `CMD` (`sh -c "… --port ${PORT:-8000}"`) expands `$PORT` itself
  and defaults to 8000. If you previously set a Custom Start Command in the
  dashboard, clear it.

---

## 2. Console → Vercel

The console lives in `apps/web`.

1. **Vercel project → Settings → General → Root Directory = `apps/web`.**
   (This is the fix for a platform 404 at `/` — without it Vercel builds from
   the repo root and finds no app.)
2. **Settings → Git → Production Branch** = the branch with this code.
3. **Settings → Environment Variables:**
   - `NEXT_PUBLIC_API_URL` = `https://<your-api>.up.railway.app/api`
4. **Redeploy.** Open `/` → Dashboard → "Rebuild the Brain" / "Test the Brain".

---

## 3. CORS

The API allows all origins by default (`apps/api/main.py`). To lock it to your
Vercel domain, set `allow_origins` to `["https://<your-app>.vercel.app"]`.

## Going live with real refunds (ACTIONS_MODE=live)

**This moves real money.** Sandbox is the default and is safe; live is opt-in and
fails closed. To enable real Stripe refunds:

1. **Provider key** — set `STRIPE_API_KEY` (use a *restricted* key scoped to
   refunds only) on the API service. Without it, every live refund refuses to run.
2. **Order → charge mapping** — a real refund needs the Stripe `charge` /
   `payment_intent` id, not just an order id. Populate
   `order_record.provider_charge_id` (in production this comes from your orders
   connector). If it's missing for an order, the live refund fails closed.
3. **Flip the flag** — set `ACTIONS_MODE=live` on the API service.

Safety properties that still hold in live mode:

- The refund only runs **after** the approval gate clears (a `>$500` refund is
  still held for a human approver).
- The `idempotency_key` is passed to Stripe's native idempotency, so a retry
  past our own check still cannot double-refund.
- Any adapter/provider error is caught and returned as a typed `error` outcome,
  logged in `execution_log` — it never crashes the server or silently succeeds.
- Tools without a dedicated live adapter (apply_discount, page_oncall, …) refuse
  to run in live mode rather than guessing.

Recommended rollout: keep `ACTIONS_MODE=sandbox` until you've (a) confirmed the
approval workflow in the console, (b) loaded real `provider_charge_id`s, and (c)
set a refund-scoped restricted Stripe key. Then flip one service to `live`.

## 4. MCP (agents)

The MCP server (`python -m apps.api.mcp.server`, stdio) is for agent clients and
is typically run alongside an agent rather than hosted. See `docs/AGENTS.md`.
