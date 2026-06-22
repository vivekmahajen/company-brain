.PHONY: install demo test api mcp web fmt

install:
	cd apps/api && pip install -r requirements.txt

# Run the Phase-1 refund loop end-to-end against bundled fixtures.
demo:
	python -m apps.api.demo

# Eval harness: extraction precision/recall, routing accuracy, governance, determinism.
test:
	python -m pytest

# REST API (console backend + non-MCP agents).
api:
	uvicorn apps.api.main:app --reload --port 8000

# MCP server (agent interface, stdio transport).
mcp:
	python -m apps.api.mcp.server

# Review console.
web:
	cd apps/web && npm install && npm run dev
