.PHONY: install demo test api mcp web fmt

install:
	cd apps/api && pip install -r requirements.txt

# Run the Phase-1 refund loop end-to-end against bundled fixtures.
demo:
	python -m apps.api.demo

# Unit/eval test suite (pytest).
test:
	python -m pytest

# CBE Scorecard: GAR/SEC + supporting metrics → evals_out/cbe_scorecard.{json,md,html}
eval:
	python -m apps.api.evals.run --n 5

# CI gate: hard-fail on GAR<100% / PER<100% / determinism<1.0 / regressions.
eval-ci:
	python -m apps.api.evals.run --ci --n 1 --no-persist

# Refit the resolver confidence calibrator on the held-out calib split.
calibrate:
	python -m apps.api.resolver.calibration

# Measured NLP quality on the REAL model (judge-graded extraction F1, N≥5, mean±CI).
# Costs money + needs network + a key — DELIBERATELY NOT in eval-ci (the deterministic
# suite stays the gate). Refuses to fabricate a number without a real provider.
eval-extraction-live:
	@test -n "$$ANTHROPIC_API_KEY" || (echo "set ANTHROPIC_API_KEY (and LLM_PROVIDER=anthropic) first" && exit 2)
	LLM_PROVIDER=anthropic python -m apps.api.evals.extraction_live --n 5 --split test

# REST API (console backend + non-MCP agents).
api:
	uvicorn apps.api.main:app --reload --port 8000

# MCP server (agent interface, stdio transport).
mcp:
	python -m apps.api.mcp.server

# Review console.
web:
	cd apps/web && npm install && npm run dev
