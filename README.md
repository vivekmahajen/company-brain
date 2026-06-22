# Company Brain

A living, executable knowledge layer that turns a company's fragmented artifacts
into **skills AI agents can act on** — implementing the "Company Brain" primitive
from Y Combinator's S2026 Request for Startups.

This is **not** enterprise search, a RAG chatbot, or a vector index you query for
snippets. It is:

- A governed, typed model of how the company actually operates (entities,
  relationships, policies, procedures, metric definitions).
- A **skills compiler** that emits executable `SKILL.md` files an agent acts on.
- A self-maintaining system that detects staleness and recompiles.
- A **RESOLVER** routing layer that sends a task to the correct skill.
- A closed loop that compares what is happening to what should happen.

## Status — Phase 1 (end-to-end thin slice)

The full refund loop works end-to-end:

```
Slack + Notion connectors → extraction (typed KUs + provenance)
  → dedup / synthesis (canonical, bitemporal facts)
  → compile handle-refund.skill.md (thresholds + tool bindings + guardrails)
  → RESOLVER routing → MCP / REST serve with approval gating
```

### Key design decision: it runs offline

The LLM and embedding layers sit behind interfaces (`llm/base.py`). A
**deterministic fixture provider** lets the entire pipeline + eval harness run
with **no network and no API key**, which makes the loop reproducible and
CI-testable. Swapping to the real Anthropic client (`claude-opus-4-8` for
extraction/compilation, `claude-haiku-4-5` for cheap classification) is one env
var. See `apps/api/llm/`.

The DB defaults to SQLite so the demo runs anywhere; it is written for
PostgreSQL 16 + pgvector with the seam isolated in `models/db.py` and
`graph/similarity.py`.

## Quickstart

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the whole Phase-1 loop against the bundled fixtures and print the result:
python -m apps.api.demo        # (run from repo root) or: make demo

# Run the eval harness (extraction precision/recall + routing accuracy):
pytest -q                      # or: make test
```

To use real Anthropic:

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

## Deploy

API on Railway (Dockerfile + `railway.json` included), console on Vercel
(`apps/web`). Full step-by-step: **[docs/DEPLOY.md](docs/DEPLOY.md)**.
A platform 404 at the Vercel `/` means the project's **Root Directory** isn't set
to `apps/web`.

## Layout

See the build prompt; the repo follows §8 of it. Highlights:

- `apps/api/connectors` — M1 ingestion (Slack, Notion real; others stubbed)
- `apps/api/extraction` — M2 typed KU extraction with provenance
- `apps/api/graph` — M3 entity resolution, dedup, synthesis (bitemporal)
- `apps/api/compiler` — M4 SKILL.md compiler
- `apps/api/resolver` — M5 routing + RESOLVER.md generation
- `apps/api/freshness` — M6 staleness signals + recompile
- `apps/api/mcp` — M7 MCP server (+ REST mirror in routers)
- `apps/api/governance` — M8 policy / provenance / confidence gating
- `apps/api/monitor` — M9 closed-loop drift detection
- `apps/web` — M10 Next.js review console
- `apps/api/evals` + `tests` — eval harness

## License

UNLICENSED — internal build.
