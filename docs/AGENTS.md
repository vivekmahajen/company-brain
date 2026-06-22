# Consuming the Brain from an AI agent (MCP)

The Brain exposes skills to agents over MCP (stdio) and a REST mirror.

## MCP

Run the server:

```bash
python -m apps.api.mcp.server
```

Register it with an MCP client (e.g. Claude Desktop / Claude Code). Example
client config:

```json
{
  "mcpServers": {
    "company-brain": {
      "command": "python",
      "args": ["-m", "apps.api.mcp.server"],
      "cwd": "/path/to/company-brain"
    }
  }
}
```

Tools exposed:

| Tool | Purpose |
|---|---|
| `resolve(task)` | Route a natural-language task to the right skill(s) + why |
| `brain_list_skills()` | List executable skills |
| `get_skill_md(slug)` | Fetch the compiled SKILL.md + bound tools + provenance |
| `execute(slug, tool, inputs)` | Run a bound tool; side-effecting tools honor approval gates |

### Approval gating (governance enforced inline)

```
execute("handle-refund", "stripe_refund", {"order_id": "o1", "amount": 620})
  -> {"outcome": "approval_required", "reason": "policy 'refund_high_value' ...", ...}

execute("handle-refund", "stripe_refund", {"order_id": "o2", "amount": 50})
  -> {"outcome": "executed", "result": {...}}
```

A `>$500` refund returns approval-required instead of acting; every call is
written to `execution_log` for closed-loop drift detection (M9).

## REST mirror

Same surface for non-MCP clients (see `apps/api/routers/brain.py`):

```
POST /api/resolve            {"task": "..."}
GET  /api/skills
GET  /api/skills/{slug}
POST /api/execute            {"slug","tool","inputs"}
```
