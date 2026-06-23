# Consuming the Brain from an AI agent (governed MCP server)

The Brain exposes skills to agents over a first-party **MCP server** with
server-side governance: a single `GovernedExecutor` is the only path to a side
effect, and approval-gated tools are held until a human approves.

## Transports

- **stdio** (local agents — Claude Desktop, Cursor):
  ```bash
  BRAIN_MCP_TOKEN=agent-token python -m apps.api.mcp.stdio
  ```
  See `infra/claude_desktop_config.sample.json`.
- **Streamable HTTP** (remote): mounted into the FastAPI app at `/mcp`; deploys
  on Railway with the REST API. Clients send `Authorization: Bearer <token>`.

## Identity

A credential maps to a `principal` (org + role + scopes). Seeded demo tokens:

| token | role | scopes |
|---|---|---|
| `agent-token` | agent | `invoke:*` |
| `agent-readonly-token` | agent | `invoke:update_support_ticket` only |
| `human-token` | approver | `approve:*`, `invoke:*` |

## Tools

| Tool | Purpose |
|---|---|
| `resolve(task)` | Route a task to the right skill(s) + why (visible skills only) |
| `list_skills()` | Approved skills visible to the caller |
| `get_skill(slug)` | Compiled SKILL.md + bindings + inputs + provenance |
| `get_approval(approval_id)` | Poll a held action's status/result |
| `invoke_skill_tool(skill_slug, tool_name, args, idempotency_key, approval_id?)` | The single governed entry point |
| `<slug>__<tool>` | Per-skill native wrappers (e.g. `handle-refund__stripe_refund`) — thin callers of `invoke_skill_tool` |

Each approved skill is also an MCP **resource** at `skill://<slug>`.

## The two refund paths

```
# under threshold -> executes (sandbox)
handle-refund__stripe_refund {order_id:"55", amount:200, idempotency_key:"a1"}
  -> {status:"executed", result:{refund_id:"re_sandbox_…"}}

# over threshold -> held, NO side effect
handle-refund__stripe_refund {order_id:"1234", amount:620, idempotency_key:"b1"}
  -> {status:"approval_required", approval_id:"…", gate_reason:"amount 620 > 500"}

# a human with approve:stripe_refund approves in the console (or POST
# /api/approvals/{id}/decide). The server executes the held action.
get_approval {approval_id:"…"}  -> {status:"executed", result:{…}}
```

## Safety invariants (enforced server-side)

- **Single choke point** — every side effect routes through `GovernedExecutor.invoke`.
- **Server-side gate facts** — the gate reads the order's true charge/age, not the agent's claim.
- **No execution before approval** — gated side effects are held, not run.
- **Separation of duties** — the requester cannot approve their own request.
- **Idempotency** — repeating an `idempotency_key` replays the stored result; no double-refund.
- **Least visibility** — `resolve`/`get_skill`/`tools/list` show only the caller's approved skills.

Run the acceptance suite: `python scripts/mcp_smoke.py` (sandbox, no keys).

## REST mirror

The same governed path backs `POST /api/execute`; approvals are managed at
`GET /api/approvals` and `POST /api/approvals/{id}/decide`.
