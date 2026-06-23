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

# REST API (console backend + non-MCP agents).
api:
	uvicorn apps.api.main:app --reload --port 8000

# MCP server (agent interface, stdio transport).
mcp:
	python -m apps.api.mcp.server

# Review console.
web:
	cd apps/web && npm install && npm run dev
